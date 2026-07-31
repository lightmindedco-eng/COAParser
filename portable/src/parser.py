"""Entry point for routing parsed content to the appropriate parser."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from src.core.detector import detect_format, detect_product_name, detect_company_name, detect_metrc_category, detect_report_date
from src.core.extractor import extract_text, read_text
from src.core.logger import log_exception
from src.core.writer import write_output
from src.models.result import ParsedResult

logger = logging.getLogger("coa_parser")
from src.parsers.aerolabs import AerolabsParser
from src.parsers.baseline import BaselineParser
from src.parsers.confident import ConfidentParser
from src.parsers.gateway import GatewayParser
from src.parsers.greenleaf import GreenleafParser
from src.parsers.highres import HighresParser
from src.parsers.metis_qa import MetisQAParser
from src.parsers.sunrise import SunriseParser
from src.parsers.ocr_merge import has_embedded_coa_images, extract_ocr_items


class COAParser:
    def __init__(self) -> None:
        self.parsers = {
            "aerolabs": AerolabsParser(),
            "baseline": BaselineParser(),
            "confident": ConfidentParser(),
            "gateway": GatewayParser(),
            "greenleaf": GreenleafParser(),
            "highres": HighresParser(),
            "metis_qa": MetisQAParser(),
            "sunrise": SunriseParser(),
        }

    def parse_file(self, file_path: str | Path, output_dir: str | None = None) -> ParsedResult:
        path = Path(file_path)
        try:
            content = read_text(path)
            lines = extract_text(content)
        except Exception:
            logger.error("Failed to read or extract text from %s", path.name)
            log_exception()
            return ParsedResult(format_name="error", items=[], metadata={"source_file": str(path), "error": "read/extract failed"})
        format_name = detect_format(content)
        product_name = detect_product_name(lines)
        company_name = detect_company_name(lines)
        metrc_category = detect_metrc_category(lines)
        report_date = detect_report_date(lines)
        parser = self.parsers.get(format_name, self.parsers["aerolabs"])
        try:
            parsed = parser.parse(lines)
        except Exception:
            logger.error("Parser %s failed for %s", format_name, path.name)
            log_exception()
            return ParsedResult(format_name="error", items=[], metadata={"source_file": str(path), "error": f"{format_name} parser crashed"})

        items = parsed.get("items", [])

        metadata: dict[str, Any] = {
            "line_count": len(lines),
            "source_file": str(path),
            "product_name": product_name,
            "company_name": company_name,
            "metrc_category": metrc_category,
            "report_date": report_date,
        }

        try:
            if has_embedded_coa_images(path):
                ocr_data = extract_ocr_items(path, parser_name=format_name)
                if ocr_data:
                    metadata["strain_groups"] = ocr_data
        except Exception:
            logger.warning("OCR image extraction failed for %s", path.name)
            log_exception()

        result = ParsedResult(
            format_name=format_name,
            items=items,
            metadata=metadata,
        )

        if output_dir is not None:
            try:
                strain_groups = result.metadata.get("strain_groups", [])
                report = _build_report(path.name, format_name, result.items, product_name, metrc_category, strain_groups)
                output_path = write_output(
                    output_dir, path.name, report,
                    product_name=product_name,
                    company_name=company_name,
                    lab_name=format_name,
                    report_date=report_date,
                )
                result.output_path = str(output_path)
            except Exception:
                logger.error("Failed to write output for %s", path.name)
                log_exception()

        return result


def _strip_name(name: str) -> str:
    idx = name.find(" - ")
    if idx > 0:
        return name[idx + 3:]
    return name


def _post_process_terpenes(items: list[str]) -> list[str]:
    """Compute Total Terpenes if missing; validate no individual > total."""
    cannabinoids: list[str] = []
    terpenes: list[str] = []
    has_total_terpenes = False

    for item in items:
        if _is_terpene(item):
            base = _strip_name(item.split(":")[0].strip())
            if base.lower() == "total terpenes":
                has_total_terpenes = True
            terpenes.append(item)
        else:
            cannabinoids.append(item)

    terpene_values: list[tuple[str, float, str]] = []
    for t in terpenes:
        name = t.split(":")[0].strip()
        base = _strip_name(name)
        if base.lower() == "total terpenes":
            continue
        if " - " in name:
            continue
        m = re.search(r":\s*(\d+\.?\d*)%$", t)
        if m:
            terpene_values.append((name, float(m.group(1)), t))

    if not has_total_terpenes and terpene_values:
        computed_total = sum(pct for _, pct, _ in terpene_values)
        if computed_total > 0:
            terpenes = [f"Total Terpenes: {computed_total:.4g}%"] + terpenes

    total_terp_pct = 0.0
    for t in terpenes:
        base = _strip_name(t.split(":")[0].strip())
        if base.lower() == "total terpenes":
            m = re.search(r":\s*(\d+\.?\d*)%", t)
            if m:
                total_terp_pct = float(m.group(1))
            break

    if total_terp_pct > 0:
        validated_terpenes: list[str] = []
        for t in terpenes:
            name = t.split(":")[0].strip()
            base = _strip_name(name)
            if base.lower() == "total terpenes":
                validated_terpenes.append(t)
                continue
            if " - " in name:
                validated_terpenes.append(t)
                continue
            m = re.search(r":\s*(\d+\.?\d*)%", t)
            if m:
                pct = float(m.group(1))
                if pct > total_terp_pct:
                    validated_terpenes.append(f"{name}: {total_terp_pct:.4g}%")
                else:
                    validated_terpenes.append(t)
            else:
                validated_terpenes.append(t)
        terpenes = validated_terpenes

    return cannabinoids + terpenes


def _build_report(filename: str, format_name: str, items: list[str], product_name: str = "", metrc_category: str = "", strain_groups: list[tuple[str, list[str]]] | None = None) -> str:
    items = _post_process_terpenes(items)

    lines: list[str] = [
        "=" * 60,
        f"COA Parser Report",
        f"Source file : {filename}",
        f"Detected format : {format_name}",
        "=" * 60,
        "",
    ]
    if product_name:
        lines.append(f"Product : {product_name.strip()}")
    lines.append(f"METRC Category : {metrc_category if metrc_category else 'N/A'}")
    lines.append("")

    def add_section(sec_title: str, sec_items: list[str], indent: str = "") -> None:
        if not sec_items:
            return
        lines.append(f"{indent}{sec_title}")
        lines.append(f"{indent}{'-' * 30}")
        lines.extend(f"{indent}  {item}" for item in sec_items)
        lines.append("")

    if items:
        cannabinoids = [i for i in items if not _is_terpene(i)]
        terpenes = [i for i in items if _is_terpene(i)]
        add_section("CANNABINOIDS", cannabinoids)
        add_section("TERPENES", terpenes)
        if not cannabinoids and not terpenes:
            add_section("DETECTED ANALYTES", items)
    else:
        lines.append("No analytes detected.")
        lines.append("")

    if strain_groups:
        lines.append("=" * 60)
        lines.append("")
        for strain_name, strain_items in strain_groups:
            strain_processed = _post_process_terpenes(strain_items)
            lines.append(f"{strain_name}")
            lines.append("-" * 30)
            s_canna = [i for i in strain_processed if not _is_terpene(i)]
            s_terps = [i for i in strain_processed if _is_terpene(i)]
            if s_canna:
                lines.append("  CANNABINOIDS")
                lines.extend(f"    {item}" for item in s_canna)
            if s_terps:
                lines.append("  TERPENES")
                lines.extend(f"    {item}" for item in s_terps)
            lines.append("")

    lines.append("=" * 60)
    return "\n".join(lines)


_TERPENE_NAMES = {
    "myrcene", "limonene", "pinene", "linalool", "caryophyllene",
    "humulene", "terpinolene", "ocimene", "bisabolol", "nerolidol",
    "guaiol", "valencene", "geraniol", "camphene", "borneol",
    "eucalyptol", "terpineol", "fenchol", "sabinene", "phellandrene",
    "3-carene", "pulegone", "geranyl acetate", "citronellol", "nerol",
    "isopulegol", "beta-myrcene", "alpha-pinene", "beta-pinene",
    "beta-caryophyllene", "alpha-humulene", "trans-nerolidol",
    "alpha-bisabolol", "beta-ocimene", "d-limonene", "caryophyllene oxide",
    "alpha-terpinene", "gamma-terpinene", "p-cymene", "alpha-terpineol",
    "cis-ocimene", "trans-ocimene",
    "farnesene", "trans-beta-farnesene", "trans-beta-farnesol",
    "total terpenes",
}


def _normalize_compound_name(name: str) -> str:
    """Normalize compound name by replacing Greek letters with spelled-out versions."""
    # Replace Greek letters with their spelled-out equivalents
    normalized = name
    normalized = normalized.replace("α", "alpha-")
    normalized = normalized.replace("β", "beta-")
    normalized = normalized.replace("γ", "gamma-")
    normalized = normalized.replace("δ", "delta-")
    # Handle cases where letter is already followed by hyphen
    normalized = normalized.replace("alpha--", "alpha-")
    normalized = normalized.replace("beta--", "beta-")
    normalized = normalized.replace("gamma--", "gamma-")
    normalized = normalized.replace("delta--", "delta-")
    # Handle OCR misreads of Greek letter prefixes (a→α, b→β, y→γ)
    normalized = re.sub(r'\ba-(?=[A-Za-z])', 'alpha-', normalized, flags=re.IGNORECASE)
    normalized = re.sub(r'\bb-(?=[A-Za-z])', 'beta-', normalized, flags=re.IGNORECASE)
    normalized = re.sub(r'\by-(?=[A-Za-z])', 'gamma-', normalized, flags=re.IGNORECASE)
    return normalized


def _is_terpene(item: str) -> bool:
    compound_name = item.split(":")[0].strip()
    normalized = _normalize_compound_name(compound_name).lower()
    if normalized in _TERPENE_NAMES:
        return True
    idx = normalized.find(" - ")
    if idx > 0:
        return normalized[idx + 3:] in _TERPENE_NAMES
    return False

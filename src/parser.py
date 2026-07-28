"""Entry point for routing parsed content to the appropriate parser."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from src.core.detector import detect_format, detect_product_name, detect_company_name, detect_report_date
from src.core.extractor import extract_text, read_text
from src.core.writer import write_output
from src.models.result import ParsedResult
from src.parsers.aerolabs import AerolabsParser
from src.parsers.baseline import BaselineParser
from src.parsers.confident import ConfidentParser
from src.parsers.gateway import GatewayParser


class COAParser:
    def __init__(self) -> None:
        self.parsers = {
            "aerolabs": AerolabsParser(),
            "baseline": BaselineParser(),
            "gateway": GatewayParser(),
            "confident": ConfidentParser(),
        }

    def parse_file(self, file_path: str | Path, output_dir: str | None = None) -> ParsedResult:
        path = Path(file_path)
        content = read_text(path)
        lines = extract_text(content)
        format_name = detect_format(content)
        product_name = detect_product_name(lines)
        company_name = detect_company_name(lines)
        report_date = detect_report_date(lines)
        parser = self.parsers.get(format_name, self.parsers["aerolabs"])
        parsed = parser.parse(lines)

        result = ParsedResult(
            format_name=format_name,
            items=parsed.get("items", []),
            metadata={
                "line_count": len(lines),
                "source_file": str(path),
                "product_name": product_name,
                "company_name": company_name,
                "report_date": report_date,
            },
        )

        if output_dir is not None:
            report = _build_report(path.name, format_name, result.items)
            output_path = write_output(
                output_dir, path.name, report,
                product_name=product_name,
                company_name=company_name,
                lab_name=format_name,
                report_date=report_date,
            )
            result.output_path = str(output_path)

        return result


def _post_process_terpenes(items: list[str]) -> list[str]:
    """Compute Total Terpenes if missing; validate no individual > total."""
    # Separate cannabinoids and terpenes
    cannabinoids: list[str] = []
    terpenes: list[str] = []
    has_total_terpenes = False

    for item in items:
        if _is_terpene(item):
            if item.split(":")[0].strip().lower() == "total terpenes":
                has_total_terpenes = True
            terpenes.append(item)
        else:
            cannabinoids.append(item)

    # Parse individual terpene percentages
    terpene_values: list[tuple[str, float, str]] = []  # (name, pct, original_item)
    for t in terpenes:
        name = t.split(":")[0].strip()
        if name.lower() == "total terpenes":
            continue
        m = re.search(r":\s*(\d+\.?\d*)%$", t)
        if m:
            terpene_values.append((name, float(m.group(1)), t))

    # Compute total if missing
    if not has_total_terpenes and terpene_values:
        computed_total = sum(pct for _, pct, _ in terpene_values)
        if computed_total > 0:
            terpenes = [f"Total Terpenes: {computed_total:.4g}%"] + terpenes

    # Validate: no individual terpene should exceed Total Terpenes
    # Find the Total Terpenes value
    total_terp_pct = 0.0
    for t in terpenes:
        if t.split(":")[0].strip().lower() == "total terpenes":
            m = re.search(r":\s*(\d+\.?\d*)%", t)
            if m:
                total_terp_pct = float(m.group(1))
            break

    if total_terp_pct > 0:
        validated_terpenes: list[str] = []
        for t in terpenes:
            name = t.split(":")[0].strip()
            if name.lower() == "total terpenes":
                validated_terpenes.append(t)
                continue
            m = re.search(r":\s*(\d+\.?\d*)%", t)
            if m:
                pct = float(m.group(1))
                if pct > total_terp_pct:
                    # Cap individual terpene at total (shouldn't happen, but safety check)
                    validated_terpenes.append(f"{name}: {total_terp_pct:.4g}%")
                else:
                    validated_terpenes.append(t)
            else:
                validated_terpenes.append(t)
        terpenes = validated_terpenes

    return cannabinoids + terpenes


def _build_report(filename: str, format_name: str, items: list[str]) -> str:
    # Post-process: compute Total Terpenes if missing, validate individual terpenes
    items = _post_process_terpenes(items)

    lines: list[str] = [
        "=" * 60,
        f"COA Parser Report",
        f"Source file : {filename}",
        f"Detected format : {format_name}",
        "=" * 60,
        "",
    ]
    if items:
        cannabinoids = [i for i in items if not _is_terpene(i)]
        terpenes = [i for i in items if _is_terpene(i)]
        if cannabinoids:
            lines.append("CANNABINOIDS")
            lines.append("-" * 30)
            lines.extend(f"  {item}" for item in cannabinoids)
            lines.append("")
        if terpenes:
            lines.append("TERPENES")
            lines.append("-" * 30)
            lines.extend(f"  {item}" for item in terpenes)
            lines.append("")
        if not cannabinoids and not terpenes:
            lines.append("DETECTED ANALYTES")
            lines.append("-" * 30)
            lines.extend(f"  {item}" for item in items)
            lines.append("")
    else:
        lines.append("No analytes detected.")
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
    return normalized


def _is_terpene(item: str) -> bool:
    compound_name = item.split(":")[0].strip()
    # Normalize Greek letters first
    normalized = _normalize_compound_name(compound_name)
    return normalized.lower() in _TERPENE_NAMES

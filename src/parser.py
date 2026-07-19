"""Entry point for routing parsed content to the appropriate parser."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.core.detector import detect_format, detect_product_name
from src.core.extractor import extract_text, read_text
from src.core.writer import write_output
from src.models.result import ParsedResult
from src.parsers.aerolabs import AerolabsParser
from src.parsers.confident import ConfidentParser
from src.parsers.gateway import GatewayParser


class COAParser:
    def __init__(self) -> None:
        self.parsers = {
            "aerolabs": AerolabsParser(),
            "gateway": GatewayParser(),
            "confident": ConfidentParser(),
        }

    def parse_file(self, file_path: str | Path, output_dir: str | None = None) -> ParsedResult:
        path = Path(file_path)
        content = read_text(path)
        lines = extract_text(content)
        format_name = detect_format(content)
        product_name = detect_product_name(lines)
        parser = self.parsers.get(format_name, self.parsers["aerolabs"])
        parsed = parser.parse(lines)

        result = ParsedResult(
            format_name=format_name,
            items=parsed.get("items", []),
            metadata={"line_count": len(lines), "source_file": str(path)},
        )

        if output_dir is not None:
            report = _build_report(path.name, format_name, result.items)
            output_path = write_output(output_dir, path.name, report, product_name)
            result.output_path = str(output_path)

        return result


def _build_report(filename: str, format_name: str, items: list[str]) -> str:
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


def _is_terpene(item: str) -> bool:
    return item.split(":")[0].strip().lower() in _TERPENE_NAMES

"""Output writer helpers."""

from __future__ import annotations

from pathlib import Path
import re


def write_output(
    output_dir: str,
    filename: str,
    content: str,
    product_name: str | None = None,
    company_name: str | None = None,
    lab_name: str | None = None,
    report_date: str | None = None,
) -> Path:
    """Write a text blob to the output directory as a .txt file.

    Output filename format: (Company Name)Product Name(Lab Name)(Date).txt
    Falls back to product name alone, then input filename stem.
    """
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)

    parts: list[str] = []
    if company_name:
        parts.append(f"({company_name})")
    if product_name:
        parts.append(product_name)
    if lab_name:
        parts.append(f"({lab_name})")
    if report_date:
        parts.append(f"({report_date})")

    if parts:
        stem = "".join(parts)
    else:
        stem = Path(filename).stem

    # Sanitize for filename
    stem = re.sub(r'[<>:"/\\|?*]', '-', stem)
    stem = stem.strip('. ')

    output_path = path / f"{stem}.txt"
    output_path.write_text(content, encoding="utf-8")
    return output_path

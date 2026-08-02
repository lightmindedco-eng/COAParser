"""Output writer helpers."""

from __future__ import annotations

from pathlib import Path
import re

# Maps output stem -> source filename that created it. When a different source
# PDF would collide on the same output name, a numeric suffix is appended so
# every input keeps its own .txt / .webp pair.
_STEM_SOURCES: dict[str, str] = {}


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
        base_stem = "".join(parts)
    else:
        base_stem = Path(filename).stem

    # Sanitize for filename
    base_stem = re.sub(r'[<>:"/\\|?*]', '-', base_stem)
    base_stem = base_stem.strip('. ')

    source_name = Path(filename).name
    stem = base_stem
    if _STEM_SOURCES.get(stem, source_name) != source_name:
        n = 2
        while True:
            candidate = f"{base_stem} ({n})"
            if _STEM_SOURCES.get(candidate, source_name) == source_name:
                stem = candidate
                break
            n += 1
    _STEM_SOURCES[stem] = source_name

    output_path = path / f"{stem}.txt"
    output_path.write_text(content, encoding="utf-8")
    return output_path

"""Output writer helpers."""

from __future__ import annotations

from pathlib import Path
import re


def write_output(output_dir: str, filename: str, content: str, product_name: str | None = None) -> Path:
    """Write a text blob to the output directory as a .txt file.
    
    If product_name is provided, uses it for the output filename.
    Otherwise falls back to using the input filename stem.
    """
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    
    # Use product name if available, otherwise use input filename
    if product_name:
        # Sanitize product name for use as filename
        # Replace invalid filename characters
        stem = re.sub(r'[<>:"/\\|?*]', '-', product_name)
        # Remove leading/trailing whitespace and dots
        stem = stem.strip('. ')
    else:
        stem = Path(filename).stem
    
    output_path = path / f"{stem}.txt"
    output_path.write_text(content, encoding="utf-8")
    return output_path

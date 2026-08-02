"""Database output helpers: bundle all parsed text and image outputs into one ZIP file."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def default_database_name() -> str:
    """Default base name for the database ZIP, e.g. COA_Database_2026-07-30."""
    return f"COA_Database_{date.today().isoformat()}"


def find_output_files(output_dir: str | Path) -> list[Path]:
    """Return every parse output file (.txt text, .webp image) in the output directory."""
    return sorted([*Path(output_dir).glob("*.txt"), *Path(output_dir).glob("*.webp")])


def create_database_zip(output_dir: str | Path, zip_path: str | Path) -> tuple[int, Path]:
    """Zip all .txt and .webp outputs under output_dir into zip_path.

    Files are stored at the ZIP root under their original names. A .zip
    extension is appended if the target has none.

    Returns (file_count, final_path).
    """
    files = find_output_files(output_dir)
    dest = Path(zip_path)
    if dest.suffix.lower() != ".zip":
        dest = dest.with_suffix(".zip")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(dest, "w", ZIP_DEFLATED) as zf:
        for file in files:
            zf.write(file, arcname=file.name)
    return len(files), dest

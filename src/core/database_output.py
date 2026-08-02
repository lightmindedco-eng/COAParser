"""Database output helpers: bundle parsed text outputs into one ZIP file and
copy the matching WEBP images into the web app's images folder."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from shutil import copy2
from zipfile import ZIP_DEFLATED, ZipFile


def default_database_name() -> str:
    """Default base name for the database ZIP, e.g. COA_Database_2026-07-30."""
    return f"COA_Database_{date.today().isoformat()}"


def find_output_files(output_dir: str | Path) -> list[Path]:
    """Return every .txt output file in the output directory, sorted by name."""
    return sorted(Path(output_dir).glob("*.txt"))


def find_image_files(output_dir: str | Path) -> list[Path]:
    """Return every .webp image output in the output directory, sorted by name."""
    return sorted(Path(output_dir).glob("*.webp"))


def default_images_dir() -> Path:
    """Default web app images folder (COAWeb/images next to the app folder)."""
    return (Path.cwd() / ".." / "COAWeb" / "images").resolve()


def create_database_zip(output_dir: str | Path, zip_path: str | Path) -> tuple[int, Path]:
    """Zip all .txt outputs under output_dir into zip_path.

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


def copy_images(output_dir: str | Path, images_dir: str | Path) -> tuple[int, Path]:
    """Copy every .webp in output_dir into images_dir (created if missing).

    Returns (copied_count, images_dir).
    """
    dest_dir = Path(images_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for file in find_image_files(output_dir):
        copy2(file, dest_dir / file.name)
        count += 1
    return count, dest_dir

from pathlib import Path
from zipfile import ZipFile

from src.core.database_output import (
    create_database_zip,
    default_database_name,
    find_output_files,
)


def test_create_database_zip_zips_all_txt(tmp_path: Path) -> None:
    output_dir = tmp_path / "Output"
    output_dir.mkdir()
    (output_dir / "a.txt").write_text("alpha", encoding="utf-8")
    (output_dir / "b.txt").write_text("bravo", encoding="utf-8")
    (output_dir / "c.pdf").write_bytes(b"not a txt")

    count, dest = create_database_zip(output_dir, tmp_path / "db")

    assert dest.name == "db.zip"
    assert count == 2
    with ZipFile(dest) as zf:
        assert sorted(zf.namelist()) == ["a.txt", "b.txt"]
        assert zf.read("a.txt") == b"alpha"


def test_find_output_files_ignores_non_txt(tmp_path: Path) -> None:
    output_dir = tmp_path / "Output"
    output_dir.mkdir()
    (output_dir / "b.txt").write_text("x", encoding="utf-8")
    (output_dir / "a.txt").write_text("y", encoding="utf-8")

    files = find_output_files(output_dir)

    assert [f.name for f in files] == ["a.txt", "b.txt"]


def test_default_database_name_has_zip_safe_chars() -> None:
    name = default_database_name()
    assert name.startswith("COA_Database_")
    assert all(c.isalnum() or c in "-_" for c in name)

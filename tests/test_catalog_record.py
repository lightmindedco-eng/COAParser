from pathlib import Path

from src.core.catalog_record import (
    build_catalog_doc,
    hash_string,
    image_path_for,
    parse_file,
    parse_filename,
    parse_value,
)

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_TXT = (FIXTURES / "sample_output.txt").read_text(encoding="utf-8")
SAMPLE_NAME = "(788 Collection)Energy Bath Bomb(confident)(01-16-2024).txt"
FLAGS_NAME = (
    "(Choctaw Processing, LLC)FG - Vape - 2.0g Disposable - Bodega Boyz - "
    "Blueberry Muf\u00d7n & Sherblato(confident)(05-29-2026).txt"
)


def test_parse_file_sample_matches_js_golden() -> None:
    pf = parse_file(SAMPLE_TXT, SAMPLE_NAME)
    assert pf["ok"] is True
    assert pf["id"] == "a09f2ca"
    r = pf["record"]
    assert r["product"] == "Energy Bath Bomb"
    assert r["company"] == "788 Collection"
    assert r["lab"] == "confident"
    assert r["date"] == "2024-01-16"
    assert r["dateRaw"] == "01-16-2024"
    assert r["metrcCategory"] is None
    assert r["itemCount"] == 6
    assert r["quality"] == 0.92
    assert r["flags"] == []
    assert set(r["sections"]) == {"CANNABINOIDS", "TERPENES"}
    assert len(r["sections"]["CANNABINOIDS"]) == 3


def test_parse_file_flags_fixture_matches_js_golden() -> None:
    txt = (FIXTURES / "sample_flags_output.txt").read_text(encoding="utf-8")
    pf = parse_file(txt, FLAGS_NAME)
    assert pf["id"] == "a9fe2d29"
    r = pf["record"]
    assert r["company"] == "Choctaw Processing, LLC"
    assert r["product"] == (
        "FG | Vape | 2.0g Disposable | Bodega Boyz - Blueberry Muf\u00d7n & Sherblato"
    )
    assert r["itemCount"] == 51
    assert r["quality"] == 1
    assert r["flags"] == ['Possible section title not followed by a rule: "Delta-8-THC"']


def test_hash_string_is_deterministic_lowercase_hex() -> None:
    assert hash_string("hello") == hash_string("hello")
    assert set(hash_string("hello")) <= set("abcdef0123456789")


def test_parse_filename_decomposes_groups() -> None:
    fn = parse_filename(SAMPLE_NAME[:-4])
    assert fn["company"] == "788 Collection"
    assert fn["product"] == "Energy Bath Bomb"
    assert fn["lab"] == "confident"
    assert fn["date"] == "2024-01-16"
    assert fn["flags"] == []


def test_parse_value_statuses() -> None:
    assert parse_value("N/A")["status"] == "na"
    assert parse_value("Not Detected")["status"] == "not_detected"
    assert parse_value("<LOQ")["status"] == "below_loq"
    present = parse_value("0.12%")
    assert present["status"] == "present"
    assert present["value"] == 0.12
    assert present["unit"] == "%"
    assert parse_value("apple pie")["status"] == "text"


def test_build_catalog_doc_fields() -> None:
    doc = build_catalog_doc(SAMPLE_TXT, SAMPLE_NAME)
    assert doc["id"] == "a09f2ca"
    assert doc["imagePath"] == (
        "images/(788 Collection)Energy Bath Bomb(confident)(01-16-2024).webp"
    )
    assert "metrcCategoryRaw" not in doc
    assert "energy bath bomb" in doc["searchText"]
    assert "cannabinoids" in doc["searchText"]
    assert "total thc" in doc["searchText"]


def test_image_path_for() -> None:
    assert image_path_for(SAMPLE_NAME) == (
        "images/(788 Collection)Energy Bath Bomb(confident)(01-16-2024).webp"
    )

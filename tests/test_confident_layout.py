"""Regression tests for Confident parser column-layout handling."""

from __future__ import annotations

from src.parsers.confident import ConfidentParser


def test_confident_picks_result_pct_not_mg_per_g_column() -> None:
    """Confident LIMS tables can carry both 'Result %' and 'Result mg/g'
    numeric columns. The parser must take the % column (first numeric),
    not the mg/g column (which is 10x the % value)."""
    lines = [
        "Certi×cate of Analysis",
        "Powered by Con×dent LIMS",
        "Cannabinoids",
        "Analyte",
        "LOQ",
        "Result",
        "Result",
        "%",
        "%",
        "mg/g",
        "ThCa (Tetrahydrocannabinolic Acid)",
        "33.262",
        "332.62",
        "Δ9-THC (Delta 9 Tetrahydrocannabinol)",
        "0.911",
        "9.11",
        "CBDa (Cannabidiolic Acid)",
        "0.081",
        "0.81",
        "Total",
        "35.786",
    ]

    parser = ConfidentParser()
    result = parser.parse(lines)
    items = result["items"]

    assert "THCa: 33.262%" in items
    assert "THCa: 332.62%" not in items
    assert "Delta-9-THC: 0.911%" in items
    assert "Delta-9-THC: 9.11%" not in items
    assert "CBDa: 0.081%" in items
    assert "CBDa: 0.81%" not in items


def test_confident_terpene_rows_keep_loq_column() -> None:
    """Terpene sections with the same 'LOQ | % | mg/g' headers have 3 numerics
    per row; the % is the second value (not the second-to-last), and rows with
    unrecognized intermediate compounds must not shift the selection."""
    lines = [
        "Terpenes",
        "Analyte",
        "LOQ Result Result",
        "%",
        "% mg/g",
        "alpha-Farnesene",
        "0.001 0.466",
        "4.66",
        "Limonene",
        "0.002 0.424",
        "4.24",
        "Caryophyllene",
        "Oxide",
        "0.002 0.126",
        "1.26",
        "alpha-Cedrene",
        "0.002 0.115",
        "1.15",
        "(-)-Borneol",
        "0.002 0.109",
        "1.09",
        "Total Terpenes",
        "2.991",
    ]

    parser = ConfidentParser()
    result = parser.parse(lines)
    items = result["items"]

    assert "Farnesene: 0.466%" in items
    assert "Farnesene: 4.66%" not in items
    assert "Limonene: 0.424%" in items
    assert "Limonene: 4.24%" not in items
    assert "beta-Caryophyllene: 0.126%" in items
    assert "beta-Caryophyllene: 0.115%" not in items
    assert "Borneol: 0.109%" in items
    assert "Borneol: 1.09%" not in items


def test_confident_lod_layout_uses_front_index() -> None:
    """Tables with LOD | LOQ | % | mg/g columns keep the % at the 3rd numeric
    even though an mg/g column is present."""
    lines = [
        "Cannabinoids",
        "Analyte",
        "LOD",
        "LOQ",
        "Results",
        "Results",
        "PPM",
        "PPM",
        "%",
        "mg/g",
        "THCa",
        "15000.00",
        "30000.00",
        "ND",
        "ND",
        "Delta-9-THC",
        "15000.00",
        "30000.00",
        "85.45",
        "854.5",
    ]

    parser = ConfidentParser()
    result = parser.parse(lines)
    items = result["items"]

    assert "Delta-9-THC: 85.45%" in items
    assert "Delta-9-THC: 854.5%" not in items
    assert "Delta-9-THC: 30000.00%" not in items

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

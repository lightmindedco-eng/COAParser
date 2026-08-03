import re

import pytest

from src.core import compound_profiles as cp


def _load(tmp_path, text: str) -> dict[str, cp.CompoundProfile]:
    path = tmp_path / "profiles.txt"
    path.write_text(text, encoding="utf-8")
    cp._state.update(mtime=None, profiles=None)
    monkey = pytest.MonkeyPatch()
    monkey.setattr(cp, "PROFILES_FILE", path)
    try:
        return cp._parse(path)
    finally:
        monkey.undo()


CANNABINOIDS = """# Cannabinoids
THC = Euphoric, Pain Relief, #EF9800
CBG = Focus, Anti-inflammatory (CBG, CBGV), #F9DD25
# Terpenes
beta-Myrcene = Calming, Sedating, #5E35B1
trans-Nerolidol = Calming, Sedating, #5E35B1
d-Limonene = Mood Elevation, Stress Relief, #4CAF50
# Aliases
Myrcene = beta-Myrcene
Limonene = d-Limonene
"""


def test_normalize_name() -> None:
    assert cp.normalize_name("Delta-9-THC") == "delta-9-thc"
    assert cp.normalize_name("THC - Flower") == "flower"
    assert cp.normalize_name("β-Myrcene") == "beta-myrcene"
    assert cp.normalize_name("a-Pinene") == "alpha-pinene"
    assert cp.normalize_name("b-Caryophyllene") == "beta-caryophyllene"
    assert cp.normalize_name("  CBD  ") == "cbd"


def test_split_on_top_commas() -> None:
    assert cp._split_on_top_commas("A, B, C") == ["A", "B", "C"]
    assert cp._split_on_top_commas("Precursor (CBG, CBD, CBC), Anti-inflammatory") == [
        "Precursor (CBG, CBD, CBC)",
        "Anti-inflammatory",
    ]


def test_parse_sections_and_effects(tmp_path) -> None:
    profiles = _load(tmp_path, CANNABINOIDS)
    assert profiles["thc"].kind == "cannabinoid"
    assert profiles["beta-myrcene"].kind == "terpene"
    assert profiles["thc"].effects == ["Euphoric", "Pain Relief"]
    assert profiles["cbg"].effects == ["Focus", "Anti-inflammatory (CBG, CBGV)"]
    assert profiles["thc"].color == "#EF9800"


def test_alias_points_to_canonical(tmp_path) -> None:
    profiles = _load(tmp_path, CANNABINOIDS)
    assert profiles["myrcene"] is profiles["beta-myrcene"]
    assert profiles["limonene"] is profiles["d-limonene"]
    assert profiles["myrcene"].color == profiles["beta-myrcene"].color
    assert profiles["limonene"].effects == profiles["d-limonene"].effects


def test_green_gradient_differentiates_shared_colors(tmp_path) -> None:
    profiles = _load(tmp_path, CANNABINOIDS)
    base = profiles["beta-myrcene"].color
    shifted = profiles["trans-nerolidol"].color
    assert base == "#5E35B1", "first sorted key keeps its color"
    assert base != shifted, "shared colors must be differentiated"
    assert re.fullmatch(r"#[0-9A-F]{6}", shifted)


def test_shift_toward_green_moves_hue_closer() -> None:
    purple = cp._shift_toward_green("#5E35B1", 1.0)
    green = cp._shift_toward_green("#5E35B1", 0.0)
    assert purple != green


def test_unknown_compound() -> None:
    assert cp.get_color("Not A Compound") is None
    assert cp.get_effects("Not A Compound") == []


def test_real_data_file_loads() -> None:
    profiles = cp._load()
    assert "thc" in profiles
    assert "beta-myrcene" in profiles
    assert "d-limonene" in profiles
    assert profiles["myrcene"] is profiles["beta-myrcene"]
    assert all(re.fullmatch(r"#[0-9A-Fa-f]{6}", p.color) for p in profiles.values())

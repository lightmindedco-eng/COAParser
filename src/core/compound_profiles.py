"""Load compound effect/color profiles from data/cannabinoids_terpenes.txt.

This file is the single source of truth for the visual output. Its format:

    # Section                     (section marker: Cannabinoids / Terpenes / Aliases)
    Name = Effect1, Effect2, #RRGGBB
    ...
    # Aliases
    Generic = Specific            (maps a generic name onto a specific entry)

Entries may contain commas inside parentheses (e.g. "Precursor (CBG, CBD, ...)"),
so effects are split on commas only outside parentheses.
"""

from __future__ import annotations

import colorsys
import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / ".." / "data"
PROFILES_FILE = DATA_DIR / "cannabinoids_terpenes.txt"

MAX_GREEN_SHIFT = 0.18

_HEX_RE = re.compile(r"#[0-9A-Fa-f]{6}$")


class CompoundProfile:
    __slots__ = ("name", "kind", "effects", "color")

    def __init__(self, name: str, kind: str, effects: list[str], color: str) -> None:
        self.name = name
        self.kind = kind  # "cannabinoid" | "terpene"
        self.effects = effects
        self.color = color  # "#RRGGBB"


def normalize_name(name: str) -> str:
    """Normalize a compound name for lookups (mirrors parser/visual normalizers)."""
    n = name.strip().lower()
    n = n.replace("α", "alpha-").replace("β", "beta-").replace("γ", "gamma-").replace("δ", "delta-")
    n = re.sub(r"\ba-(?=[a-z])", "alpha-", n)
    n = re.sub(r"\bb-(?=[a-z])", "beta-", n)
    n = re.sub(r"\by-(?=[a-z])", "gamma-", n)
    n = n.replace("alpha--", "alpha-").replace("beta--", "beta-").replace("gamma--", "gamma-")
    idx = n.find(" - ")
    if idx > 0:
        n = n[idx + 3:]
    return n


def _split_on_top_commas(text: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    parts.append("".join(current).strip())
    return [p for p in parts if p]


def _shift_toward_green(hex_color: str, fraction: float) -> str:
    """Move a hex color a fraction of the way toward green (hue 120)."""
    r, g, b = (int(hex_color[i:i + 2], 16) / 255.0 for i in (1, 3, 5))
    h, light, sat = colorsys.rgb_to_hls(r, g, b)
    green_hue = 120.0 / 360.0
    diff = (green_hue - h) % 1.0
    if diff > 0.5:
        diff -= 1.0
    h = (h + diff * fraction) % 1.0
    r, g, b = colorsys.hls_to_rgb(h, light, sat)
    return "#{:02X}{:02X}{:02X}".format(
        int(round(r * 255)), int(round(g * 255)), int(round(b * 255))
    )


def _parse(path: Path) -> dict[str, CompoundProfile]:
    profiles: dict[str, CompoundProfile] = {}
    aliases: dict[str, str] = {}
    kind = "cannabinoid"

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return profiles

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            header = line[1:].strip().lower()
            if "cannabinoid" in header:
                kind = "cannabinoid"
            elif "terpene" in header:
                kind = "terpene"
            elif "alias" in header:
                kind = "alias"
            continue

        if "=" not in line:
            continue
        name, _, rest = line.partition("=")
        name = name.strip()
        tokens = _split_on_top_commas(rest)

        if kind == "alias":
            if len(tokens) >= 1:
                aliases[normalize_name(name)] = normalize_name(tokens[0])
            continue

        color = tokens[-1] if tokens and _HEX_RE.match(tokens[-1]) else None
        if color is not None:
            effects = tokens[:-1]
        else:
            effects = tokens
        if not name or not effects:
            continue
        profiles[normalize_name(name)] = CompoundProfile(
            name=name,
            kind=kind,
            effects=[e for e in effects if e],
            color=color or "#888888",
        )

    for alias, target in aliases.items():
        if target in profiles:
            profiles[alias] = profiles[target]

    _apply_green_gradient(profiles)

    for alias, target in aliases.items():
        if target in profiles:
            profiles[alias] = profiles[target]

    return profiles


def _apply_green_gradient(profiles: dict[str, CompoundProfile]) -> None:
    """Slightly shift shared colors toward green so similar compounds differ."""
    groups: dict[str, list[str]] = {}
    for key, profile in profiles.items():
        groups.setdefault(profile.color.upper(), []).append(key)

    for color, keys in groups.items():
        if len(keys) < 2:
            continue
        keys = sorted(keys)
        step = MAX_GREEN_SHIFT / (len(keys) - 1)
        for idx, key in enumerate(keys):
            if idx == 0:
                continue
            profile = profiles[key]
            profiles[key] = CompoundProfile(
                profile.name,
                profile.kind,
                list(profile.effects),
                _shift_toward_green(profile.color, idx * step),
            )


_state: dict = {"mtime": None, "profiles": None}


def _load() -> dict[str, CompoundProfile]:
    try:
        mtime = PROFILES_FILE.stat().st_mtime
    except OSError:
        mtime = None
    if _state["profiles"] is not None and _state["mtime"] == mtime:
        return _state["profiles"]
    profiles = _parse(PROFILES_FILE)
    _state.update(mtime=mtime, profiles=profiles)
    return profiles


def get_profile(name: str) -> CompoundProfile | None:
    return _load().get(normalize_name(name))


def get_color(name: str) -> str | None:
    profile = get_profile(name)
    return profile.color if profile is not None else None


def get_effects(name: str) -> list[str]:
    profile = get_profile(name)
    return list(profile.effects) if profile is not None else []

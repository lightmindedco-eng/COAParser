from __future__ import annotations

import re
from typing import Any

from .base import BaseParser


class SunriseParser(BaseParser):
    name = "sunrise"

    _ABBREV_MAP: dict[str, str] = {
        "CBC": "CBC",
        "CBD": "CBD",
        "CBDA": "CBDA",
        "CBDV": "CBDV",
        "CBG": "CBG",
        "CBGA": "CBGA",
        "CBN": "CBN",
        "THCA": "THCa",
        "THCV": "THCV",
        "THCVA": "THCVA",
        "D8-THC": "d8-THC",
        "D9-THC": "d9-THC",
    }

    _SUMMARY_LABELS: dict[str, str] = {
        "total thc": "Total THC",
        "total cbd": "Total CBD",
        "d9-thc": "d9-THC",
        "total terpenes": "Total Terpenes",
    }

    def parse(self, lines: list[str]) -> dict[str, Any]:
        total_weight_g = self._extract_total_weight(lines)
        summary_values = self._extract_summary(lines)
        compound_values = self._extract_compounds(lines)

        results: list[str] = []

        summary_names_in_table: set[str] = set()
        for compound_abbrev, _ in compound_values:
            summary_names_in_table.add(self._ABBREV_MAP[compound_abbrev].lower())

        for key, (val, unit) in summary_values.items():
            display_name = self._SUMMARY_LABELS[key]
            if display_name.lower() in summary_names_in_table:
                continue
            if unit == "mg/unit" and total_weight_g:
                pct = val / (total_weight_g * 10)
                results.append(f"{display_name}: {pct:.4g}% ({val:.4g} mg/unit)")
            elif unit == "%":
                results.append(f"{display_name}: {val:.4g}%")

        total_mg = sum(v for _, v in compound_values if v is not None)
        for abbrev, mg_val in compound_values:
            name = self._ABBREV_MAP[abbrev]
            if mg_val is not None and total_mg > 0:
                pct = (mg_val / total_mg) * 100
                results.append(f"{name}: {pct:.4g}% ({mg_val:.4g} mg/unit)")
            elif mg_val is not None:
                results.append(f"{name}: {mg_val:.4g} mg/unit")

        if results:
            return {"format": self.name, "items": results}
        return {"format": self.name, "items": lines[:20] or ["No content extracted from document"]}

    def _extract_total_weight(self, lines: list[str]) -> float | None:
        for line in lines:
            m = re.match(r"Total Weight \(g\):\s*([\d.]+)", line.strip())
            if m:
                return float(m.group(1))
        return None

    def _extract_summary(self, lines: list[str]) -> dict[str, tuple[float, str]]:
        result: dict[str, tuple[float, str]] = {}
        consumed: set[int] = set()
        for i, line in enumerate(lines):
            lower = line.strip().lower()
            if lower in self._SUMMARY_LABELS:
                for j in range(i + 1, min(i + 15, len(lines))):
                    if j in consumed:
                        continue
                    stripped = lines[j].strip()
                    m = re.match(r"^([\d.]+)\s*(mg/unit|%)$", stripped)
                    if m:
                        val = float(m.group(1))
                        unit = m.group(2)
                        result[lower] = (val, unit)
                        consumed.add(j)
                        break
        return result

    def _extract_compounds(self, lines: list[str]) -> list[tuple[str, float | None]]:
        result: list[tuple[str, float | None]] = []
        seen_abbrevs: set[str] = set()
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.lower() in self._SUMMARY_LABELS:
                continue
            for abbrev in self._ABBREV_MAP:
                if abbrev in seen_abbrevs:
                    continue
                if f"({abbrev}" in stripped or stripped == abbrev:
                    found_val: float | None = None
                    for k in range(1, 10):
                        if i + k >= len(lines):
                            break
                        next_line = lines[i + k].strip()
                        if not next_line:
                            continue
                        if next_line.upper() == "ND":
                            found_val = None
                            break
                        m_num = re.match(r"^(\d+\.?\d*)$", next_line)
                        if m_num:
                            found_val = float(m_num.group(1))
                            break
                        break
                    result.append((abbrev, found_val))
                    seen_abbrevs.add(abbrev)
                    break
        return result

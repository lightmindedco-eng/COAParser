"""Parser for Baseline Laboratories COA documents."""

from __future__ import annotations

import re
from typing import Any

from .base import BaseParser


class BaselineParser(BaseParser):
    """Parser for Baseline Laboratories COA format.

    Layout (values on separate lines):
        Cannabinoid          (or Terpenes)
        Result (%)
        Result (μg/g)
        CBDa
        0.113
        1130
        CBG
        2.642
        26400
    """

    name = "baseline"

    @staticmethod
    def _normalize_name(name: str) -> str:
        """Normalize compound name by replacing Greek letters with spelled-out versions."""
        normalized = name
        normalized = normalized.replace("\u0394", "delta-").replace("\u03b4", "delta-")
        normalized = normalized.replace("\u03b1", "alpha-").replace("\u0391", "alpha-")
        normalized = normalized.replace("\u03b2", "beta-").replace("\u0392", "beta-")
        normalized = normalized.replace("\u03b3", "gamma-").replace("\u0393", "gamma-")
        for letter in ["delta", "alpha", "beta", "gamma"]:
            normalized = normalized.replace(f"{letter}--", f"{letter}-")
        return normalized

    def _match_compound(self, line_lower: str) -> str | None:
        """Match a line against vocabulary and aliases. Returns canonical name or None."""
        all_compounds = sorted(
            self.vocabulary["cannabinoids"] + self.vocabulary["terpenes"],
            key=len, reverse=True,
        )

        for compound in all_compounds:
            if re.search(rf"\b{re.escape(compound.lower())}\b", line_lower):
                return compound

        for canonical, aliases in self.vocabulary["aliases"].items():
            for alias in aliases:
                if re.search(rf"\b{re.escape(alias.lower())}\b", line_lower):
                    return canonical

        return None

    def _extract_compounds(self, lines: list[str]) -> list[str]:
        """
        Extract compound names and percentage values from Baseline Labs COA.

        Strategy:
        1. Extract summary totals (Total THC, Total CBD, Total Cannabinoids, Total Terpenes)
        2. Detect section headers (Cannabinoid, Terpenes)
        3. For each compound line, the next line is Result %
        4. ND on the value line = not detected, skip
        """
        nd_re = re.compile(r"^ND$", re.IGNORECASE)
        number_re = re.compile(r"^(\d+\.?\d*)$")
        total_re = re.compile(r"(Total\s+[\w\s-]+?):\s*(\d+\.?\d*)\s*%", re.IGNORECASE)
        results: list[str] = []
        seen: set[str] = set()

        # Pass 0 – Extract summary totals (Total THC, Total CBD, Total Cannabinoids, Total Terpenes)
        _valid_totals = {
            "total cannabinoids", "total thc", "total cbd", "total terpenes",
        }
        for line in lines:
            m = total_re.search(line)
            if m:
                label = m.group(1).strip()
                value = m.group(2)
                key = label.lower()
                if key in _valid_totals and key not in seen:
                    seen.add(key)
                    results.append(f"{label}: {value}%")

        # Pass 0b – Adjacent-line totals: "TOTAL THC" on one line, numeric on next
        for i, line in enumerate(lines):
            stripped = line.strip()
            m = re.match(r"^(Total\s+[\w\s-]+?)\s*$", stripped, re.IGNORECASE)
            if m and i + 1 < len(lines):
                label = m.group(1).strip()
                key = label.lower()
                if key in _valid_totals and key not in seen:
                    next_line = lines[i + 1].strip()
                    m_val = number_re.match(next_line)
                    if m_val:
                        seen.add(key)
                        results.append(f"{label}: {m_val.group(1)}%")

        in_section = False

        i = 0
        while i < len(lines):
            line = lines[i].strip()
            line_lower = line.lower()

            # Detect section headers
            if re.search(r"^cannabinoid", line_lower) or re.search(r"^terpene", line_lower):
                in_section = True
                i += 1
                continue

            # Skip header rows, metadata, totals, and non-data lines
            if (
                not line
                or "result" in line_lower
                or "sop" in line_lower
                or "date" in line_lower
                or "method" in line_lower
                or "total" in line_lower
                or "reporting limit" in line_lower
                or "nd = not detected" in line_lower
                or "analysis" in line_lower
                or re.search(r"^\d+\s*$", line)  # standalone page numbers
                or "=" in line
                or "certificate" in line_lower
                or "license" in line_lower
                or "sample" in line_lower
                or "batch" in line_lower
                or "metrc" in line_lower
                or "matrix" in line_lower
                or "page" in line_lower
                or "report" in line_lower
                or "passed" in line_lower
                or "not detected" in line_lower
            ):
                i += 1
                continue

            if not in_section:
                i += 1
                continue

            # Try to match a compound name
            normalized = self._normalize_name(line)
            matched = self._match_compound(normalized.lower())

            if matched is None or matched.lower() in seen:
                i += 1
                continue

            # Look ahead for the value (next line should be Result %)
            value: str | None = None
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if nd_re.match(next_line):
                    value = "ND"
                elif number_re.match(next_line):
                    value = f"{next_line}%"

            seen.add(matched.lower())
            if value == "ND":
                pass  # skip ND compounds
            elif value:
                results.append(f"{matched}: {value}")
            else:
                results.append(matched)

            i += 1

        # Post-filter: remove compounds with percentage values below 0.01%
        filtered: list[str] = []
        for item in results:
            m = re.search(r":\s*(\d+\.?\d*)%$", item)
            if m:
                pct = float(m.group(1))
                if pct < 0.01:
                    continue
            filtered.append(item)

        return filtered

    def parse(self, lines: list[str]) -> dict[str, Any]:
        compounds = self._extract_compounds(lines)
        if compounds:
            return {"format": self.name, "items": compounds}
        return {"format": self.name, "items": lines[:20] or ["No content extracted from document"]}

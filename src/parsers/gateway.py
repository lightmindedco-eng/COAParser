"""Parser for Gateway-style COA documents."""

from __future__ import annotations

import re
from typing import Any

from .base import BaseParser


class GatewayParser(BaseParser):
    name = "gateway"

    def _extract_compounds(self, lines: list[str]) -> list[str]:
        """
        Extract compound names and percentage values from Gateway Labs COA.

        Gateway Labs tables have different column orders:
        - Cannabinoids: Compound → CAS# → LOD → LOQ → Result % → mg/g (3rd numeric)
        - Terpenes: Compound → mg/g → Result % → CAS# → LOD → LOQ (2nd numeric)
        """
        number_re = re.compile(r"^(\d+\.?\d*)$")
        nd_re = re.compile(r"^ND$", re.IGNORECASE)
        total_re = re.compile(r"(Total\s+[\w\s-]+?):\s*(\d+\.?\d*)\s*%", re.IGNORECASE)
        rank_prefix_re = re.compile(r"^\d+\s+")

        results: list[str] = []
        seen: set[str] = set()
        # Sort longest-first so specific names (e.g. d8-THC) match before generic (THC)
        all_compounds = sorted(
            self.vocabulary["cannabinoids"] + self.vocabulary["terpenes"],
            key=len,
            reverse=True,
        )

        # Pass 1a – "Total X: Y %" on a single line
        for line in lines:
            m = total_re.search(line)
            if m:
                label = m.group(1).strip()
                value = m.group(2)
                key = label.lower()
                if key not in seen:
                    seen.add(key)
                    results.append(f"{label}: {value}%")

        # Pass 1b – "Total X" on one line, numeric value on the next line
        # Only match cannabinoid/terpene totals to avoid capturing unrelated test totals
        _valid_totals = {
            "total cannabinoids", "total thc", "total cbd", "total cbn",
            "total cbg", "total cbga", "total cbc", "total cbca",
            "total thcv", "total thcva", "total cbdv", "total cbdva",
            "total cbl", "total cbt", "total terpenes",
            "total terpene", "total monoterpenes", "total sesquiterpenes",
        }
        for i, line in enumerate(lines):
            m = re.match(r"^(Total\s+[\w\s-]+?)\s*$", line.strip(), re.IGNORECASE)
            if m and i + 1 < len(lines):
                label = m.group(1).strip()
                if label.lower() not in _valid_totals:
                    continue
                next_line = lines[i + 1].strip()
                m_val = number_re.match(next_line)
                m_nd = nd_re.match(next_line)
                key = label.lower()
                if key not in seen:
                    if m_nd:
                        seen.add(key)
                        results.append(f"{label}: ND")
                    elif m_val:
                        seen.add(key)
                        results.append(f"{label}: {m_val.group(1)}%")

        # Pass 2 – individual compound rows
        # Track terpene column order variant: some Gateway COAs use
        # mg/g, Result%, CAS#, LOD, LOQ (2nd numeric) vs LOD, LOQ, Result%, mg/g (3rd numeric)
        in_terpene_section = False
        terpene_result_index = 3  # default: 3rd numeric = Result %
        for i, raw_line in enumerate(lines):
            line_lower = raw_line.strip().lower()

            # Detect section boundaries and determine terpene column order
            if re.search(r"terpene", line_lower) and not re.search(r"^total\s", line_lower):
                if not in_terpene_section:
                    # First entry into terpene section: detect column variant
                    in_terpene_section = True
                    terpene_result_index = 3  # default: LOD, LOQ, Result%, mg/g
                    for j in range(1, min(11, len(lines) - i)):
                        if "cas#" in lines[i + j].lower():
                            terpene_result_index = 2  # newer format: mg/g, Result%, CAS#...
                            break
            elif re.search(r"cannabinoid", line_lower) and not re.search(r"^total\s", line_lower):
                in_terpene_section = False

            line = rank_prefix_re.sub("", raw_line.strip())

            # Skip headers and totals
            if re.search(r"^total\s", line_lower) or "analyte" in line_lower:
                continue

            # Match against vocabulary (sorted longest-first)
            matched: str | None = None
            for compound in all_compounds:
                if re.search(rf"\b{re.escape(compound.lower())}\b", line_lower):
                    matched = compound
                    break

            # Match against aliases
            if matched is None:
                for canonical, aliases in self.vocabulary["aliases"].items():
                    for alias in aliases:
                        if re.search(rf"\b{re.escape(alias.lower())}\b", line_lower):
                            matched = canonical
                            break
                    if matched:
                        break

            if matched is None or matched.lower() in seen:
                continue

            # Collect next 12 lines
            ahead = [lines[i + j].strip() if i + j < len(lines) else "" for j in range(1, 13)]

            value: str | None = None
            target_numeric = terpene_result_index if in_terpene_section else 3
            numeric_count = 0
            for candidate_line in ahead:
                m_num = number_re.match(candidate_line)
                if m_num:
                    numeric_count += 1
                    if numeric_count == target_numeric:
                        value = f"{m_num.group(1)}%"
                        break

                if nd_re.match(candidate_line) and numeric_count >= target_numeric - 1:
                    value = "ND"
                    break

            seen.add(matched.lower())
            if value == "ND":
                pass  # skip ND compounds
            elif value:
                results.append(f"{matched}: {value}")
            else:
                results.append(matched)

        return results

    def parse(self, lines: list[str]) -> dict[str, Any]:
        compounds = self._extract_compounds(lines)
        if compounds:
            return {"format": self.name, "items": compounds}
        # Fallback: show first 20 lines for diagnosis
        return {"format": self.name, "items": lines[:20] or ["No content extracted from document"]}

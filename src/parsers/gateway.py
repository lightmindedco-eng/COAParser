"""Parser for Gateway-style COA documents."""

from __future__ import annotations

import logging
import re
from typing import Any

from .base import BaseParser

logger = logging.getLogger(__name__)


class GatewayParser(BaseParser):
    name = "gateway"

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
        """Match a line against vocabulary (sorted longest-first) and aliases."""
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
        Extract compound names and percentage values from Gateway Labs COA.

        Gateway Labs has two terpene table formats:
        - v1 (old): Compound -> LOD -> LOQ -> % -> mg/g (3rd numeric)
          The "%" column is already absolute % of sample.
        - v2 (new): Compound -> mg/g -> % -> CAS# -> LOD -> LOQ (2nd numeric)
          The "%" column is relative composition (% of total terpenes).
          We convert to absolute: absolute_% = (relative_% / 100) * total_terpenes_%

        Detection: v2 has "CAS#" in the header near the terpene section.
        """
        number_re = re.compile(r"^(\d+\.?\d*)$")
        nd_re = re.compile(r"^ND$", re.IGNORECASE)
        total_re = re.compile(r"(Total\s+[\w\s-]+?):\s*(\d+\.?\d*)\s*%", re.IGNORECASE)
        rank_prefix_re = re.compile(r"^\d+\s+")

        results: list[str] = []
        seen: set[str] = set()
        all_compounds = sorted(
            self.vocabulary["cannabinoids"] + self.vocabulary["terpenes"],
            key=len, reverse=True,
        )

        # Pass 1a - "Total X: Y %" on a single line
        for line in lines:
            m = total_re.search(line)
            if m:
                label = m.group(1).strip()
                value = m.group(2)
                key = label.lower()
                if key not in seen:
                    seen.add(key)
                    results.append(f"{label}: {value}%")

        # Pass 1b - "Total X" on one line, numeric value on the next line
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

        # Detect if cannabinoid section uses mg/unit with no direct % column
        # e.g., "Cannabinoids by LC-DAD" with mg/unit header and totals in mg/unit
        cannabinoid_uses_mg_unit = False
        total_cannabinoids_mg_unit: float | None = None
        for line in lines:
            m = re.search(r"Total\s+Cannabinoids?:\s*([\d.]+)\s*mg/unit", line, re.IGNORECASE)
            if m:
                total_cannabinoids_mg_unit = float(m.group(1))
                break
        for i, line in enumerate(lines):
            if re.search(r"^cannabinoid", line.lower()):
                for j in range(i, min(i + 15, len(lines))):
                    if "mg/unit" in lines[j].lower():
                        cannabinoid_uses_mg_unit = True
                        break
                break

        # Pass 2 - individual compound rows
        in_terpene_section = False
        terpene_result_index = 3  # default: 3rd numeric = Result %
        terpene_items: list[tuple[str, float]] = []  # collected for post-conversion
        cannabinoid_mg_unit_items: list[tuple[str, float]] = []  # mg/unit values for % calc

        for i, raw_line in enumerate(lines):
            line_normalized = self._normalize_name(raw_line.strip())
            line_lower = line_normalized.lower()

            # Detect section boundaries and determine terpene column order
            if re.search(r"terpene", line_lower) and not re.search(r"^total\s", line_lower):
                if not in_terpene_section:
                    in_terpene_section = True
                    terpene_result_index = 3  # default v1: LOD, LOQ, Result%, mg/g
                    for j in range(1, min(11, len(lines) - i)):
                        if "cas#" in lines[i + j].lower():
                            terpene_result_index = 1  # v2: mg/g=actual %, %=mg/g*10
                            break
            elif re.search(r"cannabinoid", line_lower) and not re.search(r"^total\s", line_lower):
                in_terpene_section = False

            line = rank_prefix_re.sub("", raw_line.strip())

            # Skip headers and totals
            if re.search(r"^total\s", line_lower) or "analyte" in line_lower:
                continue

            # Match against vocabulary (sorted longest-first)
            matched: str | None = self._match_compound(line_lower)

            # If no match, try normalizing Greek letters and matching again
            if matched is None:
                line_norm = self._normalize_name(line).lower()
                matched = self._match_compound(line_norm)

            # Gateway v1 uses spaces in terpene names ("alpha pinene" vs "alpha-Pinene").
            # Try replacing spaces with hyphens in known patterns.
            if matched is None and in_terpene_section:
                space_fixed = re.sub(r"(alpha|beta|gamma|delta)\s+", r"\1-", line_lower)
                matched = self._match_compound(space_fixed)

            if matched is None or matched.lower() in seen:
                continue

            # Collect next 12 lines
            ahead = [lines[i + j].strip() if i + j < len(lines) else "" for j in range(1, 13)]

            value: str | None = None
            if in_terpene_section:
                target_numeric = terpene_result_index
            elif cannabinoid_uses_mg_unit:
                target_numeric = 1  # mg/unit is 1st numeric
            else:
                target_numeric = 3
            position = 0
            for candidate_line in ahead:
                if candidate_line.startswith("<"):
                    position += 1
                    if position == target_numeric:
                        value = "ND"
                        break
                    continue

                m_num = number_re.match(candidate_line)
                if m_num:
                    position += 1
                    if position == target_numeric:
                        value = f"{m_num.group(1)}%"
                        break
                    continue

                if nd_re.match(candidate_line):
                    position += 1
                    if position == target_numeric:
                        value = "ND"
                        break
                    continue

            seen.add(matched.lower())
            if value == "ND":
                pass  # skip ND compounds
            elif value:
                if in_terpene_section:
                    try:
                        val_pct = float(value.rstrip("%"))
                        terpene_items.append((matched, val_pct))
                    except ValueError:
                        logger.debug("Could not parse terpene pct: %s", value)
                elif cannabinoid_uses_mg_unit:
                    try:
                        mg_val = float(value.rstrip("%"))
                        if mg_val >= 0.001:
                            cannabinoid_mg_unit_items.append((matched, mg_val))
                    except ValueError:
                        logger.debug("Could not parse cannabinoid mg/unit: %s", value)
                else:
                    results.append(f"{matched}: {value}")
            else:
                results.append(matched)

        # Post-process terpenes: output % column values verbatim
        for name, val in terpene_items:
            if val >= 0.001:
                results.append(f"{name}: {val:.4g}%")

        # Convert mg/unit cannabinoid values to percentages (preserve mg for display)
        if cannabinoid_uses_mg_unit and total_cannabinoids_mg_unit and total_cannabinoids_mg_unit > 0:
            for name, mg_val in cannabinoid_mg_unit_items:
                pct = (mg_val / total_cannabinoids_mg_unit) * 100
                if pct >= 0.001:
                    results.append(f"{name}: {pct:.4g}% ({mg_val:.4g} mg/unit)")

        # Post-filter: remove compounds with percentage values below 0.001%
        filtered: list[str] = []
        for item in results:
            m = re.search(r":\s*(\d+\.?\d*)%$", item)
            if m:
                pct = float(m.group(1))
                if pct < 0.001:
                    continue
            filtered.append(item)

        return filtered

    def parse(self, lines: list[str]) -> dict[str, Any]:
        compounds = self._extract_compounds(lines)
        if compounds:
            return {"format": self.name, "items": compounds}
        # Fallback: show first 20 lines for diagnosis
        return {"format": self.name, "items": lines[:20] or ["No content extracted from document"]}

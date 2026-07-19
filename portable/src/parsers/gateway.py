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
        
        Gateway Labs tables have: LOD (%) | LOQ (%) | % | mg/g
        So we skip the first 2 numeric values (LOD, LOQ) and take the 3rd (Result %).
        """
        number_re = re.compile(r"^(\d+\.?\d*)$")
        nd_re = re.compile(r"^ND$", re.IGNORECASE)
        total_re = re.compile(r"(Total\s+[\w\s-]+?):\s*(\d+\.?\d*)\s*%", re.IGNORECASE)
        rank_prefix_re = re.compile(r"^\d+\s+")

        results: list[str] = []
        seen: set[str] = set()
        all_compounds = self.vocabulary["cannabinoids"] + self.vocabulary["terpenes"]

        # Pass 1 – clean "Total X: Y %" summary lines (most reliable)
        for line in lines:
            m = total_re.search(line)
            if m:
                label = m.group(1).strip()
                value = m.group(2)
                key = label.lower()
                if key not in seen:
                    seen.add(key)
                    results.append(f"{label}: {value}%")

        # Pass 2 – individual compound rows
        for i, raw_line in enumerate(lines):
            line = rank_prefix_re.sub("", raw_line.strip())
            line_lower = line.lower()

            # Skip headers and totals
            if re.search(r"^total\s", line_lower) or "analyte" in line_lower:
                continue

            # Match against vocabulary
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
            # Gateway Labs: skip first 2 numeric values (LOD%, LOQ%), take the 3rd (Result %)
            numeric_count = 0
            for candidate_line in ahead:
                if nd_re.match(candidate_line):
                    value = "ND"
                    break
                
                m_num = number_re.match(candidate_line)
                if m_num:
                    numeric_count += 1
                    if numeric_count == 3:  # Third numeric value = Result % (after LOD and LOQ)
                        value = f"{m_num.group(1)}%"
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

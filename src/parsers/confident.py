"""Parser for Confident-style COA documents."""

from __future__ import annotations

import re
from typing import Any

from .base import BaseParser


class ConfidentParser(BaseParser):
    name = "confident"

    @staticmethod
    def _normalize_name(name: str) -> str:
        """Normalize compound name by replacing Greek letters with spelled-out versions."""
        normalized = name
        # Handle both uppercase and lowercase Greek letters
        normalized = normalized.replace("Δ", "delta-").replace("δ", "delta-")
        normalized = normalized.replace("α", "alpha-").replace("Α", "alpha-")
        normalized = normalized.replace("β", "beta-").replace("Β", "beta-")
        normalized = normalized.replace("γ", "gamma-").replace("Γ", "gamma-")
        # Remove double hyphens
        for letter in ["delta", "alpha", "beta", "gamma"]:
            normalized = normalized.replace(f"{letter}--", f"{letter}-")
        return normalized

    def _extract_compounds(self, lines: list[str]) -> list[str]:
        """
        Extract compound names and percentage values from Confident/Condent LIMS COA.
        
        Handles both standard and Havard Industries (Condent) formats.
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
            # Normalize Greek letters in the line for matching
            line_normalized = self._normalize_name(line)
            line_lower = line_normalized.lower()

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
            below_loq = False

            # Check current line for <LOQ / <value patterns (e.g., "0.080<0.080")
            if re.search(r"<\s*(?:LOQ|[\d.]+)", line, re.IGNORECASE):
                below_loq = True

            # First, try to extract inline values from the current line (Havard Industries format)
            # Look for all numeric values in the line (space or tab separated)
            inline_values_re = re.compile(r"\d+\.?\d*")
            # Skip inline extraction if line has <LOQ pattern
            inline_matches = [] if below_loq else inline_values_re.findall(line)
            
            # Filter out numbers that are likely part of compound names (e.g., "9" from "Δ9-THC" or "d9-THC")
            # We keep: decimal numbers (with a dot) or multi-digit numbers >= 10
            # This filters out single-digit integers like "9", "8" that appear in compound names
            result_values = []
            for num_str in inline_matches:
                num = float(num_str)
                # Skip single-digit integers (likely part of compound name)
                # but keep 0.00, 0.05, etc. (decimals)
                if "." in num_str or int(float(num_str)) >= 10:
                    # Also filter out mg/g values that might be > 1000
                    if num <= 999.99:
                        # Check if this number is preceded by < in the original line
                        # (e.g., "0.080<0.080" — the second 0.080 is <LOQ)
                        if not re.search(rf"<\s*{re.escape(num_str)}", line):
                            result_values.append(num_str)
            
            # If we have numeric values, use the second one (skip LOQ%, take Result%)
            if len(result_values) >= 2:
                # Skip first numeric value (LOQ%), take second (Result %)
                try:
                    value = f"{result_values[1]}%"
                except (IndexError, ValueError):
                    pass
            elif len(result_values) == 1:
                # Single value - likely Result% with no LOQ or ND
                try:
                    value = f"{result_values[0]}%"
                except (IndexError, ValueError):
                    pass
            
            # If no inline values found, look ahead in next lines (Gateway/other format)
            if value is None:
                numeric_count = 0
                numeric_values = []
                for candidate_line in ahead:
                    if nd_re.match(candidate_line):
                        value = "ND"
                        break
                    # Skip <LOQ / <value patterns
                    if re.match(r"^<(?:LOQ|[\d.]+)", candidate_line, re.IGNORECASE):
                        below_loq = True
                        break
                    
                    m_num = number_re.match(candidate_line)
                    if m_num:
                        numeric_count += 1
                        numeric_values.append(float(m_num.group(1)))
                        
                        # For line-by-line format, we need to distinguish between:
                        # - Havard Industries: LOQ%, Result%, Result_mg/g (take 2nd)
                        # - Gateway: LOD%, LOQ%, Result% (take 3rd)
                        # Heuristic: if we have 3 values and value[2] is ~10x value[1],
                        # then value[1] is the result percentage and value[2] is mg/g
                        if numeric_count >= 3 and len(numeric_values) >= 3:
                            val2 = numeric_values[1]
                            val3 = numeric_values[2]
                            # Check if val3 is approximately 10x val2 (within 15% tolerance)
                            if val2 > 0 and 8.5 < (val3 / val2) < 11.5:
                                # Havard format: use 2nd value (Result%)
                                value = f"{numeric_values[1]}%"
                            else:
                                # Gateway format: use 3rd value (Result%)
                                value = f"{numeric_values[2]}%"
                            break

            seen.add(matched.lower())
            if value == "ND" or below_loq:
                pass  # skip ND / <LOQ compounds
            elif value:
                results.append(f"{matched}: {value}")
            else:
                results.append(matched)

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
        # Fallback: show first 20 lines for diagnosis
        return {"format": self.name, "items": lines[:20] or ["No content extracted from document"]}

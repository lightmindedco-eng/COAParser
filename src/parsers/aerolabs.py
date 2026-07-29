"""Parser for Aerolabs-style COA documents (Condent LIMS format)."""

from __future__ import annotations

import re
from typing import Any

from .base import BaseParser


class AerolabsParser(BaseParser):
    name = "aerolabs"

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
        # Handle OCR misreads of Greek letter prefixes (a→α, b→β, y→γ)
        normalized = re.sub(r'\ba-(?=[A-Za-z])', 'alpha-', normalized, flags=re.IGNORECASE)
        normalized = re.sub(r'\bb-(?=[A-Za-z])', 'beta-', normalized, flags=re.IGNORECASE)
        normalized = re.sub(r'\by-(?=[A-Za-z])', 'gamma-', normalized, flags=re.IGNORECASE)
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
        Extract compound names and percentage values from Condent LIMS COA.

        Condent LIMS format has inline values on the same line:
            THCa 0.16 6.59 65.9
            (Analyte | LOQ% | Mass% | mg/g)

        Multi-word compound names may span two lines:
            Caryophyllene
            Oxide 0.02 0.16 1.6

        Strategy:
        1. Pass 1: Extract "Total X: Y %" summary lines (colon format)
        2. Pass 1b: Extract "Total X" / "Y %" on adjacent lines
        3. Pass 2: Match compound names and extract inline values
           - Check for ND first (ND on line = not detected)
           - If compound found and numbers exist inline, take 2nd numeric (skip LOQ%, take Result%)
           - If compound found but no numbers, check next line for continuation
        """
        number_re = re.compile(r"^(\d+\.?\d*)$")
        nd_re = re.compile(r"^ND$", re.IGNORECASE)
        total_re = re.compile(r"(Total\s+[\w\s-]+?):\s*(\d+\.?\d*)\s*%", re.IGNORECASE)
        inline_values_re = re.compile(r"\d+\.?\d*")

        results: list[str] = []
        seen: set[str] = set()

        # Pass 1 – "Total X: Y %" summary lines (most reliable)
        for line in lines:
            m = total_re.search(line)
            if m:
                label = m.group(1).strip()
                value = m.group(2)
                key = label.lower()
                if key not in seen:
                    seen.add(key)
                    results.append(f"{label}: {value}%")

        # Pass 1b – Value-label or label-value patterns on adjacent lines
        # Aerolabs layout: value THEN label (e.g., "47.12%" / "Total THC")
        # Confident layout: label THEN value (e.g., "Total THC" / "ND" or "25.81%")
        # Detect layout by checking the first "Total X" line found:
        #   - If the line BEFORE it is a percentage → Aerolabs (value-before-label)
        #   - If the line AFTER it is a percentage or ND → Confident (label-before-value)
        pct_re = re.compile(r"^(\d+\.?\d*)\s*%$")
        layout = None  # "value_before" or "value_after"
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            m_total = re.match(r"^Total\s+([\w\s-]+)$", line_stripped, re.IGNORECASE)
            if m_total:
                prev_is_pct = i > 0 and pct_re.match(lines[i - 1].strip())
                next_is_pct = i + 1 < len(lines) and pct_re.match(lines[i + 1].strip())
                if prev_is_pct and not next_is_pct:
                    layout = "value_before"
                elif next_is_pct and not prev_is_pct:
                    layout = "value_after"
                elif prev_is_pct and next_is_pct:
                    # Both sides have percentages — check if prev is Total Cannabinoids-like
                    # In Aerolabs, the value before "Total THC" is the actual Total THC value
                    layout = "value_before"
                break

        if layout is None:
            layout = "value_after"  # default to old behavior

        for i, line in enumerate(lines):
            line_stripped = line.strip()
            m_total = re.match(r"^Total\s+([\w\s-]+)$", line_stripped, re.IGNORECASE)
            if m_total and i + 1 < len(lines):
                label = m_total.group(1).strip()
                key = f"total {label.lower()}"
                if key in seen:
                    continue
                if layout == "value_before":
                    # Aerolabs: value is on the line BEFORE the label
                    if i > 0:
                        prev_line = lines[i - 1].strip()
                        m_val = pct_re.match(prev_line)
                        if m_val:
                            seen.add(key)
                            results.append(f"Total {label}: {m_val.group(1)}%")
                else:
                    # Confident: value is on the line AFTER the label
                    next_line = lines[i + 1].strip()
                    m_val = pct_re.match(next_line)
                    if m_val:
                        seen.add(key)
                        results.append(f"Total {label}: {m_val.group(1)}%")

        # Pass 2 – individual compound rows (inline format)
        # Track column layout per section: some Confident LIMS COAs have LOD before LOQ,
        # pushing Result % to 3rd numeric instead of 2nd.
        result_index = 2  # default: LOQ, Result%, mg/g → 2nd numeric
        mg_unit_mode = False  # True when cannabinoids are reported in mg/unit (no % column)
        mg_unit_items: list[tuple[str, float]] = []  # (name, mg/unit value) for percentage calc
        i = 0
        while i < len(lines):
            raw_line = lines[i].strip()
            line_normalized = self._normalize_name(raw_line)
            line_lower = line_normalized.lower()

            # Detect section headers (cannabinoids, terpenes) and check for LOD column
            if (re.search(r"^cannabinoid", line_lower) or re.search(r"^terpene", line_lower)) and not re.search(r"^total", line_lower):
                result_index = 2  # default
                mg_unit_mode = False
                # Look ahead for header keywords to determine column layout:
                # - "lod" at start → LOD, LOQ, Result%, ... (3rd numeric)
                # - "mg/unit" without "%" → no Result % column, values in mg/unit
                # - "result (%)" appearing before "lod"/"loq" → Result% is 1st numeric
                for j in range(1, min(20, len(lines) - i)):
                    ahead_lower = lines[i + j].strip().lower()
                    if re.match(r"^lod\b", ahead_lower):
                        result_index = 3
                        break
                    if "mg/unit" in ahead_lower and "%" not in ahead_lower:
                        mg_unit_mode = True
                    # HighRes Labs: "Result (%)" before "LOQ" or "LOD" → Result% is 1st
                    if re.match(r"^result\s*\(%\)", ahead_lower):
                        # Check if lod/loq appear AFTER this line
                        for k in range(j + 1, min(j + 5, len(lines) - i)):
                            later = lines[i + k].strip().lower()
                            if re.match(r"^(lod|loq)\b", later):
                                result_index = 1
                                break
                        break
                    # Stop searching once we hit compound data or another section
                    if (self._match_compound(ahead_lower) or re.search(r"^(cannabinoid|terpene)", ahead_lower)) and not re.search(r"^total", ahead_lower):
                        break

            # Skip headers, totals, formulas, and metadata lines
            if (
                not line_lower
                or "analyte" in line_lower
                or "=" in raw_line
                or re.search(r"^total\s", line_lower)
            ):
                i += 1
                continue

            matched = self._match_compound(line_lower)

            # If no match on current line, try joining with next line (multi-word names)
            if matched is None and i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                next_normalized = self._normalize_name(next_line)
                combined = f"{raw_line} {next_line}".lower()
                combined_normalized = self._normalize_name(combined)

                # Join conditions:
                # 1. Next line has numeric data and isn't another compound (existing logic)
                # 2. Current line is a Greek letter prefix (e.g., "β-") — always join
                greek_prefix = re.match(r"^[αβγδ]\s*[-–]?\s*$", raw_line.strip())
                if greek_prefix:
                    joined = f"{raw_line.rstrip('- \t')}-{next_line}".lower()
                    joined_normalized = self._normalize_name(joined)
                    matched = self._match_compound(joined_normalized)
                    if matched is not None:
                        raw_line = joined
                        line_lower = joined_normalized.lower()
                        i += 1
                elif inline_values_re.search(next_line) and not self._match_compound(next_normalized.lower()):
                    matched = self._match_compound(combined_normalized)
                    if matched is not None:
                        raw_line = combined
                        line_lower = combined_normalized.lower()
                        i += 1

            if matched is None or matched.lower() in seen:
                i += 1
                continue

            # Check for ND / <LOQ / NR FIRST — compound has no usable result
            value: str | None = None
            below_loq = False

            # Check current line for ND
            if re.search(r"\bND\b", raw_line, re.IGNORECASE):
                parts = raw_line.split(None, 1)
                if len(parts) > 1 and re.search(r"\bND\b", parts[1], re.IGNORECASE):
                    value = "ND"

            # Look ahead up to 3 lines for ND, <LOQ, <value, or NR patterns
            # (Condent LIMS puts result values on separate lines)
            if value is None:
                for j in range(1, 4):
                    if i + j < len(lines):
                        ahead_line = lines[i + j].strip()
                        if nd_re.match(ahead_line):
                            value = "ND"
                            break
                        if re.match(r"^<(?:LOQ|[\d.]+)", ahead_line, re.IGNORECASE):
                            below_loq = True
                            break
                        if re.match(r"^NR$", ahead_line, re.IGNORECASE):
                            value = "ND"
                            break

            # Extract inline numeric values from the (possibly combined) line
            if value is None and not below_loq:
                # Skip lines that are primarily date patterns (e.g. "3/11/2026")
                is_date_line = re.match(r"^\d{1,2}/\d{1,2}/\d{2,4}", raw_line)
                inline_matches = [] if is_date_line else inline_values_re.findall(raw_line)

                # Filter: keep decimal numbers or multi-digit integers; skip single-digit
                # integers that are likely part of compound names (e.g., "9" from "d9-THC")
                result_values: list[str] = []
                for num_str in inline_matches:
                    num = float(num_str)
                    if "." in num_str or int(num) >= 10:
                        if num <= 999.99:
                            result_values.append(num_str)

                if result_values:
                    # Column layout varies:
                    # - Simple: LOQ%, Result%, mg/g → 2nd value
                    # - With LOD: LOD%, LOQ%, Result%, PPM → 3rd value
                    if len(result_values) >= result_index:
                        value = f"{result_values[result_index - 1]}%"
                    elif len(result_values) == 1:
                        # Single value on line — could be Result% or just the LOQ
                        # with <LOQ/ND on subsequent lines. Check ahead.
                        single_ahead_nd = False
                        single_ahead_loq = False
                        for j in range(1, 7):
                            if i + j < len(lines):
                                ahead_line = lines[i + j].strip()
                                if nd_re.match(ahead_line):
                                    single_ahead_nd = True
                                    break
                                if re.match(r"^<(?:LOQ|[\d.]+)", ahead_line, re.IGNORECASE):
                                    single_ahead_loq = True
                                    break
                        if single_ahead_nd:
                            value = "ND"
                        elif single_ahead_loq:
                            below_loq = True
                        else:
                            value = f"{result_values[0]}%"

            # Fallback: look ahead to next lines for standalone numbers
            if value is None and not below_loq:
                ahead = [lines[i + j].strip() if i + j < len(lines) else "" for j in range(1, 13)]
                numeric_count = 0
                for candidate_line in ahead:
                    if nd_re.match(candidate_line):
                        value = "ND"
                        break
                    if re.match(r"^<(?:LOQ|[\d.]+)", candidate_line, re.IGNORECASE):
                        below_loq = True
                        break
                    if re.match(r"^NR$", candidate_line, re.IGNORECASE):
                        value = "ND"
                        break
                    # Skip date patterns (e.g. "3/11/2026") — they contain numeric-looking values
                    if re.match(r"^\d{1,2}/\d{1,2}/\d{2,4}", candidate_line):
                        continue
                    m_num = number_re.match(candidate_line)
                    if m_num:
                        numeric_count += 1
                        if numeric_count == result_index:
                            value = f"{m_num.group(1)}%"
                            break
                    else:
                        # Handle multi-value lines (e.g. "10.54 1567.03 11.82")
                        inline_nums = inline_values_re.findall(candidate_line)
                        for num_str in inline_nums:
                            num = float(num_str)
                            max_val = 99999.99 if mg_unit_mode else 999.99
                            if "." in num_str or int(num) >= 10:
                                if num <= max_val:
                                    numeric_count += 1
                                    if numeric_count == result_index:
                                        value = f"{num_str}%"
                                        break
                        if value:
                            break

            seen.add(matched.lower())
            if value == "ND" or below_loq:
                pass  # skip ND / <LOQ compounds
            elif value:
                if mg_unit_mode:
                    # In mg/unit mode, value is raw mg/unit — collect for percentage computation
                    try:
                        mg_val = float(value.rstrip("%"))
                        mg_unit_items.append((matched, mg_val))
                    except ValueError:
                        pass
                else:
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

        # If mg/unit mode, compute percentages from collected mg/unit values (preserve mg for display)
        if mg_unit_items:
            total_mg = sum(v for _, v in mg_unit_items)
            if total_mg > 0:
                computed_map: dict[str, str] = {}
                for name, mg_val in mg_unit_items:
                    pct = (mg_val / total_mg) * 100
                    if pct >= 0.01:
                        computed_map[name.lower()] = f"{name}: {pct:.2f}% ({mg_val:.4g} mg/unit)"
                # Merge: computed cannabinoids + existing items (terpenes, totals)
                new_filtered: list[str] = []
                seen_names: set[str] = set()
                for item in filtered:
                    item_name = item.split(":")[0].strip().lower()
                    if item_name in computed_map:
                        new_filtered.append(computed_map[item_name])
                        seen_names.add(item_name)
                    else:
                        new_filtered.append(item)
                # Add any computed cannabinoids not already in filtered
                for name_lower, formatted in computed_map.items():
                    if name_lower not in seen_names:
                        new_filtered.append(formatted)
                filtered = new_filtered

        return filtered

    def parse(self, lines: list[str]) -> dict[str, Any]:
        compounds = self._extract_compounds(lines)
        if compounds:
            return {"format": self.name, "items": compounds}
        # Fallback: show first 20 lines for diagnosis
        return {"format": self.name, "items": lines[:20] or ["No content extracted from document"]}

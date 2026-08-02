"""Parser for Confident-style COA documents (Confident LIMS / Havard Industries)."""
from __future__ import annotations

import logging
import re
from typing import Any

from .base import BaseParser

logger = logging.getLogger(__name__)


class ConfidentParser(BaseParser):
    name = "confident"

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
        normalized = re.sub(r'\ba-(?=[A-Za-z])', 'alpha-', normalized, flags=re.IGNORECASE)
        normalized = re.sub(r'\bb-(?=[A-Za-z])', 'beta-', normalized, flags=re.IGNORECASE)
        normalized = re.sub(r'\by-(?=[A-Za-z])', 'gamma-', normalized, flags=re.IGNORECASE)
        return normalized

    def _match_compound(self, line_lower: str) -> str | None:
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
        number_re = re.compile(r"^(\d+\.?\d*)$")
        nd_re = re.compile(r"^ND$", re.IGNORECASE)
        total_re = re.compile(r"(Total\s+[\w\s-]+?):\s*(\d+\.?\d*)\s*%", re.IGNORECASE)
        inline_values_re = re.compile(r"\d+\.?\d*")

        results: list[str] = []
        seen: set[str] = set()

        # Pass 1 – "Total X: Y %" summary lines
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
        pct_re = re.compile(r"^(\d+\.?\d*)\s*%$")
        mg_unit_re = re.compile(r"^(\d+\.?\d*)\s*(?:mg/unit|mg/g)$", re.IGNORECASE)
        skip_re = re.compile(r"^(pass|fail|mu range|not tested|nd|nr|<loq|safe|pesticide|microbial|mycotoxin|solvent|metal|foreign)", re.IGNORECASE)
        layout = None
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            m_total = re.match(r"^Total\s+([\w\s-]+)$", line_stripped, re.IGNORECASE)
            if m_total:
                prev_is_val = False
                for back in range(1, min(i + 1, 6)):
                    candidate = lines[i - back].strip()
                    if pct_re.match(candidate) or mg_unit_re.match(candidate):
                        prev_is_val = True
                        break
                    if not skip_re.match(candidate):
                        break
                next_line = lines[i + 1].strip() if i + 1 < len(lines) else ""
                next_is_val = bool(pct_re.match(next_line) or mg_unit_re.match(next_line))
                if prev_is_val and not next_is_val:
                    layout = "value_before"
                elif next_is_val and not prev_is_val:
                    layout = "value_after"
                elif prev_is_val and next_is_val:
                    layout = "value_before"
                break

        if layout is None:
            layout = "value_after"

        def _extract_total_value(line: str) -> str | None:
            m = pct_re.match(line)
            if m:
                return f"{m.group(1)}%"
            m = mg_unit_re.match(line)
            if m:
                unit = "mg/unit" if "mg/unit" in line.lower() else "mg/g"
                return f"{m.group(1)} {unit}"
            return None

        for i, line in enumerate(lines):
            line_stripped = line.strip()
            m_total = re.match(r"^Total\s+([\w\s-]+)$", line_stripped, re.IGNORECASE)
            if m_total and i + 1 < len(lines):
                label = m_total.group(1).strip()
                key = f"total {label.lower()}"
                if key in seen:
                    continue
                if layout == "value_before":
                    for back in range(1, min(i + 1, 6)):
                        prev_line = lines[i - back].strip()
                        total_val = _extract_total_value(prev_line)
                        if total_val:
                            seen.add(key)
                            results.append(f"Total {label}: {total_val}")
                            break
                        if not skip_re.match(prev_line):
                            break
                else:
                    next_line = lines[i + 1].strip()
                    total_val = _extract_total_value(next_line)
                    if total_val:
                        seen.add(key)
                        results.append(f"Total {label}: {total_val}")

        # Pass 2 – individual compound rows
        result_index = 2
        mg_unit_mode = False
        mg_unit_items: list[tuple[str, float]] = []
        _mg_unit_str = "mg/unit"
        _section_type = None
        _first_section_entered = False
        _ppm_mode = False
        _4col_mode = False

        i = 0
        while i < len(lines):
            raw_line = lines[i].strip()
            line_normalized = self._normalize_name(raw_line)
            line_lower = line_normalized.lower()

            # Detect section headers and check column layout
            if (re.search(r"^cannabinoid", line_lower) or re.search(r"^terpene", line_lower)) and not re.search(r"^total", line_lower):
                is_terpene = bool(re.search(r"^terpene", line_lower))
                _section_type = "terpenes" if is_terpene else "cannabinoids"
                result_index = 2
                mg_unit_mode = False
                _ppm_mode = False
                _4col_mode = False
                # On the very first data-section entry, clear seen and trim results
                # to only totals (removes false positives from product-name lines).
                # Do NOT repeat this on subsequent section entries or transitions
                # so that compounds already extracted are preserved.
                if not _first_section_entered:
                    _first_section_entered = True
                    seen.clear()
                    results[:] = [r for r in results if r.startswith("Total ")]
                else:
                    # Section-to-section transition: only reset seen; keep results
                    seen.clear()
                found_ppm = False
                _saw_pct_header = False
                _has_mass_column = False
                _mg_g_col = False
                _has_pct_col = False
                _has_mg_unit_col = False
                for j in range(1, min(20, len(lines) - i)):
                    ahead_lower = lines[i + j].strip().lower()
                    if re.match(r"^lod\b", ahead_lower) or re.search(r"(?<!\w)lod(?!\w)", ahead_lower):
                        result_index = 3
                        _4col_mode = True
                    if re.match(r"^(loq|reporting)\b", ahead_lower):
                        # LOQ / Reporting Limit is the first data column; Mass% stays at index 2
                        pass
                    if "mg/unit" in ahead_lower and "%" not in ahead_lower:
                        mg_unit_mode = True
                    if "mg/unit" in ahead_lower:
                        _has_mg_unit_col = True
                    if "%" in ahead_lower or re.search(r"\bmass\b", ahead_lower):
                        _saw_pct_header = True
                    # A genuine "%" column header (a bare % or "Result (%)" token, not a
                    # value line like "81.179%"). When present the rows carry real
                    # percentages, so the mass-relative mg_unit_mode must not apply.
                    if "%" in ahead_lower and not re.search(r"\d", ahead_lower):
                        _has_pct_col = True
                    if is_terpene and "ppm" in ahead_lower:
                        found_ppm = True
                    if re.search(r"\bmg/g\b", ahead_lower):
                        # 'Result %' and 'Result mg/g' columns. The mg/g column is
                        # always the LAST numeric; the % column sits immediately
                        # before it, so the % value is the second-to-last numeric
                        # of each row (see row parsing below). With an LOD column
                        # the leading count is fixed (3), so front-indexing applies.
                        if _has_pct_col and result_index != 3:
                            _mg_g_col = True
                        elif not _has_pct_col:
                            _has_mass_column = True
                    if ahead_lower == "mass":
                        _has_mass_column = True
                    if re.match(r"^result\s*\(%\)", ahead_lower):
                        for k in range(j + 1, min(j + 5, len(lines) - i)):
                            later = lines[i + k].strip().lower()
                            if re.match(r"^(lod|loq|reporting)\b", later):
                                result_index = 1
                                break
                        break
                    if (self._match_compound(ahead_lower) or re.search(r"^(cannabinoid|terpene)", ahead_lower)) and not re.search(r"^total", ahead_lower):
                        break
                # PPM mode: terpene section has "ppm" in header but no "%" or "mass" column
                if _saw_pct_header and found_ppm and result_index == 1:
                    # "Result (%)" was found first, then LOQ; Mass% is at index 1
                    pass
                if is_terpene and found_ppm and not _saw_pct_header:
                    _ppm_mode = True
                # Only compute mass-relative percentages when the section has NO
                # genuine "%" column. With a real % column the row values are
                # already percentages and mg_unit_mode would recompute them wrong.
                if _has_pct_col:
                    mg_unit_mode = False
                elif _has_mg_unit_col:
                    mg_unit_mode = True
                    _mg_unit_str = "mg/unit"
                elif _has_mass_column:
                    mg_unit_mode = True
                    _mg_unit_str = "mg/g"

            # Detect end of cannabinoid/terpene data sections: when a different
            # test section starts (pesticides, solvents, etc.), stop matching.
            # Clear section type and seen, but DO NOT touch results – the
            # compounds already extracted from this section are valid.
            if _section_type and re.search(r"^(pesticide|residual\s+solvent|microbial|mycotoxin|heavy\s+metal|moisture|water\s+activity|foreign\s+matter|amendment)", line_lower):
                # Moisture/Water-Activity can appear as summary rows WITHIN a
                # cannabinoid section, not only as section boundaries.  Peek
                # ahead; if a compound table (Analyte + LOQ) follows, keep
                # the section active so the table rows get extracted.
                if line_lower.startswith("moisture") or line_lower.startswith("water activity"):
                    for peek in range(1, 8):
                        if i + peek >= len(lines):
                            break
                        peek_line = lines[i + peek].strip().lower()
                        if "analyte" in peek_line:
                            break
                        if self._match_compound(peek_line) and not re.search(r"^total\s", peek_line):
                            break
                    else:
                        _section_type = None
                        seen.clear()
                        i += 1
                        continue
                else:
                    _section_type = None
                    seen.clear()
                    i += 1
                    continue

            if (
                not line_lower
                or "analyte" in line_lower
                or "=" in raw_line
                or re.search(r"^total\s", line_lower)
            ):
                i += 1
                continue

            # Only match compounds inside cannabinoid/terpene data sections
            if not _section_type:
                i += 1
                continue

            matched = self._match_compound(line_lower)

            if matched is None and i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                next_normalized = self._normalize_name(next_line)
                combined = f"{raw_line} {next_line}".lower()
                combined_normalized = self._normalize_name(combined)

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

            value: str | None = None
            below_loq = False

            if re.search(r"\bND\b", raw_line, re.IGNORECASE):
                parts = raw_line.split(None, 1)
                if len(parts) > 1 and re.search(r"\bND\b", parts[1], re.IGNORECASE):
                    value = "ND"

            if value is None:
                if re.search(r">ULOQ", raw_line, re.IGNORECASE):
                    value = "ND"
                elif re.search(r"<\s*(?:LOQ|[\d.]+)", raw_line, re.IGNORECASE):
                    below_loq = True

            if value is None and not below_loq:
                for j in range(1, 4):
                    if i + j < len(lines):
                        ahead_line = lines[i + j].strip()
                        if nd_re.match(ahead_line):
                            value = "ND"
                            break
                        if re.search(r"<\s*(?:LOQ|[\d.]+)", ahead_line, re.IGNORECASE):
                            below_loq = True
                            break
                        if re.match(r"^NR$", ahead_line, re.IGNORECASE):
                            value = "ND"
                            break

            if value is None and not below_loq:
                is_date_line = re.search(r"\d{1,2}/\d{1,2}/\d{2,4}", raw_line)
                inline_matches = [] if is_date_line else inline_values_re.findall(raw_line)

                result_values: list[str] = []
                _inline_max = 99999.99 if (_ppm_mode or _section_type == "terpenes" or _4col_mode) else 999.99
                for num_str in inline_matches:
                    num = float(num_str)
                    if "." in num_str or int(num) >= 10:
                        if num <= _inline_max:
                            if not re.search(rf"<\s*{re.escape(num_str)}", raw_line):
                                result_values.append(num_str)

                if result_values:
                    if _mg_g_col and len(result_values) >= 2:
                        # [%, mg/g] rows have 2 numerics; [LOQ, %, mg/g] rows have 3+
                        idx = 1 if len(result_values) >= 3 else 0
                        value = f"{result_values[idx]}%"
                    elif len(result_values) >= result_index:
                        value = f"{result_values[result_index - 1]}%"
                    elif len(result_values) == 1:
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

            if value is None and not below_loq:
                # Multi-line look-ahead: scan following lines for numeric values.
                # With an mg/g column the % is the second-to-last numeric of the
                # row, so collect every numeric until the row ends. Otherwise use
                # result_index to pick the correct column. Stop at next compound.
                ahead = [lines[i + j].strip() if i + j < len(lines) else "" for j in range(1, 13)]
                numeric_count = 0
                got_value = False
                row_nums: list[str] = []
                for candidate_line in ahead:
                    if nd_re.match(candidate_line):
                        value = "ND"
                        got_value = True
                        break
                    if re.search(r"<\s*(?:LOQ|[\d.]+)", candidate_line, re.IGNORECASE):
                        below_loq = True
                        got_value = True
                        break
                    if re.match(r"^NR$", candidate_line, re.IGNORECASE):
                        value = "ND"
                        got_value = True
                        break
                    if re.search(r"\d{1,2}/\d{1,2}/\d{2,4}", candidate_line):
                        continue
                    # Stop at Total lines — they mark end of section data
                    if re.match(r"^total\b", candidate_line.strip(), re.IGNORECASE):
                        break
                    # Stop at next compound name (different from current)
                    candidate_normalized = self._normalize_name(candidate_line)
                    candidate_lower = candidate_normalized.lower()
                    if candidate_lower != line_lower and self._match_compound(candidate_lower):
                        break
                    m_num = number_re.match(candidate_line)
                    if m_num:
                        numeric_count += 1
                        row_nums.append(m_num.group(1))
                        if not _mg_g_col and numeric_count == result_index:
                            value = f"{m_num.group(1)}%"
                            got_value = True
                            break
                    else:
                        inline_nums = inline_values_re.findall(candidate_line)
                        for num_str in inline_nums:
                            num = float(num_str)
                            max_val = 99999.99 if (mg_unit_mode or _ppm_mode or _section_type == "terpenes" or _4col_mode) else 999.99
                            if "." in num_str or int(num) >= 10:
                                if num <= max_val:
                                    numeric_count += 1
                                    row_nums.append(num_str)
                                    if not _mg_g_col and numeric_count == result_index:
                                        value = f"{num_str}%"
                                        got_value = True
                                        break
                        if got_value:
                            break
                if _mg_g_col and not got_value and len(row_nums) >= 2:
                    # [%, mg/g] rows have 2 numerics; [LOQ, %, mg/g] rows have 3+.
                    # Front-indexing is robust when unrecognized intermediate
                    # compounds merge their numbers into this row.
                    idx = 1 if len(row_nums) >= 3 else 0
                    value = f"{row_nums[idx]}%"

            seen.add(matched.lower())
            if value == "ND" or below_loq:
                pass
            elif value:
                # Value-based PPM conversion: if terpene value > 100%, it's likely ppm
                if _section_type == "terpenes" and value.endswith("%"):
                    try:
                        v = float(value.rstrip("%"))
                        if v > 100:
                            value = f"{v / 10000:.4f}%"
                    except ValueError:
                        pass
                if mg_unit_mode:
                    try:
                        mg_val = float(value.rstrip("%"))
                        mg_unit_items.append((matched, mg_val))
                    except ValueError:
                        logger.debug("Could not parse mg value: %s", value)
                else:
                    results.append(f"{matched}: {value}")
            else:
                results.append(matched)

            i += 1

        # Value-based PPM conversion for terpene totals (>100% is ppm)
        for idx, item in enumerate(results):
            m_ppm = re.match(r"^(Total\s+(?:[Tt]erpenes|[Tt]erpenoids?)):\s*([\d.eE+\-]+)%$", item)
            if m_ppm:
                try:
                    val = float(m_ppm.group(2))
                    if val > 100:
                        results[idx] = f"{m_ppm.group(1)}: {val / 10000:.4f}%"
                except ValueError:
                    pass

        # Post-filter: remove compounds with percentage values below 0.01%
        filtered: list[str] = []
        for item in results:
            m = re.search(r":\s*(\d+\.?\d*)%$", item)
            if m:
                pct = float(m.group(1))
                if pct < 0.01:
                    continue
            filtered.append(item)

        if mg_unit_items:
            total_mg = sum(v for _, v in mg_unit_items)
            if total_mg > 0:
                computed_map: dict[str, str] = {}
                for name, mg_val in mg_unit_items:
                    pct = (mg_val / total_mg) * 100
                    if pct >= 0.01:
                        computed_map[name.lower()] = f"{name}: {pct:.2f}% ({mg_val:.4g} {_mg_unit_str})"
                new_filtered: list[str] = []
                seen_names: set[str] = set()
                for item in filtered:
                    item_name = item.split(":")[0].strip().lower()
                    if item_name in computed_map:
                        new_filtered.append(computed_map[item_name])
                        seen_names.add(item_name)
                    else:
                        new_filtered.append(item)
                for name_lower, formatted in computed_map.items():
                    if name_lower not in seen_names:
                        new_filtered.append(formatted)
                filtered = new_filtered

        return filtered

    def parse(self, lines: list[str]) -> dict[str, Any]:
        compounds = self._extract_compounds(lines)
        if compounds:
            return {"format": self.name, "items": compounds}
        return {"format": self.name, "items": lines[:20] or ["No content extracted from document"]}

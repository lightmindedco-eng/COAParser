"""Parser for Confident-style COA documents (Confident LIMS / Havard Industries)."""

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
        skip_re = re.compile(r"^(pass|fail|mu range|not tested|nd|nr|<loq|safe|pesticide|microbial|mycotoxin|solvent|metal|foreign)", re.IGNORECASE)
        layout = None
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            m_total = re.match(r"^Total\s+([\w\s-]+)$", line_stripped, re.IGNORECASE)
            if m_total:
                prev_is_pct = False
                for back in range(1, min(i + 1, 6)):
                    candidate = lines[i - back].strip()
                    if pct_re.match(candidate):
                        prev_is_pct = True
                        break
                    if not skip_re.match(candidate):
                        break
                next_is_pct = i + 1 < len(lines) and pct_re.match(lines[i + 1].strip())
                if prev_is_pct and not next_is_pct:
                    layout = "value_before"
                elif next_is_pct and not prev_is_pct:
                    layout = "value_after"
                elif prev_is_pct and next_is_pct:
                    layout = "value_before"
                break

        if layout is None:
            layout = "value_after"

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
                        m_val = pct_re.match(prev_line)
                        if m_val:
                            seen.add(key)
                            results.append(f"Total {label}: {m_val.group(1)}%")
                            break
                        if not skip_re.match(prev_line):
                            break
                else:
                    next_line = lines[i + 1].strip()
                    m_val = pct_re.match(next_line)
                    if m_val:
                        seen.add(key)
                        results.append(f"Total {label}: {m_val.group(1)}%")

        # Pass 2 – individual compound rows
        result_index = 2
        mg_unit_mode = False
        mg_unit_items: list[tuple[str, float]] = []
        _section_type = None

        i = 0
        while i < len(lines):
            raw_line = lines[i].strip()
            line_normalized = self._normalize_name(raw_line)
            line_lower = line_normalized.lower()

            # Detect section headers and check for PPM column layout
            if (re.search(r"^cannabinoid", line_lower) or re.search(r"^terpene", line_lower)) and not re.search(r"^total", line_lower):
                is_terpene = bool(re.search(r"^terpene", line_lower))
                _section_type = "terpenes" if is_terpene else "cannabinoids"
                result_index = 2
                mg_unit_mode = False
                found_ppm = False
                for j in range(1, min(20, len(lines) - i)):
                    ahead_lower = lines[i + j].strip().lower()
                    if re.match(r"^lod\b", ahead_lower):
                        result_index = 3
                        break
                    if "mg/unit" in ahead_lower and "%" not in ahead_lower:
                        mg_unit_mode = True
                    if is_terpene and "ppm" in ahead_lower:
                        found_ppm = True
                    if re.match(r"^result\s*\(%\)", ahead_lower):
                        for k in range(j + 1, min(j + 5, len(lines) - i)):
                            later = lines[i + k].strip().lower()
                            if re.match(r"^(lod|loq)\b", later):
                                result_index = 1
                                break
                        break
                    if (self._match_compound(ahead_lower) or re.search(r"^(cannabinoid|terpene)", ahead_lower)) and not re.search(r"^total", ahead_lower):
                        break

            if (
                not line_lower
                or "analyte" in line_lower
                or "=" in raw_line
                or re.search(r"^total\s", line_lower)
            ):
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
                        if re.match(r"^<(?:LOQ|[\d.]+)", ahead_line, re.IGNORECASE):
                            below_loq = True
                            break
                        if re.match(r"^NR$", ahead_line, re.IGNORECASE):
                            value = "ND"
                            break

            if value is None and not below_loq:
                is_date_line = re.match(r"^\d{1,2}/\d{1,2}/\d{2,4}", raw_line)
                inline_matches = [] if is_date_line else inline_values_re.findall(raw_line)

                result_values: list[str] = []
                for num_str in inline_matches:
                    num = float(num_str)
                    if "." in num_str or int(num) >= 10:
                        if num <= 999.99:
                            if not re.search(rf"<\s*{re.escape(num_str)}", raw_line):
                                result_values.append(num_str)

                if result_values:
                    if len(result_values) >= result_index:
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
                ahead = [lines[i + j].strip() if i + j < len(lines) else "" for j in range(1, 13)]
                numeric_count = 0
                numeric_values: list[float] = []
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
                    if re.match(r"^\d{1,2}/\d{1,2}/\d{2,4}", candidate_line):
                        continue
                    m_num = number_re.match(candidate_line)
                    if m_num:
                        numeric_count += 1
                        numeric_values.append(float(m_num.group(1)))
                        if numeric_count >= 3 and len(numeric_values) >= 3:
                            val2 = numeric_values[1]
                            val3 = numeric_values[2]
                            if val2 > 0 and 8.5 < (val3 / val2) < 11.5:
                                value = f"{numeric_values[1]}%"
                            elif val2 > 0 and (val3 / val2) > 100:
                                value = f"{numeric_values[1]}%"
                            else:
                                value = f"{numeric_values[2]}%"
                            break
                    else:
                        inline_nums = inline_values_re.findall(candidate_line)
                        for num_str in inline_nums:
                            num = float(num_str)
                            max_val = 99999.99 if mg_unit_mode else 999.99
                            if "." in num_str or int(num) >= 10:
                                if num <= max_val:
                                    numeric_count += 1
                                    numeric_values.append(num)
                                    if numeric_count >= 3 and len(numeric_values) >= 3:
                                        val2 = numeric_values[1]
                                        val3 = numeric_values[2]
                                        if val2 > 0 and 8.5 < (val3 / val2) < 11.5:
                                            value = f"{numeric_values[1]}%"
                                        elif val2 > 0 and (val3 / val2) > 100:
                                            value = f"{numeric_values[1]}%"
                                        else:
                                            value = f"{numeric_values[2]}%"
                                        break
                        if value:
                            break

            seen.add(matched.lower())
            if value == "ND" or below_loq:
                pass
            elif value:
                if mg_unit_mode:
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

        if mg_unit_items:
            total_mg = sum(v for _, v in mg_unit_items)
            if total_mg > 0:
                computed_map: dict[str, str] = {}
                for name, mg_val in mg_unit_items:
                    pct = (mg_val / total_mg) * 100
                    if pct >= 0.01:
                        computed_map[name.lower()] = f"{name}: {pct:.2f}% ({mg_val:.4g} mg/unit)"
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

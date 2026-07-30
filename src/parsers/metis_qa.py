"""Parser for Metis QA Laboratory COA documents."""

from __future__ import annotations

import re
from typing import Any

from .base import BaseParser


class MetisQAParser(BaseParser):
    name = "metis_qa"

    @staticmethod
    def _normalize_name(name: str) -> str:
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
        normalized = re.sub(r'\?(\d)', r'd\1', normalized)
        normalized = re.sub(r'\b[d](?=\d)', 'delta-', normalized, flags=re.IGNORECASE)
        # Remove spaces after trailing hyphens (e.g., "trans-beta- farnesene" -> "trans-beta-farnesene")
        normalized = re.sub(r'-\s+', '-', normalized)
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
        edible_mode = False

        # Pre-scan for edible indicators: "mg/unit" in column headers or "= Xg" product info
        for line in lines:
            lowered = line.lower()
            if "mg/unit" in lowered:
                edible_mode = True
                break

        # Pass 1 – standalone "Total:" summary lines
        for i, line in enumerate(lines):
            m = total_re.search(line)
            if m:
                label = m.group(1).strip()
                value = m.group(2)
                key = label.lower()
                if key not in seen:
                    seen.add(key)
                    results.append(f"{label}: {value}%")

        # Also detect "Total" label on adjacent lines (Metis QA format)
        # e.g., "Total THC" / "24.46%" or "Total" / "28.87" / "288.7"
        _section_for_total = None
        for i, line in enumerate(lines):
            stripped = line.strip()
            line_lower = stripped.lower()
            # Track section for standalone "Total" lines
            if re.search(r"^cannabinoid", line_lower) and "complete" not in line_lower:
                _section_for_total = "cannabinoids"
            if re.search(r"^terpene", line_lower) and "complete" not in line_lower:
                _section_for_total = "terpenes"
            m_total = re.match(r"^Total\s+(.+)$", stripped, re.IGNORECASE)
            if m_total:
                label = m_total.group(1).strip()
                key = f"total {label.lower()}"
                if key in seen:
                    continue
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    m_val = number_re.match(next_line)
                    if m_val:
                        seen.add(key)
                        results.append(f"Total {label}: {m_val.group(1)}%")
            # Value-before-label: "X mg/unit" followed by "Total Y"
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                m_next_total = re.match(r"^Total\s+(.+)$", next_line, re.IGNORECASE)
                if m_next_total:
                    m_pre_val = re.match(r"^([\d.]+)\s*mg/unit", stripped, re.IGNORECASE)
                    if m_pre_val:
                        label = m_next_total.group(1).strip()
                        key = f"total {label.lower()}"
                        if key not in seen:
                            seen.add(key)
                            results.append(f"Total {label}: {m_pre_val.group(1)} mg/unit")

            # "Total" on its own line (value before on same line as "Total")
            if stripped.lower() == "total" and i + 2 < len(lines):
                if _section_for_total == "terpenes":
                    key = "total terpenes"
                else:
                    key = "total cannabinoids"
                if key in seen:
                    continue
                val1 = lines[i + 1].strip()
                val2 = lines[i + 2].strip()
                m1 = number_re.match(val1)
                if m1 and not nd_re.match(val2):
                    seen.add(key)
                    if _section_for_total == "terpenes":
                        results.append(f"Total Terpenes: {val2}%")
                    else:
                        suffix = " mg/unit" if edible_mode else "%"
                        results.append(f"Total Cannabinoids: {m1.group(1)}{suffix}")

        # Pass 2 – individual compound rows
        section = None  # "cannabinoids" or "terpenes"
        result_index = 2  # default for cannabinoids columns: LOQ, Result%, mg/g
        i = 0
        while i < len(lines):
            raw_line = lines[i].strip()
            line_normalized = self._normalize_name(raw_line)
            line_lower = line_normalized.lower()

            # Detect section headers
            if re.search(r"^cannabinoid", line_lower) and "complete" not in line_lower:
                section = "cannabinoids"
                # Edible layout: LOQ, mg/unit, % → % at index 3
                # Standard layout: LOQ, %, mg/g → % at index 2
                result_index = 3 if edible_mode else 2
                i += 1
                continue
            if re.search(r"^terpene", line_lower) and "complete" not in line_lower:
                section = "terpenes"
                # Both layouts: LOQ, mg/g (or mg/unit), % → % at index 3
                result_index = 3
                i += 1
                continue

            # Skip headers, totals, pass/fail lines
            if (not raw_line or "analyte" in line_lower or "=" in raw_line
                    or re.search(r"^total\s", line_lower) or line_lower in ("complete", "pass")):
                i += 1
                continue

            # Detect edible mode (e.g., "1 Unit = 3.27g")
            if "unit" in line_lower and "=" in raw_line and "g" in raw_line:
                edible_mode = True
                i += 1
                continue

            if section is None:
                i += 1
                continue

            matched = self._match_compound(line_lower)

            # Try joining with next line for multi-word names
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                # Don't join if current line is a pure number (it's a value, not a compound name)
                if not re.match(r'^\d+\.?\d*%?$', raw_line):
                    # Never join if the next line starts with "Total" (keep it as a label)
                    if not re.search(r"^total\s", next_line, re.IGNORECASE):
                        next_normalized = self._normalize_name(next_line)
                        combined = f"{raw_line} {next_line}".lower()
                        combined_normalized = self._normalize_name(combined)
                        if matched is not None and not inline_values_re.search(next_line):
                            combined_match = self._match_compound(combined_normalized)
                            if combined_match and len(combined_match) > len(matched):
                                matched = combined_match
                                raw_line = combined
                                line_lower = combined_normalized.lower()
                                i += 1
                        elif matched is None and (inline_values_re.search(next_line) or self._match_compound(combined_normalized)):
                            combined_match = self._match_compound(combined_normalized)
                            next_match = self._match_compound(next_normalized.lower())
                            if combined_match and combined_match != next_match:
                                matched = combined_match
                                raw_line = combined
                                line_lower = combined_normalized.lower()
                                i += 1

            if matched and len(raw_line) > len(matched) * 2:
                matched = None

            if matched is None or matched.lower() in seen:
                i += 1
                continue

            # Check for ND / <LOQ / NR
            value: str | None = None
            below_loq = False
            if re.search(r"\bND\b", raw_line, re.IGNORECASE):
                parts = raw_line.split(None, 1)
                if len(parts) > 1 and re.search(r"\bND\b", parts[1], re.IGNORECASE):
                    value = "ND"
            if value is None:
                if re.search(r"<\s*(?:LOQ|[\d.]+)", raw_line, re.IGNORECASE):
                    below_loq = True

            # Look ahead up to 3 lines for ND / <LOQ / NR
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

            # Extract inline values from current line (Metis QA puts LOQ/Result/mg/g on separate lines)
            if value is None and not below_loq:
                is_date_line = re.search(r"\d{1,2}/\d{1,2}/\d{2,4}", raw_line)
                inline_matches = [] if is_date_line else inline_values_re.findall(raw_line)
                result_values: list[str] = []
                for num_str in inline_matches:
                    num = float(num_str)
                    if "." in num_str or int(num) >= 10:
                        if num <= 999.99:
                            result_values.append(num_str)

                # Look ahead for standalone numeric values (Metis QA puts each value on its own line)
                if section == "terpenes" and not raw_line:
                    i += 1
                    continue
                ahead = [lines[i + j].strip() if i + j < len(lines) else "" for j in range(1, 13)]
                numeric_values: list[str] = []
                need_count = result_index + 1
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
                    if re.search(r"\d{1,2}/\d{1,2}/\d{2,4}", candidate_line):
                        continue
                    m_num = number_re.match(candidate_line)
                    if m_num:
                        numeric_values.append(m_num.group(1))
                        if len(numeric_values) >= need_count:
                            break
                    else:
                        inline_nums = inline_values_re.findall(candidate_line)
                        for num_str in inline_nums:
                            num = float(num_str)
                            if "." in num_str or int(num) >= 10:
                                if num <= 999.99:
                                    numeric_values.append(num_str)
                                    if len(numeric_values) >= need_count:
                                        break
                        if len(numeric_values) >= need_count:
                            break
                    if value:
                        break

            # Extract % and mg/g (or mg/unit) from collected numeric values
            if value is None and not below_loq and numeric_values:
                unit_label = "mg/unit" if edible_mode else "mg/g"
                if len(numeric_values) >= result_index:
                    pct = numeric_values[result_index - 1]
                    mg_val = None
                    if edible_mode:
                        # Edible layout: LOQ, mg/unit, mg/g — no % column
                        if len(numeric_values) >= 2:
                            mg_val = numeric_values[1]
                    elif section == "cannabinoids":
                        # Standard layout: LOQ, %, mg/g → mg/g at index result_index (= 2)
                        if len(numeric_values) >= result_index + 1:
                            mg_val = numeric_values[result_index]
                    else:  # terpenes
                        # Standard layout: LOQ, mg/g, % → mg/g at index 1
                        if len(numeric_values) >= 2:
                            mg_val = numeric_values[1]
                    if edible_mode:
                        if mg_val is not None and float(mg_val) < 99999:
                            mg_g = numeric_values[result_index - 1] if len(numeric_values) >= result_index else None
                            if mg_g is not None and float(mg_g) < 99999:
                                value = f"{mg_val} {unit_label} ({mg_g} mg/g)"
                            else:
                                value = f"{mg_val} {unit_label}"
                    elif mg_val is not None and float(mg_val) < 99999:
                        value = f"{pct}% ({mg_val} {unit_label})"
                    else:
                        value = f"{pct}%"

            seen.add(matched.lower())
            if value == "ND" or below_loq:
                pass
            elif value:
                results.append(f"{matched}: {value}")
            else:
                results.append(matched)

            i += 1

        # Post-filter
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

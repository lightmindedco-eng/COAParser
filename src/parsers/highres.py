"""Parser for HighRes Labs COA documents."""

from __future__ import annotations

import re
from typing import Any

from .base import BaseParser


class HighresParser(BaseParser):
    name = "highres"

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

        # Pass 1: total summary lines
        for line in lines:
            m = total_re.search(line)
            if m:
                label = m.group(1).strip()
                value = m.group(2)
                key = label.lower()
                if key not in seen:
                    seen.add(key)
                    results.append(f"{label}: {value}%")

        # Pass 1b: HighRes totals on adjacent lines (e.g., "Total THC" / "35.78")
        # HighRes puts total values on separate lines:
        #   Total THC: Result%(1st) | mg/g(2nd) | LOQ(3rd)
        #   Total Terpenes: mg/g(1st) | Result%(2nd) | LOQ(3rd)
        for i, line in enumerate(lines):
            stripped = line.strip()
            m_total = re.match(r"^Total\s+(.+)$", stripped, re.IGNORECASE)
            if m_total:
                label = m_total.group(1).strip()
                key = f"total {label.lower()}"
                if key in seen:
                    continue
                # Look ahead for the first 2 numeric values
                values: list[str] = []
                for j in range(1, 6):
                    if i + j >= len(lines):
                        break
                    ahead = lines[i + j].strip()
                    if number_re.match(ahead):
                        values.append(ahead)
                        if len(values) >= 2:
                            break
                    if ahead == "-":
                        continue
                    if not number_re.match(ahead) and ahead:
                        break
                if len(values) >= 2:
                    v0, v1 = float(values[0]), float(values[1])
                    if v0 > 0:
                        ratio = v1 / v0
                        if 8 < ratio < 12:
                            pct_val = values[0]  # cannabinoid: 1st is %
                        elif 0.08 < ratio < 0.12:
                            pct_val = values[1]  # terpene: 2nd is %
                        else:
                            pct_val = values[0]
                        seen.add(key)
                        results.append(f"Total {label}: {pct_val}%")
                elif len(values) == 1:
                    seen.add(key)
                    results.append(f"Total {label}: {values[0]}%")

        # Pass 2: compound extraction with ratio-based layout detection
        # HighRes values are on separate lines after the compound name:
        #   Cannabinoids: Result% (1st), mg/g (2nd, ~10x 1st), LOQ (3rd)
        #   Terpenes:     mg/g (1st), Result% (2nd, ~0.1x 1st), LOQ (3rd)
        # Detect layout by sampling the first compound: if 2nd value ≈ 10x 1st → cannabinoid

        layout = None  # "cannabinoids" or "terpenes"

        i = 0
        while i < len(lines):
            raw_line = lines[i].strip()
            line_normalized = self._normalize_name(raw_line)
            line_lower = line_normalized.lower()

            # Detect section boundaries to reset layout detection
            if re.search(r"^cannabinoid", line_lower) and "complete" not in line_lower:
                layout = None
                i += 1
                continue
            if re.search(r"^terpene", line_lower) and "complete" not in line_lower:
                layout = None
                i += 1
                continue

            # Skip non-data lines (use a broad skip list)
            skip_patterns = [
                "date", "instrument", "method",
                "calibration", "page", "powered by", "certificate", "highres",
                "report version", "sample", "result", "loq",
                "sop", "client", "address", "phone", "license",
                "specification", "status", "comments", "moisture", "water activity",
                "foreign material", "heavy metal", "microbial", "pesticide",
                "mycotoxin", "residual solvent", "potency", "analysis performed",
                "nt = not tested", "nd = not detected",
            ]
            if not raw_line or any(p in line_lower for p in skip_patterns):
                i += 1
                continue
            # Skip standalone "Total" labels — values handled in Pass 1b
            if re.match(r"^total\s", line_lower):
                i += 1
                continue

            # Skip standalone numeric lines and date lines
            if re.match(r"^[\d.]+$", raw_line) or re.match(r"^\d{1,2}/\d{1,2}/\d{2,4}", raw_line):
                i += 1
                continue

            matched = self._match_compound(line_lower)
            if matched is None or matched.lower() in seen:
                i += 1
                continue

            # Check for ND / <LOQ on current or next line
            value: str | None = None
            below_loq = False
            if re.search(r"\bND\b", raw_line, re.IGNORECASE):
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

            # Extract numeric values from next lines
            if value is None and not below_loq:
                ahead = [lines[i + j].strip() if i + j < len(lines) else "" for j in range(1, 8)]
                numeric_values: list[str] = []
                for candidate_line in ahead:
                    if nd_re.match(candidate_line):
                        break
                    if re.match(r"^<(?:LOQ|[\d.]+)", candidate_line, re.IGNORECASE):
                        below_loq = True
                        break
                    if re.match(r"^\d{1,2}/\d{1,2}/\d{2,4}", candidate_line):
                        continue
                    m_num = number_re.match(candidate_line)
                    if m_num:
                        numeric_values.append(m_num.group(1))
                        if len(numeric_values) >= 2:
                            break
                    else:
                        inline_nums = inline_values_re.findall(candidate_line)
                        for num_str in inline_nums:
                            num = float(num_str)
                            if "." in num_str or int(num) >= 10:
                                if num <= 9999.99:
                                    numeric_values.append(num_str)
                                    if len(numeric_values) >= 2:
                                        break
                        if len(numeric_values) >= 2:
                            break

                if numeric_values:
                    if layout is None and len(numeric_values) >= 2:
                        val0 = float(numeric_values[0])
                        val1 = float(numeric_values[1])
                        if val0 > 0:
                            ratio = val1 / val0
                            if 8 < ratio < 12:
                                layout = "cannabinoids"  # 1st=%, 2nd=mg/g
                            elif 0.08 < ratio < 0.12:
                                layout = "terpenes"  # 1st=mg/g, 2nd=%

                    if layout == "cannabinoids":
                        value = f"{numeric_values[0]}%"
                    elif layout == "terpenes":
                        value = f"{numeric_values[1]}%"
                    else:
                        value = f"{numeric_values[0]}%"

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

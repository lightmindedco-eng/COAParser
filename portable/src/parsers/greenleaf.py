"""Parser for Greenleaf Labs COA documents.

Greenleaf uses "Powered by Confident LIMS" but has a unique per-line column layout:
  Analyte → LOQ → Result (%) → Result (mg/g or PPM)
"""
from __future__ import annotations

import logging
import re
from typing import Any

from .base import BaseParser

logger = logging.getLogger(__name__)


class GreenleafParser(BaseParser):
    name = "greenleaf"

    _NUMBER_RE = re.compile(r"^(\d+\.?\d*)$")
    _ND_RE = re.compile(r"^ND$", re.IGNORECASE)
    _PCT_RE = re.compile(r"^(\d+\.?\d*)\s*%$")

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
        results: list[str] = []
        seen: set[str] = set()

        # Pass 1 – pre-table summary values (value-before-label)
        for i, line in enumerate(lines):
            stripped = line.strip()
            m_pct = self._PCT_RE.match(stripped)
            if m_pct and i + 1 < len(lines):
                next_lower = lines[i + 1].strip().lower()
                if next_lower == "total thc":
                    seen.add("total thc")
                    results.append(f"Total THC: {m_pct.group(1)}%")
                elif next_lower == "total cbd":
                    seen.add("total cbd")
                    results.append(f"Total CBD: {m_pct.group(1)}%")

        # Pass 2 – data table extraction
        _section_type = None
        _in_data_table = False
        _result_offset = 2

        i = 0
        while i < len(lines):
            raw = lines[i].strip()
            lowered = self._normalize_name(raw).lower()

            # Detect section start
            if "gl-msop-01" in lowered or ("potency" in lowered and "hplc" in lowered):
                _section_type = "cannabinoids"
                _in_data_table = False

                i += 1
                continue
            if "gl-msop-03" in lowered or ("terpenes" in lowered and "gc-ms" in lowered):
                _section_type = "terpenes"
                _in_data_table = False

                i += 1
                continue

            if not _section_type:
                i += 1
                continue

            # "Analyte" marks the start of the data table
            if re.match(r"^analyte\s*$", raw, re.IGNORECASE):
                _in_data_table = True
                sub: list[str] = []
                for j in range(i + 1, min(i + 13, len(lines))):
                    h = lines[j].strip().lower()
                    if h in ("%", "ppm", "mg/g"):
                        sub.append(h)
                        if len(sub) == 3:
                            break
                _result_offset = 3 if (len(sub) == 3 and sub[2] == "%") else 2
                i += 1
                continue

            if not _in_data_table:
                i += 1
                continue

            if re.match(r"^(loq|result|%|mg/g|ppm)$", raw, re.IGNORECASE):
                i += 1
                continue

            # Section boundary – stop processing when other test sections begin
            if re.search(r"^(pesticide|heavy\s+metal|microbiology|solvent|mycotoxin|moisture|water\s+activity|foreign\s+matter|residual\s+solvent)", lowered):
                _section_type = None
                _in_data_table = False
                i += 1
                continue

            if re.match(r"^Total\s*$", raw, re.IGNORECASE):
                total_val_idx = i + _result_offset - 1
                if total_val_idx < len(lines):
                    m = self._NUMBER_RE.match(lines[total_val_idx].strip())
                    if m:
                        key = "total terpenes" if _section_type == "terpenes" else "total thc"
                        if key not in seen:
                            seen.add(key)
                            label = "Total Terpenes" if _section_type == "terpenes" else "Total THC"
                            results.append(f"{label}: {m.group(1)}%")
                _section_type = None
                _in_data_table = False
                i += 1
                continue

            matched = self._match_compound(lowered)
            if matched is None or matched.lower() in seen:
                i += 1
                continue

            # Data layout: compound → LOQ → (Result PPM) → Result % → Unit
            # _result_offset tells us which of the 3 data columns holds %
            value: str | None = None
            val_idx = i + _result_offset
            if val_idx < len(lines):
                val_line = lines[val_idx].strip()
                if self._ND_RE.match(val_line):
                    value = "ND"
                else:
                    m_num = self._NUMBER_RE.match(val_line)
                    if m_num:
                        value = f"{m_num.group(1)}%"

            seen.add(matched.lower())
            if value and value != "ND":
                results.append(f"{matched}: {value}")

            i += 4
            continue

        return results

    def parse(self, lines: list[str]) -> dict[str, Any]:
        compounds = self._extract_compounds(lines)
        if compounds:
            return {"format": self.name, "items": compounds}
        return {"format": self.name, "items": lines[:20] or ["No content extracted from document"]}

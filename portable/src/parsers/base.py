"""Base parser abstraction."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from src.core.extractor import read_text


class BaseParser:
    name = "base"

    def __init__(self) -> None:
        self.data_dir = Path(__file__).resolve().parents[1] / ".." / "data"
        self.vocabulary = self._load_vocab()
        self.training_examples = self._load_training_examples()

    def _load_vocab(self) -> dict[str, Any]:
        vocab: dict[str, Any] = {"cannabinoids": [], "terpenes": [], "aliases": {}}
        for file_name, key in (("cannabinoids.json", "cannabinoids"), ("terpenes.json", "terpenes")):
            path = self.data_dir / file_name
            if path.exists():
                with path.open("r", encoding="utf-8") as handle:
                    payload = json.load(handle)
                    vocab[key] = payload.get(key, [])

        aliases_path = self.data_dir / "aliases.json"
        if aliases_path.exists():
            with aliases_path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
                vocab["aliases"] = payload.get("aliases", {})
        return vocab

    def _load_training_examples(self) -> list[str]:
        training_dir = self.data_dir / "training"
        examples: list[str] = []
        if not training_dir.exists():
            return examples

        for path in sorted(training_dir.glob("*")):
            if path.is_file() and path.suffix.lower() in {".txt", ".json", ".csv", ".md", ".pdf"}:
                examples.append(read_text(path))
        return examples

    def _extract_compounds(self, lines: list[str]) -> list[str]:
        """
        Extract compound names and percentage values from COA text.

        Only extracts: Analyte name and Result % value.
        Ignores: LOQ%, Result mg/g, Result PPM, LOD%, CAS, etc.

        Simple strategy: After finding compound name, scan ahead for the first
        numeric percentage value that appears on its own line.
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
            # Skip first numeric value (LOQ%), take the second one (Result %)
            numeric_count = 0
            for candidate_line in ahead:
                if nd_re.match(candidate_line):
                    value = "ND"
                    break
                
                m_num = number_re.match(candidate_line)
                if m_num:
                    numeric_count += 1
                    if numeric_count == 2:  # Second numeric value = Result %
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
        return {"format": self.name, "items": compounds or [f"Detected {self.name} document"]}

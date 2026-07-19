"""Parser for Confident-style COA documents."""

from __future__ import annotations

from typing import Any

from .base import BaseParser


class ConfidentParser(BaseParser):
    name = "confident"

    def parse(self, lines: list[str]) -> dict[str, Any]:
        compounds = self._extract_compounds(lines)
        if compounds:
            return {"format": self.name, "items": compounds}
        # Fallback: show first 20 lines for diagnosis
        return {"format": self.name, "items": lines[:20] or ["No content extracted from document"]}

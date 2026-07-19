from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ParsedResult:
    format_name: str
    items: list[str] = field(default_factory=list)
    output_path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

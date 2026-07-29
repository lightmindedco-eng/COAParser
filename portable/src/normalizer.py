"""Normalization helpers for extracted values."""

from __future__ import annotations


def normalize_value(value: str) -> str:
    """Trim and collapse whitespace for stable parsing."""
    return " ".join(value.split())

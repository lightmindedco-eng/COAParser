"""Normalization helpers."""

from __future__ import annotations


def normalize_value(value: str) -> str:
    return " ".join(value.split())

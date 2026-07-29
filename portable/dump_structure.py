#!/usr/bin/env python3
"""Dump all extracted lines to see structure."""
from pathlib import Path
from src.core.extractor import read_text, extract_text

pdf_path = Path("data/training/0000324224.PDF")
raw_text = read_text(str(pdf_path))
lines = extract_text(raw_text)

# Find line containing cannabinoid table start
for i, line in enumerate(lines):
    if "thca" in line.lower() or "delta" in line.lower():
        print(f"Found cannabinoid section at line {i}")
        print("=" * 80)
        # Show 50 lines from here
        for j in range(max(0, i-2), min(len(lines), i+50)):
            print(f"{j:3d}: {repr(lines[j])}")
        break

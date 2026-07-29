#!/usr/bin/env python3
"""Show exact table structure with all lines."""
from pathlib import Path
from src.core.extractor import read_text, extract_text
import re

pdf_path = Path("data/training/0000324224.PDF")
raw_text = read_text(str(pdf_path))
lines = extract_text(raw_text)

print("=" * 100)
print("EXACT TABLE STRUCTURE")
print("=" * 100)
print()

# Find cannabinoid table
rank_prefix_re = re.compile(r"^\d+\s+")

for i, line in enumerate(lines):
    if "cannabinoid" in line.lower() and ("analyte" in line.lower() or "result" in line.lower()):
        print(f"CANNABINOID TABLE HEADER at line {i}:")
        print(f"  {line}")
        print()
        print("Next 50 lines (exact order):")
        print("-" * 100)
        for j in range(i+1, min(i+51, len(lines))):
            cleaned = rank_prefix_re.sub("", lines[j].strip())
            print(f"{j:3d}: '{cleaned}'")
        break

print()
print()

# Find first terpene
for i, line in enumerate(lines):
    if "terpene" in line.lower() and ("analyte" in line.lower() or "result" in line.lower()):
        print(f"TERPENE TABLE HEADER at line {i}:")
        print(f"  {line}")
        print()
        print("Next 40 lines (exact order):")
        print("-" * 100)
        for j in range(i+1, min(i+41, len(lines))):
            cleaned = rank_prefix_re.sub("", lines[j].strip())
            print(f"{j:3d}: '{cleaned}'")
        break

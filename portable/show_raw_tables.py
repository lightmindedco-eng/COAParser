#!/usr/bin/env python3
"""Analyze exact table structure."""
from pathlib import Path
from src.core.extractor import read_text, extract_text

pdf_path = Path("data/training/0000324224.PDF")
raw_text = read_text(str(pdf_path))
lines = extract_text(raw_text)

print("=" * 100)
print("TABLE STRUCTURE ANALYSIS")
print("=" * 100)
print()

# Find the cannabinoid and terpene tables
for i, line in enumerate(lines):
    if "cannabinoid" in line.lower() and ("analyte" in line.lower() or "result" in line.lower()):
        print("CANNABINOID TABLE HEADER:")
        print(f"Line {i}: {line}")
        print()
        print("Following 40 lines:")
        for j in range(i+1, min(i+41, len(lines))):
            print(f"{j:3d}: {lines[j]}")
        break

print()
print()

# Find terpene table
for i, line in enumerate(lines):
    if "terpene" in line.lower() and ("analyte" in line.lower() or "result" in line.lower()):
        print("TERPENE TABLE HEADER:")
        print(f"Line {i}: {line}")
        print()
        print("Following 30 lines:")
        for j in range(i+1, min(i+31, len(lines))):
            print(f"{j:3d}: {lines[j]}")
        break

#!/usr/bin/env python3
"""Show exact line-by-line structure of extracted text around compounds."""
from pathlib import Path
from src.core.extractor import read_text, extract_text

pdf_path = Path("data/training/0000324224.PDF")
raw_text = read_text(str(pdf_path))
lines = extract_text(raw_text)

# Find lines with cannabinoid/terpene names
cannabinoids = ["thca", "thc", "cbda", "cbd", "cbga", "cbg", "cbc", "cbn"]
found_indices = []

for i, line in enumerate(lines):
    line_lower = line.lower()
    for cbd in cannabinoids:
        if cbd in line_lower and len(line) < 50:
            found_indices.append(i)
            break

print("=" * 80)
print("LINE-BY-LINE STRUCTURE AROUND COMPOUNDS")
print("=" * 80)
print()

# Show context around each compound
for idx in found_indices[:5]:  # First 5 compounds
    print(f"LINE {idx}: {repr(lines[idx])}")
    print("  Next 15 lines:")
    for offset in range(1, 16):
        if idx + offset < len(lines):
            line = lines[idx + offset]
            print(f"    {offset:2d}: {repr(line)}")
    print()

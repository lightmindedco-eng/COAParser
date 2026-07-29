#!/usr/bin/env python3
"""Debug table structure to identify column positions."""
from pathlib import Path
from src.core.extractor import read_text, extract_text

pdf_path = Path("data/training/0000324224.PDF")
raw_text = read_text(str(pdf_path))
lines = extract_text(raw_text)

print("=" * 100)
print("TABLE STRUCTURE ANALYSIS")
print("=" * 100)
print()

# Look for table headers
print("SEARCHING FOR TABLE HEADERS AND STRUCTURE:")
print("-" * 100)

in_cannabinoid_table = False
in_terpene_table = False
table_lines = []

for i, line in enumerate(lines):
    line_lower = line.lower()
    
    # Detect table sections
    if "cannabinoid" in line_lower and "analyte" in line_lower:
        in_cannabinoid_table = True
        in_terpene_table = False
        print(f"\n[CANNABINOID TABLE HEADER at line {i}]")
        print(f"  {line}")
        table_lines = []
        continue
    
    if "terpene" in line_lower and "analyte" in line_lower:
        in_terpene_table = True
        in_cannabinoid_table = False
        print(f"\n[TERPENE TABLE HEADER at line {i}]")
        print(f"  {line}")
        table_lines = []
        continue
    
    # Capture table rows
    if in_cannabinoid_table or in_terpene_table:
        if line.strip() == "" or "total" in line_lower:
            if table_lines:
                print("\n  [Sample rows]:")
                for j, row in enumerate(table_lines[:10]):
                    print(f"    {row}")
                table_lines = []
            if "total" in line_lower:
                in_cannabinoid_table = False
                in_terpene_table = False
        else:
            table_lines.append(f"  {line}")

print()
print()
print("FULL TEXT AROUND CANNABINOID TABLE:")
print("=" * 100)
for i, line in enumerate(lines):
    if "cannabinoid" in line.lower() and "analyte" in line.lower():
        start = max(0, i - 2)
        end = min(len(lines), i + 30)
        for j in range(start, end):
            marker = ">>> " if j == i else "    "
            print(f"{marker}{j:3d}: {lines[j]}")
        break

print()
print()
print("FULL TEXT AROUND TERPENE TABLE:")
print("=" * 100)
for i, line in enumerate(lines):
    if "terpene" in line.lower() and "analyte" in line.lower():
        start = max(0, i - 2)
        end = min(len(lines), i + 20)
        for j in range(start, end):
            marker = ">>> " if j == i else "    "
            print(f"{marker}{j:3d}: {lines[j]}")
        break

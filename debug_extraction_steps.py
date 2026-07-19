#!/usr/bin/env python3
"""Debug extraction with detailed step-by-step output."""
from pathlib import Path
from src.core.extractor import read_text, extract_text
import re

pdf_path = Path("data/training/0000324224.PDF")
raw_text = read_text(str(pdf_path))
lines = extract_text(raw_text)

print("=" * 100)
print("STEP-BY-STEP EXTRACTION DEBUG")
print("=" * 100)
print()

# Load vocabulary
from src.parsers.base import BaseParser
parser = BaseParser()
all_compounds = parser.vocabulary["cannabinoids"] + parser.vocabulary["terpenes"]

# Regex patterns (from base.py)
rank_prefix_re = re.compile(r"^\d+\s+")
loq_md_re = re.compile(r"^(loq|limit|detection|sensitivity|mg/g|ppm)", re.IGNORECASE)
number_re = re.compile(r"^(\d+\.?\d*)$")
nd_re = re.compile(r"^ND$", re.IGNORECASE)

# Find first compound
print("FINDING FIRST COMPOUND IN TABLE:")
print("-" * 100)

for i, raw_line in enumerate(lines):
    line = rank_prefix_re.sub("", raw_line.strip())
    line_lower = line.lower()
    
    if re.search(r"^total\s", line_lower) or "analyte" in line_lower:
        continue
    
    matched = None
    for compound in all_compounds:
        if re.search(rf"\b{re.escape(compound.lower())}\b", line_lower):
            matched = compound
            break
    
    if matched:
        print(f"Found compound at line {i}: {matched}")
        print(f"Raw line: '{raw_line}'")
        print()
        
        print("Scanning next 15 lines for Result % value:")
        print("-" * 100)
        
        for offset in range(1, 16):
            if i + offset >= len(lines):
                break
            
            candidate = lines[i + offset].strip()
            
            # Analyze this line
            is_label = loq_md_re.match(candidate)
            is_empty = candidate == ""
            is_long = len(candidate) > 50
            is_nd = nd_re.match(candidate)
            is_number = number_re.match(candidate)
            
            status = "?"
            if is_label:
                status = "✗ SKIP (LOQ/limit/mg/g/ppm label)"
            elif is_empty:
                status = "✗ SKIP (empty)"
            elif is_long:
                status = "✗ SKIP (too long)"
            elif is_nd:
                status = "✓ SELECTED (ND)"
            elif is_number:
                m = number_re.match(candidate)
                status = f"✓ SELECTED (value: {m.group(1)}%)"
            else:
                status = "? (not a number)"
            
            print(f"  [{offset}] '{candidate}' {status}")
        
        print()
        break

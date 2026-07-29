#!/usr/bin/env python3
"""Debug exact extraction sequence for compounds."""
from pathlib import Path
from src.core.extractor import read_text, extract_text
import re

pdf_path = Path("data/training/0000324224.PDF")
raw_text = read_text(str(pdf_path))
lines = extract_text(raw_text)

print("=" * 100)
print("DETAILED EXTRACTION DEBUG")
print("=" * 100)
print()

# Load vocabulary
from src.parsers.base import BaseParser
parser = BaseParser()
all_compounds = parser.vocabulary["cannabinoids"] + parser.vocabulary["terpenes"]

# Regex patterns
rank_prefix_re = re.compile(r"^\d+\s+")
loq_re = re.compile(r"loq|limit.*quantitation", re.IGNORECASE)
ppm_re = re.compile(r"ppm|mg/g", re.IGNORECASE)
number_re = re.compile(r"^(\d+\.?\d*)$")
nd_re = re.compile(r"^ND$", re.IGNORECASE)

# Find first compound match
print("LOOKING FOR FIRST CANNABINOID/TERPENE MATCH:")
print("-" * 100)
for i, raw_line in enumerate(lines):
    line = rank_prefix_re.sub("", raw_line.strip())
    line_lower = line.lower()
    
    # Skip headers and totals
    if "analyte" in line_lower or re.search(r"^total\s", line_lower):
        continue
    
    # Match against vocabulary
    matched = None
    for compound in all_compounds:
        if re.search(rf"\b{re.escape(compound.lower())}\b", line_lower):
            matched = compound
            break
    
    if matched:
        print(f"\nFound compound at line {i}: {matched}")
        print(f"Full line: {raw_line}")
        print()
        
        # Show the next 12 lines with their processing
        print("Next lines with filtering logic:")
        print("-" * 100)
        ahead = [lines[i + j].strip() if i + j < len(lines) else "" for j in range(1, 12)]
        
        for j, candidate_line in enumerate(ahead):
            line_num = i + j + 1
            skipped = False
            reason = ""
            
            # Check filtering
            if loq_re.search(candidate_line):
                skipped = True
                reason = "← SKIPPED: Contains 'LOQ'"
            elif ppm_re.search(candidate_line):
                skipped = True
                reason = "← SKIPPED: Contains 'mg/g' or 'PPM'"
            elif nd_re.match(candidate_line):
                reason = "← MATCH: ND (Not Detected)"
            elif number_re.match(candidate_line):
                reason = "← MATCH: Numeric percentage value"
            
            print(f"  [{j}] Line {line_num:3d}: '{candidate_line}' {reason}")
        
        print()
        print("EXTRACTION RESULT:")
        print("-" * 100)
        
        value = None
        for j, candidate_line in enumerate(ahead):
            if loq_re.search(candidate_line) or ppm_re.search(candidate_line):
                continue
            
            if nd_re.match(candidate_line):
                value = "ND"
                print(f"Selected: ND")
                break
            
            m_num = number_re.match(candidate_line)
            if m_num:
                value = f"{m_num.group(1)}%"
                print(f"Selected: {value}")
                break
        
        if not value:
            print("No value found")
        else:
            print(f"Final output: {matched}: {value}")
        
        # Show first 3 compounds only
        break

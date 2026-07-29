#!/usr/bin/env python3
"""Test new Result-based extraction."""
from pathlib import Path
from src.core.extractor import read_text, extract_text
from src.parsers.gateway import GatewayParser

pdf_path = Path("data/training/0000324224.PDF")
raw_text = read_text(str(pdf_path))
lines = extract_text(raw_text)

print("=" * 100)
print("TESTING NEW RESULT-BASED EXTRACTION")
print("=" * 100)
print()

parser = GatewayParser()
compounds = parser._extract_compounds(lines)

print(f"Extracted {len(compounds)} compounds:")
print()
for comp in compounds:
    print(f"  {comp}")

#!/usr/bin/env python3
"""Comprehensive diagnostic for text extraction and parsing."""
from pathlib import Path
import sys

# Test with the gateway PDF that was working
test_pdf = Path("data/training/0000324224.PDF")

if not test_pdf.exists():
    print(f"ERROR: Test PDF not found: {test_pdf}")
    sys.exit(1)

print("=" * 80)
print("COMPREHENSIVE DIAGNOSTIC")
print("=" * 80)
print()

# Step 1: Text extraction
print("STEP 1: Text Extraction")
print("-" * 80)
from src.core.extractor import read_text, extract_text

raw_text = read_text(str(test_pdf))
lines = extract_text(raw_text)

print(f"Raw text: {len(raw_text)} chars")
print(f"Lines: {len(lines)}")
print(f"First 10 lines:")
for i, line in enumerate(lines[:10]):
    print(f"  {i}: {line}")
print()

# Step 2: Format detection
print("STEP 2: Format Detection")
print("-" * 80)
from src.core.detector import detect_format

fmt = detect_format(raw_text)
print(f"Detected format: {fmt}")
print()

# Step 3: Parser instantiation
print("STEP 3: Parser Instantiation")
print("-" * 80)
from src.parsers.gateway import GatewayParser

parser = GatewayParser()
print(f"Parser: {parser.__class__.__name__}")
print(f"Vocabulary loaded:")
print(f"  Cannabinoids: {len(parser.vocabulary['cannabinoids'])} items")
if parser.vocabulary['cannabinoids']:
    print(f"    {parser.vocabulary['cannabinoids']}")
print(f"  Terpenes: {len(parser.vocabulary['terpenes'])} items")
if parser.vocabulary['terpenes']:
    print(f"    {parser.vocabulary['terpenes']}")
print(f"  Aliases: {len(parser.vocabulary['aliases'])} entries")
print()

# Step 4: Compound extraction
print("STEP 4: Compound Extraction")
print("-" * 80)
compounds = parser._extract_compounds(lines)
print(f"Extracted {len(compounds)} compounds:")
for i, comp in enumerate(compounds):
    print(f"  {i+1}: {comp}")
print()

# Step 5: Full parse
print("STEP 5: Full Parse")
print("-" * 80)
result = parser.parse(lines)
print(f"Result format: {result['format']}")
print(f"Result items: {len(result['items'])}")
for i, item in enumerate(result['items'][:10]):
    print(f"  {i+1}: {item}")
if len(result['items']) > 10:
    print(f"  ... and {len(result['items']) - 10} more")

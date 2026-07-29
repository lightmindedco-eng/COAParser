#!/usr/bin/env python3
"""Diagnostic script to debug PDF parsing issues."""
import json
from pathlib import Path

# Test PDF path
test_pdf = Path("portable/Input/1A40E010002CF89000010613.pdf")
if not test_pdf.exists():
    print(f"ERROR: PDF not found at {test_pdf}")
    print(f"Current dir: {Path.cwd()}")
    print(f"Files in portable/Input: {list(Path('portable/Input').glob('*')) if Path('portable/Input').exists() else 'Directory not found'}")
    exit(1)

print("=" * 70)
print("PDF DIAGNOSTIC REPORT")
print("=" * 70)
print(f"PDF Path: {test_pdf.resolve()}")
print(f"File Size: {test_pdf.stat().st_size} bytes")
print()

# Step 1: Extract text
print("-" * 70)
print("STEP 1: Text Extraction")
print("-" * 70)
from src.core.extractor import read_text

text = read_text(str(test_pdf))
print(f"Extracted text length: {len(text)} characters")
print(f"First 1500 chars:\n{text[:1500]}")
print()
print(f"Last 1500 chars:\n{text[-1500:]}")
print()

# Step 2: Detect format
print("-" * 70)
print("STEP 2: Format Detection")
print("-" * 70)
from src.core.detector import detect_format

format_name = detect_format(text)
print(f"Detected format: {format_name}")
print()

# Step 3: Get parser for format
print("-" * 70)
print("STEP 3: Parser Selection & Parsing")
print("-" * 70)
from src.parser import COAParser

parser = COAParser()
parser_obj = parser._get_parser(format_name)
print(f"Parser class: {parser_obj.__class__.__name__}")

items = parser_obj.parse(text)
print(f"Parsed items count: {len(items)}")
for i, item in enumerate(items[:30]):
    print(f"  {i+1}. {item}")

if len(items) > 30:
    print(f"  ... and {len(items) - 30} more")

print()

# Step 4: Build report
print("-" * 70)
print("STEP 4: Report Generation")
print("-" * 70)
report = parser._build_report(test_pdf.name, format_name, items)
print(report)
print()
print("=" * 70)

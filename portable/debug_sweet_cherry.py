#!/usr/bin/env python3
"""Debug PDF text extraction and parsing."""
from pathlib import Path

pdf_path = Path("portable/Output").parent / "2501PLO0014.0044 - Shico LLC - Sweet Cherry 100mg THC_50mg THCv 2_1 Fruit Chews (1).pdf"

# Try different paths
for candidate in [pdf_path, Path("portable/Input/2501PLO0014.0044 - Shico LLC - Sweet Cherry 100mg THC_50mg THCv 2_1 Fruit Chews (1).pdf"), Path("Input/2501PLO0014.0044 - Shico LLC - Sweet Cherry 100mg THC_50mg THCv 2_1 Fruit Chews (1).pdf")]:
    if candidate.exists():
        pdf_path = candidate
        break

if not pdf_path.exists():
    print(f"PDF not found. Checked:")
    print(f"  {pdf_path}")
    print(f"Available files in Input:")
    for f in Path("portable/Input").glob("*"):
        print(f"    {f.name}")
    exit(1)

print("=" * 80)
print(f"PDF: {pdf_path.name}")
print("=" * 80)
print()

# Extract text
from src.core.extractor import read_text, extract_text

raw_text = read_text(str(pdf_path))
lines = extract_text(raw_text)

print(f"Raw text length: {len(raw_text)} chars")
print(f"Line count: {len(lines)}")
print()

print("First 50 lines:")
print("-" * 80)
for i, line in enumerate(lines[:50]):
    print(f"{i:3d}: {line}")
print()

print("Looking for cannabinoid/terpene keywords in text:")
print("-" * 80)
keywords = ["thc", "cbd", "thca", "cbda", "myrcene", "limonene", "pinene", "%", "total"]
for kw in keywords:
    matches = [i for i, line in enumerate(lines) if kw.lower() in line.lower()]
    if matches:
        print(f"  {kw.upper()}: found in {len(matches)} lines")
        for idx in matches[:3]:
            print(f"    Line {idx}: {lines[idx]}")

print()
print("=" * 80)
print("PARSER EXTRACTION TEST")
print("=" * 80)

from src.parsers.aerolabs import AerolabsParser

parser = AerolabsParser()
print(f"Vocabulary cannabinoids: {len(parser.vocabulary['cannabinoids'])}")
print(f"  {parser.vocabulary['cannabinoids'][:10]}")
print()
print(f"Vocabulary terpenes: {len(parser.vocabulary['terpenes'])}")
print(f"  {parser.vocabulary['terpenes'][:10]}")
print()

result = parser.parse(lines)
print(f"Extracted items: {len(result['items'])}")
for item in result['items'][:20]:
    print(f"  {item}")

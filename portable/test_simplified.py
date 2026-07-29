#!/usr/bin/env python3
"""Quick test of simplified extraction."""
from pathlib import Path
from src.core.extractor import read_text, extract_text
from src.parsers.gateway import GatewayParser

pdf_path = Path("data/training/0000324224.PDF")
raw_text = read_text(str(pdf_path))
lines = extract_text(raw_text)

parser = GatewayParser()
compounds = parser._extract_compounds(lines)

print("=" * 80)
print("EXTRACTED COMPOUNDS")
print("=" * 80)
print(f"Total: {len(compounds)}")
print()
for comp in compounds[:20]:
    print(f"  {comp}")
if len(compounds) > 20:
    print(f"  ... and {len(compounds) - 20} more")

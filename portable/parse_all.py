#!/usr/bin/env python3
"""Parse all PDFs in Input and generate output."""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from parser import COAParser

parser = COAParser()
input_dir = Path("Input")
output_dir = Path("Output")

# Ensure output dir exists
output_dir.mkdir(exist_ok=True)

# Parse all PDFs
pdf_files = list(input_dir.glob("*.pdf"))
print(f"Found {len(pdf_files)} PDF files\n")

for pdf in pdf_files:
    print(f"Parsing: {pdf.name}...")
    try:
        result = parser.parse_file(pdf, output_dir=str(output_dir))
        if result:
            print(f"  ✓ Format: {result.format_name}")
            print(f"  ✓ Compounds: {len(result.items)}")
        else:
            print(f"  ✗ Failed to parse")
    except Exception as e:
        print(f"  ✗ Error: {e}")

print("\nDone!")

#!/usr/bin/env python3
"""
Debug script to see what product name is being detected from a Gateway Labs PDF.
"""

import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from core.extractor import read_text, extract_text
from core.detector import detect_product_name, detect_format

def debug_pdf(pdf_path):
    """Debug product name detection for a PDF."""
    print(f"\n{'='*80}")
    print(f"Debugging: {pdf_path}")
    print(f"{'='*80}\n")
    
    # Extract text
    print("[1] Reading PDF...")
    content = read_text(pdf_path)
    lines = extract_text(content)
    
    print(f"Total lines extracted: {len(lines)}")
    print()
    
    # Show first 30 lines
    print("[2] First 30 extracted lines:")
    print("-" * 80)
    for i, line in enumerate(lines[:30], 1):
        print(f"{i:3d}: {line}")
    print()
    
    # Look for "sample name" specifically
    print("[3] Searching for 'sample name' in all lines:")
    print("-" * 80)
    found_sample = False
    for i, line in enumerate(lines, 1):
        if "sample name" in line.lower():
            print(f"Line {i}: {line}")
            found_sample = True
    if not found_sample:
        print("NO 'sample name' FOUND IN ANY LINE")
    print()
    
    # Look for "type" lines
    print("[4] Searching for 'type' in first 50 lines:")
    print("-" * 80)
    for i, line in enumerate(lines[:50], 1):
        if "type" in line.lower():
            print(f"Line {i}: {line}")
    print()
    
    # Run product name detection
    print("[5] Running detect_product_name():")
    print("-" * 80)
    product_name = detect_product_name(lines)
    print(f"Detected product name: {product_name}")
    print()
    
    # Run format detection
    print("[6] Running detect_format():")
    print("-" * 80)
    lab_format = detect_format(content)
    print(f"Detected format: {lab_format}")
    print()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python debug_product_name.py <pdf_path>")
        print("\nExample: python debug_product_name.py test.pdf")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    if not os.path.exists(pdf_path):
        print(f"ERROR: File not found: {pdf_path}")
        sys.exit(1)
    
    debug_pdf(pdf_path)

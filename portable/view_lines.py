#!/usr/bin/env python3
"""Test extraction and show results."""
from pathlib import Path
import sys

try:
    from src.core.extractor import read_text, extract_text
    from src.parsers.gateway import GatewayParser

    pdf_path = Path("data/training/0000324224.PDF")
    if not pdf_path.exists():
        print(f"ERROR: {pdf_path} not found")
        sys.exit(1)

    print(f"Reading {pdf_path}...")
    raw_text = read_text(str(pdf_path))
    print(f"Raw text length: {len(raw_text)}")
    
    lines = extract_text(raw_text)
    print(f"Extracted {len(lines)} lines")
    
    # Look for cannabinoids section
    print("\nFirst 200 lines (searching for cannabinoid section):")
    for i, line in enumerate(lines[:200]):
        if line:  # non-empty
            print(f"{i:3d}: {repr(line)}")
    
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()

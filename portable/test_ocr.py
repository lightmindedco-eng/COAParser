#!/usr/bin/env python3
"""
Test if pytesseract and Tesseract are working.
"""

import os
import sys
from pathlib import Path

# Test 1: Check Tesseract installation
print("[1] Checking Tesseract installation...")
from tesseract_config import get_tesseract_path
tess_path = get_tesseract_path()
print(f"Tesseract path: {tess_path}")
if tess_path:
    print(f"File exists: {os.path.isfile(tess_path)}")
else:
    print("ERROR: Tesseract not found!")
    sys.exit(1)

print()

# Test 2: Check pytesseract
print("[2] Testing pytesseract...")
try:
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = tess_path
    print(f"pytesseract imported successfully")
    print(f"pytesseract version: {pytesseract.__version__ if hasattr(pytesseract, '__version__') else 'unknown'}")
except Exception as e:
    print(f"ERROR importing pytesseract: {e}")
    sys.exit(1)

print()

# Test 3: Try OCRing a test image
print("[3] Testing OCR on a sample PDF page...")
try:
    import fitz
    from PIL import Image
    
    pdf_path = sys.argv[1] if len(sys.argv) > 1 else None
    if not pdf_path:
        print("ERROR: Need PDF path as argument")
        print("Usage: python test_ocr.py <pdf_path>")
        sys.exit(1)
    
    print(f"Opening: {pdf_path}")
    doc = fitz.open(pdf_path)
    
    # Try first page
    page = doc[0]
    print(f"Page 1 total: {len(doc)} pages")
    
    # Check for embedded text first
    text = page.get_text().strip()
    print(f"Embedded text length: {len(text)}")
    if text:
        print(f"Embedded text found: {text[:100]}...")
    else:
        print("No embedded text, will try OCR...")
        
        # Try OCR
        print("Converting page to image...")
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        print(f"Pixmap size: {pix.width}x{pix.height}")
        
        print("Converting to PIL Image...")
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        print(f"Image size: {img.size}")
        
        print("Running OCR...")
        ocr_text = pytesseract.image_to_string(img)
        print(f"OCR text length: {len(ocr_text)}")
        if ocr_text:
            print(f"OCR result: {ocr_text[:200]}...")
        else:
            print("OCR returned empty string")
            
except Exception as e:
    import traceback
    print(f"ERROR: {e}")
    traceback.print_exc()
    sys.exit(1)

print("\n✓ All OCR tests passed!")

"""Diagnostic: verify the parser output against a real training PDF."""

import sys
from pathlib import Path

root = Path(__file__).parent
sys.path.insert(0, str(root))

from src.parser import COAParser

training_dir = root / "data" / "training"
pdf_files = sorted(training_dir.glob("*.pdf")) + sorted(training_dir.glob("*.PDF"))
if not pdf_files:
    print("No PDFs found")
    sys.exit(1)

test_pdf = pdf_files[0]
print(f"Parsing: {test_pdf.name}")

result = COAParser().parse_file(test_pdf, output_dir="Output")
print(f"Format: {result.format_name}")
print(f"Lines extracted: {result.metadata['line_count']}")
print(f"Items found: {len(result.items)}")
print()
for item in result.items:
    print(" ", item)

if result.output_path:
    print(f"\nOutput file: {result.output_path}")
    print(Path(result.output_path).read_text(encoding="utf-8"))


import sys
from pathlib import Path

root = Path(__file__).parent
sys.path.insert(0, str(root))

try:
    import fitz  # type: ignore
except Exception as e:
    print(f"fitz MISSING: {e}")
    sys.exit(1)

training_dir = root / "data" / "training"
pdf_files = sorted(training_dir.glob("*.pdf")) + sorted(training_dir.glob("*.PDF"))
if not pdf_files:
    print("No PDF files found")
    sys.exit(1)

test_pdf = pdf_files[0]
doc = fitz.open(str(test_pdf))

all_text = []
for i, page in enumerate(doc):
    text = page.get_text().strip()
    all_text.append(f"=== PAGE {i+1} ===\n{text}")

full = "\n\n".join(all_text)
out = root / "pdf_dump.txt"
out.write_text(full, encoding="utf-8")
print(f"Done — open pdf_dump.txt ({len(full)} chars)")


import sys
from pathlib import Path

root = Path(__file__).parent
sys.path.insert(0, str(root))

from tesseract_config import get_tesseract_path

tess = get_tesseract_path()

try:
    import fitz  # type: ignore
except Exception as e:
    print(f"fitz MISSING: {e}")
    sys.exit(1)

training_dir = root / "data" / "training"
pdf_files = sorted(training_dir.glob("*.pdf")) + sorted(training_dir.glob("*.PDF"))
if not pdf_files:
    print("No PDF files found")
    sys.exit(1)

test_pdf = pdf_files[0]
doc = fitz.open(str(test_pdf))

all_text = []
for i, page in enumerate(doc):
    text = page.get_text().strip()
    all_text.append(f"=== PAGE {i+1} ===\n{text}")

full = "\n\n".join(all_text)
out = root / "diagnostic_output.txt"
out.write_text(full, encoding="utf-8")
print(f"Dumped {len(full)} chars to {out}")


import sys
from pathlib import Path

root = Path(__file__).parent
sys.path.insert(0, str(root))

from tesseract_config import get_tesseract_path

tess = get_tesseract_path()
out_lines = [f"Tesseract: {tess}", f"Tesseract exists: {Path(tess).is_file() if tess else False}", ""]

try:
    import fitz  # type: ignore
    out_lines.append(f"fitz version: {fitz.__version__}")
except Exception as e:
    out_lines.append(f"fitz MISSING: {e}")
    fitz = None

try:
    import pytesseract  # type: ignore
    if tess:
        pytesseract.pytesseract.tesseract_cmd = tess
    out_lines.append("pytesseract: OK")
except Exception as e:
    out_lines.append(f"pytesseract MISSING: {e}")
    pytesseract = None

try:
    from PIL import Image  # type: ignore
    out_lines.append("PIL: OK")
except Exception as e:
    out_lines.append(f"PIL MISSING: {e}")
    Image = None

training_dir = root / "data" / "training"
pdf_files = sorted(training_dir.glob("*.pdf")) + sorted(training_dir.glob("*.PDF"))
if not pdf_files:
    out_lines.append("No PDF files found in data/training/")
else:
    test_pdf = pdf_files[0]
    out_lines.append(f"\nTesting: {test_pdf.name}")

    if fitz is not None:
        doc = fitz.open(str(test_pdf))
        out_lines.append(f"Total pages: {doc.page_count}")
        for i, page in enumerate(doc):
            direct_text = page.get_text().strip()
            out_lines.append(f"\n--- Page {i+1} ---")
            if direct_text:
                out_lines.append(f"Direct text ({len(direct_text)} chars):")
                out_lines.append(direct_text[:500])
            else:
                out_lines.append("Direct text: EMPTY — trying OCR")
                if pytesseract is not None and Image is not None:
                    try:
                        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                        ocr = pytesseract.image_to_string(img).strip()
                        out_lines.append(f"OCR text ({len(ocr)} chars):")
                        out_lines.append(ocr[:500])
                    except Exception as e:
                        out_lines.append(f"OCR error: {e}")
                else:
                    out_lines.append("OCR unavailable")

output = "\n".join(out_lines)
out_path = root / "diagnostic_output.txt"
out_path.write_text(output, encoding="utf-8")
print(f"Written to {out_path}")


import importlib.util
import os
import sys
from pathlib import Path

results = []

# Python executable
results.append(f"Python: {sys.executable}")

# Packages
for pkg in ["pytesseract", "fitz", "PIL", "pypdf", "PyPDF2"]:
    found = bool(importlib.util.find_spec(pkg))
    results.append(f"  {pkg}: {'OK' if found else 'MISSING'}")

# Tesseract binary
sys.path.insert(0, str(Path(__file__).parent))
try:
    from tesseract_config import get_tesseract_path
    tess = get_tesseract_path()
    exists = os.path.isfile(tess) if tess else False
    results.append(f"Tesseract path: {tess}")
    results.append(f"Tesseract exists: {exists}")
except Exception as exc:
    results.append(f"Tesseract config error: {exc}")

# Try reading one PDF
training_dir = Path(__file__).parent / "data" / "training"
pdf_files = list(training_dir.glob("*.pdf")) + list(training_dir.glob("*.PDF"))
if pdf_files:
    test_pdf = pdf_files[0]
    results.append(f"\nTest PDF: {test_pdf.name}")
    try:
        import fitz  # type: ignore
        doc = fitz.open(str(test_pdf))
        text = "\n".join(p.get_text() for p in doc)
        results.append(f"fitz text length: {len(text)}")
        results.append(f"fitz sample: {repr(text[:300])}")
    except Exception as exc:
        results.append(f"fitz error: {exc}")

    try:
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore
        from tesseract_config import get_tesseract_path
        tp = get_tesseract_path()
        if tp:
            pytesseract.pytesseract.tesseract_cmd = tp
        import fitz as fitz2  # type: ignore
        doc2 = fitz2.open(str(test_pdf))
        page = doc2[0]
        pix = page.get_pixmap(matrix=fitz2.Matrix(2, 2))
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        ocr_text = pytesseract.image_to_string(img)
        results.append(f"OCR text length: {len(ocr_text)}")
        results.append(f"OCR sample: {repr(ocr_text[:300])}")
    except Exception as exc:
        results.append(f"OCR error: {exc}")
else:
    results.append("No PDF files found in training folder")

output = "\n".join(results)
print(output)
Path("diagnostic_output.txt").write_text(output, encoding="utf-8")
print("\nDiagnostic saved to diagnostic_output.txt")

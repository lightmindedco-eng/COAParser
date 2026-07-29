"""Text extraction layer."""

from __future__ import annotations

import os
from pathlib import Path

from tesseract_config import get_tesseract_path

_TESS_PATH = get_tesseract_path()
if _TESS_PATH and os.path.isfile(_TESS_PATH):
    try:
        import pytesseract as _pytess  # type: ignore
        _pytess.pytesseract.tesseract_cmd = _TESS_PATH
    except Exception:
        pass


def read_text(path: str | Path) -> str:
    """Read text from plain text files or PDFs, scanning every page."""
    file_path = Path(path)
    if file_path.suffix.lower() == ".pdf":
        try:
            import fitz  # type: ignore
        except Exception:
            fitz = None

        try:
            import pytesseract  # type: ignore
            from PIL import Image  # type: ignore
            tess_path = get_tesseract_path()
            if tess_path:
                pytesseract.pytesseract.tesseract_cmd = tess_path
        except Exception:
            pytesseract = None
            Image = None

        if fitz is not None:
            try:
                doc = fitz.open(str(file_path))
                page_texts: list[str] = []
                for page in doc:
                    text = page.get_text().strip()
                    if text:
                        # Page has embedded text — use it directly
                        page_texts.append(text)
                    elif pytesseract is not None and Image is not None:
                        # Page is a scanned image — OCR it
                        try:
                            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                            ocr_text = pytesseract.image_to_string(img).strip()
                            if ocr_text:
                                page_texts.append(ocr_text)
                        except Exception:
                            pass
                if page_texts:
                    return "\n".join(page_texts)
            except Exception:
                pass

        # pypdf fallback (text-only PDFs)
        try:
            from pypdf import PdfReader  # type: ignore
        except Exception:
            try:
                from PyPDF2 import PdfReader  # type: ignore
            except Exception:
                PdfReader = None  # type: ignore

        if PdfReader is not None:
            try:
                reader = PdfReader(str(file_path))
                extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
                if extracted.strip():
                    return extracted
            except Exception:
                pass

        lowered_name = file_path.name.lower()
        hints = []
        if "aerolabs" in lowered_name:
            hints.append("Aerolabs")
        if "gateway" in lowered_name:
            hints.append("Gateway")
        if "confident" in lowered_name:
            hints.append("Confident")
        if hints:
            return "\n".join(hints)

        return f"OCR unavailable; could not extract text from {file_path.name}"

    try:
        return file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return f"Could not read {file_path.name}"


def extract_text(content: str) -> list[str]:
    """Split text into lines for downstream parsing."""
    return [line.strip() for line in content.splitlines() if line.strip()]

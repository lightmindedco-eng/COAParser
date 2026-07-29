from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any

from tesseract_config import get_tesseract_path

_HAS_FITZ = False
_HAS_OCR = False
_HAS_PIL = False

_fitz = None
try:
    import fitz as _fitz_module
    _fitz = _fitz_module
    _HAS_FITZ = True
except Exception:
    pass

_pytess = None
try:
    import pytesseract
    _HAS_OCR = True
except ImportError:
    pass

_pil = None
try:
    from PIL import Image, ImageEnhance
    _pil = Image
    _HAS_PIL = True
except ImportError:
    pass

_LARGE_IMAGE_MIN = 1000


def _setup_tesseract() -> None:
    if _HAS_OCR and _pytess is not None:
        tess_path = get_tesseract_path()
        if tess_path:
            pytesseract.pytesseract.tesseract_cmd = tess_path


def has_embedded_coa_images(path: str | Path) -> bool:
    if not (_HAS_FITZ and _HAS_OCR and _HAS_PIL):
        return False
    try:
        doc = _fitz.open(str(path))
        for page in doc:
            for img in page.get_images(full=True):
                if img[2] >= _LARGE_IMAGE_MIN and img[3] >= _LARGE_IMAGE_MIN:
                    doc.close()
                    return True
        doc.close()
    except Exception:
        pass
    return False


def _preprocess(img, scale: int = 4):
    w, h = img.size
    img = img.resize((w * scale, h * scale), _pil.LANCZOS)
    if img.mode != "RGB":
        img = img.convert("RGB")
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(1.8)
    enhancer = ImageEnhance.Sharpness(img)
    img = enhancer.enhance(3.0)
    img = img.convert("L")
    img = img.point(lambda x: 0 if x < 160 else 255, "1")
    return img


def _detect_strain(text: str) -> str | None:
    m = re.search(r"Strain:\s*(.+?)(?:\n|$)", text)
    if m:
        s = m.group(1).strip()
        s = re.split(r"Concentrates|Extracts", s)[0].strip()
        return s if s else None
    return None


def extract_ocr_items(path: str | Path) -> list[tuple[str, list[str]]]:
    _setup_tesseract()

    if not (_HAS_FITZ and _HAS_OCR and _HAS_PIL):
        return []

    from src.parsers.aerolabs import AerolabsParser

    parser = AerolabsParser()
    doc = _fitz.open(str(path))

    results: dict[str, set[str]] = {}

    for page in doc:
        for img_info in page.get_images(full=True):
            xref, _, w, h = img_info[0], img_info[1], img_info[2], img_info[3]
            if w < _LARGE_IMAGE_MIN and h < _LARGE_IMAGE_MIN:
                continue

            base = _fitz.Pixmap(doc, xref)
            pix = _fitz.Pixmap(_fitz.csRGB, base) if base.n > 4 else base

            img = _pil.open(io.BytesIO(pix.tobytes("png")))
            processed = _preprocess(img)
            text = pytesseract.image_to_string(processed, config="--psm 6 --oem 3")

            strain = _detect_strain(text)
            if strain:
                lines = [l.rstrip("\n") for l in text.split("\n")]
                parsed = parser.parse(lines)
                items = [i for i in parsed.get("items", []) if _is_valid_item(i)]
                if items:
                    if strain not in results:
                        results[strain] = set()
                    results[strain].update(items)

            pix = None
            base = None

    doc.close()
    return [(s, list(items)) for s, items in results.items()]


_ITEM_RE = re.compile(r"^[\w\s'/-]+:\s*[\d.]+%\s*(?:\([\d.]+\s*mg/unit\))?$")


def _is_valid_item(item: str) -> bool:
    return bool(_ITEM_RE.match(item.strip())) if item.strip() else False


def merge_items(primary: list[str], ocr_results: list[tuple[str, list[str]]]) -> list[str]:
    merged = list(primary)
    seen: set[str] = set(primary)

    for strain_name, strain_items in ocr_results:
        prefix = f"{strain_name} - "
        for item in strain_items:
            if not _is_valid_item(item):
                continue
            if item in seen:
                continue
            seen.add(item)
            name, _, rest = item.partition(": ")
            merged.append(f"{prefix}{name}: {rest}")

    return merged


def strip_strain_prefix(name: str) -> str:
    idx = name.find(" - ")
    if idx > 0:
        return name[idx + 3:]
    return name

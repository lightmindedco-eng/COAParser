from __future__ import annotations

import concurrent.futures
import hashlib
import io
import json
import os
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
_CACHE_DIR = Path.home() / ".cache" / "coa_parser"
_MAX_CACHE_ENTRIES = 50
_MAX_OCR_WORKERS = 3


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


def _is_definition_page(text: str) -> bool:
    return bool(re.search(r"Definitions?\s+of\s+Abbreviated", text, re.IGNORECASE))


def _ocr_image(args: tuple) -> tuple[int, str | None, str]:
    """OCR a single image by xref. Returns (xref, strain, text)."""
    doc_path, xref, cache_key = args

    # Check cache
    if cache_key:
        cached = _load_cache(cache_key)
        if cached is not None:
            return (xref, _detect_strain(cached), cached)

    doc = _fitz.open(str(doc_path))
    base = _fitz.Pixmap(doc, xref)
    pix = _fitz.Pixmap(_fitz.csRGB, base) if base.n > 4 else base
    img = _pil.open(io.BytesIO(pix.tobytes("png")))
    processed = _preprocess(img)
    text = pytesseract.image_to_string(processed, config="--psm 6 --oem 3")
    pix = None
    base = None
    doc.close()

    if cache_key:
        _save_cache(cache_key, text)

    return (xref, _detect_strain(text), text)


def _cache_path() -> Path:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR / "ocr_cache.json"


def _load_cache(key: str) -> str | None:
    try:
        data = json.loads(_cache_path().read_text(encoding="utf-8"))
        return data.get(key)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _save_cache(key: str, text: str) -> None:
    path = _cache_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (json.JSONDecodeError, OSError):
        data = {}
    data[key] = text
    # Evict oldest entries if over limit
    if len(data) > _MAX_CACHE_ENTRIES:
        sorted_keys = sorted(data, key=lambda k: 0)  # keep insertion order
        for old_k in sorted_keys[: len(data) - _MAX_CACHE_ENTRIES]:
            data.pop(old_k, None)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _cache_key(path: str | Path, xref: int) -> str | None:
    try:
        mtime = os.path.getmtime(path)
        raw = f"{Path(path).resolve()}::{xref}::{mtime:.0f}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]
    except OSError:
        return None


def extract_ocr_items(path: str | Path) -> list[tuple[str, list[str]]]:
    _setup_tesseract()

    if not (_HAS_FITZ and _HAS_OCR and _HAS_PIL):
        return []

    from src.parsers.aerolabs import AerolabsParser

    parser = AerolabsParser()
    doc = _fitz.open(str(path))

    # Collect image info
    image_args: list[tuple] = []
    for page in doc:
        for img_info in page.get_images(full=True):
            xref, _, w, h = img_info[0], img_info[1], img_info[2], img_info[3]
            if w < _LARGE_IMAGE_MIN and h < _LARGE_IMAGE_MIN:
                continue
            image_args.append((path, xref, _cache_key(path, xref)))
    doc.close()

    if not image_args:
        return []

    # OCR all images in parallel
    ocr_results: list[tuple[int, str | None, str]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=_MAX_OCR_WORKERS) as ex:
        ocr_results = list(ex.map(_ocr_image, image_args))

    # Parse each image's text
    results: dict[str, set[str]] = {}
    for xref, strain, text in ocr_results:
        if not strain or _is_definition_page(text):
            continue

        lines = [l.rstrip("\n") for l in text.split("\n")]
        lines = _split_two_column_lines(lines)
        parsed = parser.parse(lines)
        items = [i for i in parsed.get("items", []) if _is_valid_item(i)]
        if items:
            if strain not in results:
                results[strain] = set()
            results[strain].update(items)

    return [(s, list(items)) for s, items in results.items()]


def _load_terpenes() -> list[str]:
    """Load terpene names from data file, including OCR-variant forms."""
    data_dir = Path(__file__).resolve().parents[2] / "data"
    terp_path = data_dir / "terpenes.json"
    if not terp_path.exists():
        return []
    with open(terp_path, encoding="utf-8") as f:
        data = json.load(f)
    base = data.get("terpenes", [])
    seen: set[str] = set()
    for name in base:
        lower = name.lower()
        seen.add(lower)
        # Generate OCR variants for Greek letter prefixes
        if "β-" in lower or "beta-" in lower:
            seen.add(lower.replace("β-", "b-").replace("beta-", "b-"))
        if "α-" in lower or "alpha-" in lower:
            seen.add(lower.replace("α-", "a-").replace("alpha-", "a-"))
        if "γ-" in lower or "gamma-" in lower:
            seen.add(lower.replace("γ-", "y-").replace("gamma-", "y-"))
    return sorted(seen, key=len, reverse=True)


_TERPENES_CACHE: list[str] | None = None


def _get_terpenes() -> list[str]:
    global _TERPENES_CACHE
    if _TERPENES_CACHE is None:
        _TERPENES_CACHE = _load_terpenes()
    return _TERPENES_CACHE


def _split_two_column_lines(lines: list[str]) -> list[str]:
    """Split lines containing two terpene entries into separate lines."""
    terpenes = _get_terpenes()
    if not terpenes:
        return lines

    result: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            result.append(line)
            continue

        line_lower = stripped.lower()
        matches: list[tuple[int, int, str]] = []
        for terp in terpenes:
            for m in re.finditer(rf"\b{re.escape(terp)}\b", line_lower):
                matches.append((m.start(), m.end(), terp))

        if len(matches) < 2:
            result.append(line)
            continue

        matches.sort()
        gap = matches[1][0] - matches[0][1]
        if gap >= 5 and matches[0][0] < 35:
            left = stripped[:matches[1][0]].strip()
            right = stripped[matches[1][0]:].strip()
            result.append(left)
            result.append(right)
        else:
            result.append(line)

    return result


_ITEM_RE = re.compile(r"^[\w\s'/-]+:\s*(?:[\d.]+%|>ULOQ)(?:\s*\([\d.]+\s*mg/unit\))?$")


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

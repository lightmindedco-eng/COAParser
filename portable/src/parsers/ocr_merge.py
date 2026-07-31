from __future__ import annotations

import concurrent.futures
import hashlib
import io
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from tesseract_config import get_tesseract_path

logger = logging.getLogger(__name__)

_HAS_FITZ = False
_HAS_OCR = False
_HAS_PIL = False

_fitz = None
try:
    import fitz as _fitz_module
    _fitz = _fitz_module
    _HAS_FITZ = True
except Exception:
    logger.debug("fitz (PyMuPDF) not available")

_pytess = None
try:
    import pytesseract
    _HAS_OCR = True
except ImportError:
    logger.debug("pytesseract not available")

_pil = None
try:
    from PIL import Image, ImageEnhance
    _pil = Image
    _HAS_PIL = True
except ImportError:
    logger.debug("PIL/Pillow not available")

_LARGE_IMAGE_MIN = 1000
_CACHE_DIR = Path.home() / ".cache" / "coa_parser"
_MAX_CACHE_ENTRIES = 50
_MAX_OCR_WORKERS = 5


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
        logger.debug("Failed to inspect images in %s", path)
    return False


def _preprocess(img, scale: int = 3):
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
    """OCR a single image by pixmap bytes. Returns (xref, strain, text)."""
    xref, img_bytes, cache_key = args

    if cache_key:
        cached = _load_cache(cache_key)
        if cached is not None:
            return (xref, _detect_strain(cached), cached)

    img = _pil.open(io.BytesIO(img_bytes))
    processed = _preprocess(img)
    text = pytesseract.image_to_string(processed, config="--psm 6 --oem 1")

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
        sorted_keys = sorted(data, key=lambda k: 0)
        for old_k in sorted_keys[: len(data) - _MAX_CACHE_ENTRIES]:
            data.pop(old_k, None)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _batch_save_cache(updates: dict[str, str]) -> None:
    path = _cache_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (json.JSONDecodeError, OSError):
        data = {}
    data.update(updates)
    if len(data) > _MAX_CACHE_ENTRIES:
        sorted_keys = sorted(data, key=lambda k: 0)
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


def extract_ocr_items(path: str | Path, parser_name: str = "aerolabs") -> list[tuple[str, list[str]]]:
    _setup_tesseract()

    if not (_HAS_FITZ and _HAS_OCR and _HAS_PIL):
        return []

    _PARSER_MAP: dict[str, Any] = {}
    try:
        from src.parsers.aerolabs import AerolabsParser
        _PARSER_MAP["aerolabs"] = AerolabsParser
    except ImportError:
        pass
    try:
        from src.parsers.sunrise import SunriseParser
        _PARSER_MAP["sunrise"] = SunriseParser
    except ImportError:
        pass
    try:
        from src.parsers.highres import HighresParser
        _PARSER_MAP["highres"] = HighresParser
    except ImportError:
        pass
    try:
        from src.parsers.metis_qa import MetisQAParser
        _PARSER_MAP["metis_qa"] = MetisQAParser
    except ImportError:
        pass
    try:
        from src.parsers.confident import ConfidentParser
        _PARSER_MAP["confident"] = ConfidentParser
    except ImportError:
        pass
    try:
        from src.parsers.gateway import GatewayParser
        _PARSER_MAP["gateway"] = GatewayParser
    except ImportError:
        pass
    try:
        from src.parsers.greenleaf import GreenleafParser
        _PARSER_MAP["greenleaf"] = GreenleafParser
    except ImportError:
        pass
    try:
        from src.parsers.baseline import BaselineParser
        _PARSER_MAP["baseline"] = BaselineParser
    except ImportError:
        pass

    ParserCls = _PARSER_MAP.get(parser_name, _PARSER_MAP.get("aerolabs"))
    if ParserCls is None:
        return []
    parser = ParserCls()

    doc = _fitz.open(str(path))

    # Collect image data (pixmap bytes) in main thread — avoids per-image doc open
    image_args: list[tuple] = []
    for page in doc:
        for img_info in page.get_images(full=True):
            xref, _, w, h = img_info[0], img_info[1], img_info[2], img_info[3]
            if w < _LARGE_IMAGE_MIN and h < _LARGE_IMAGE_MIN:
                continue
            base = _fitz.Pixmap(doc, xref)
            pix = _fitz.Pixmap(_fitz.csRGB, base) if base.n > 4 else base
            img_bytes = pix.tobytes("png")
            pix = None
            base = None
            image_args.append((xref, img_bytes, _cache_key(path, xref)))
    doc.close()

    if not image_args:
        return []

    # OCR all images in parallel
    ocr_results: list[tuple[int, str | None, str]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=_MAX_OCR_WORKERS) as ex:
        ocr_results = list(ex.map(_ocr_image, image_args))

    # Batch-save cache entries
    cache_updates: dict[str, str] = {}
    for xref, strain, text in ocr_results:
        ck = _cache_key(path, xref)
        if ck:
            cache_updates[ck] = text
    if cache_updates:
        _batch_save_cache(cache_updates)

    # Parse each image's text. Keep each embedded COA's items separate; merge
    # them only when no analytes conflict (complementary pages of one strain).
    strain_sets: dict[str, list[set[str]]] = {}
    for xref, strain, text in ocr_results:
        if not strain or _is_definition_page(text):
            continue

        lines = [l.rstrip("\n") for l in text.split("\n")]
        if parser_name == "aerolabs":
            lines = _split_two_column_lines(lines)
        parsed = parser.parse(lines)
        items = [i for i in parsed.get("items", []) if _is_valid_item(i)]
        # OCR text is noisy; reject physically impossible values
        items = _filter_impossible_values(items)
        if items:
            strain_sets.setdefault(strain, []).append(set(items))

    results: list[tuple[str, list[str]]] = []
    for strain, item_sets in strain_sets.items():
        merged_groups: list[set[str]] = []
        for iset in item_sets:
            for group in merged_groups:
                if not _item_conflicts(group, iset):
                    group |= iset
                    break
            else:
                merged_groups.append(set(iset))
        if len(merged_groups) == 1:
            results.append((strain, sorted(merged_groups[0])))
        else:
            for idx, group in enumerate(merged_groups, 1):
                results.append((f"{strain} ({idx})", sorted(group)))

    return results


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


_ITEM_RE = re.compile(r"^[\w\s'/-]+:\s*[\d.]+%\s*(?:\([\d.]+\s*(?:mg/unit|mg/g)\))?$")


def _item_name(item: str) -> str:
    return item.split(":")[0].strip().lower()


def _item_conflicts(a: set[str], b: set[str]) -> bool:
    """True if the same analyte appears with different values in both sets."""
    a_map = {_item_name(i): i for i in a}
    for item in b:
        name = _item_name(item)
        if name in a_map and a_map[name] != item:
            return True
    return False


def _is_valid_item(item: str) -> bool:
    return bool(_ITEM_RE.match(item.strip())) if item.strip() else False


def _filter_impossible_values(items: list[str]) -> list[str]:
    _MAX_PCT = 100.0
    out: list[str] = []
    for item in items:
        m = re.search(r":\s*(\d+\.?\d*)%", item)
        if m:
            pct = float(m.group(1))
            if pct > _MAX_PCT:
                continue
        out.append(item)
    return out


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

"""PDF-to-image rendering helpers."""

from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image

logger = logging.getLogger("coa_parser")

MAX_WEBP_DIM = 16383

_fitz = None
try:
    import fitz  # type: ignore

    _fitz = fitz
except Exception as exc:  # pragma: no cover
    logger.debug("fitz (PyMuPDF) not available: %s", exc)


def render_pdf_webp(
    pdf_path: str | Path,
    output_path: str | Path,
    zoom: float = 2.0,
    quality: int = 85,
) -> Path | None:
    """Render every page of a PDF stacked vertically into a single WEBP.

    Returns the output path on success, or None if rendering is unavailable
    or the PDF has no renderable pages.
    """
    if _fitz is None:
        logger.warning("PyMuPDF unavailable; cannot render %s to WEBP", Path(pdf_path).name)
        return None

    pdf = Path(pdf_path)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    matrix = _fitz.Matrix(zoom, zoom)
    pages: list[Image.Image] = []
    doc = _fitz.open(str(pdf))
    try:
        for page in doc:
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            pages.append(img)
    finally:
        doc.close()

    if not pages:
        return None

    width = max(p.width for p in pages)
    gap = 12
    height = sum(p.height for p in pages) + gap * (len(pages) - 1)

    canvas = Image.new("RGB", (width, height), "white")
    y = 0
    for p in pages:
        canvas.paste(p, ((width - p.width) // 2, y))
        y += p.height + gap

    if width > MAX_WEBP_DIM or height > MAX_WEBP_DIM:
        scale = MAX_WEBP_DIM / max(width, height)
        canvas = canvas.resize(
            (max(1, int(width * scale)), max(1, int(height * scale))),
            Image.LANCZOS,
        )

    canvas.save(out, format="WEBP", quality=quality)
    return out

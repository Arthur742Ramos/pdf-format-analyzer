"""PDF page rendering using PyMuPDF (fitz)."""

from __future__ import annotations

import logging
from pathlib import Path

import fitz  # PyMuPDF

from pdf_format_analyzer.models import PageImage

logger = logging.getLogger(__name__)


def render_pages(
    pdf_path: str | Path,
    *,
    dpi: int = 150,
    max_pages: int | None = None,
    page_range: tuple[int, int] | None = None,
) -> list[PageImage]:
    """Render PDF pages to PNG images.

    Args:
        pdf_path: Path to the PDF file.
        dpi: Resolution for rendering (default 150).
        max_pages: Maximum number of pages to render (None = all).
        page_range: Optional (start, end) 1-based inclusive page range.

    Returns:
        List of PageImage objects with rendered PNG bytes.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    doc = fitz.open(str(pdf_path))
    total = doc.page_count
    logger.info("Opened PDF with %d pages: %s", total, pdf_path.name)

    # Determine which pages to render
    if page_range:
        start = max(0, page_range[0] - 1)
        end = min(total, page_range[1])
        page_indices = list(range(start, end))
    else:
        page_indices = list(range(total))

    if max_pages and len(page_indices) > max_pages:
        page_indices = page_indices[:max_pages]

    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)
    pages: list[PageImage] = []

    for idx in page_indices:
        page = doc[idx]
        pix = page.get_pixmap(matrix=matrix)
        image_bytes = pix.tobytes("png")

        pages.append(
            PageImage(
                page_number=idx + 1,
                image_bytes=image_bytes,
                width=pix.width,
                height=pix.height,
                dpi=dpi,
            )
        )
        logger.debug("Rendered page %d (%dx%d)", idx + 1, pix.width, pix.height)

    doc.close()
    logger.info("Rendered %d pages at %d DPI", len(pages), dpi)
    return pages


def get_page_count(pdf_path: str | Path) -> int:
    """Return the total number of pages in a PDF."""
    doc = fitz.open(str(pdf_path))
    count = doc.page_count
    doc.close()
    return count

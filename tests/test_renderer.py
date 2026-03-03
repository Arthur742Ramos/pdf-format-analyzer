"""Tests for the PDF renderer module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pdf_format_analyzer.models import PageImage
from pdf_format_analyzer.renderer import get_page_count, render_pages


class FakePixmap:
    """Mock for fitz.Pixmap."""

    def __init__(self, width: int = 300, height: int = 400):
        self.width = width
        self.height = height

    def tobytes(self, fmt: str = "png") -> bytes:
        # Minimal valid PNG (1x1 pixel)
        return (
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde"
            b"\x00\x00\x00\x0cIDATx"
            b"\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
            b"\x00\x00\x00\x00IEND\xaeB`\x82"
        )


class FakePage:
    """Mock for fitz.Page."""

    def get_pixmap(self, matrix=None):
        return FakePixmap(300, 400)


class FakeDocument:
    """Mock for fitz.Document."""

    def __init__(self, path: str, page_count: int = 5):
        self._path = path
        self.page_count = page_count

    def __getitem__(self, idx: int) -> FakePage:
        if idx < 0 or idx >= self.page_count:
            raise IndexError(f"page {idx} out of range")
        return FakePage()

    def close(self) -> None:
        pass


@patch("pdf_format_analyzer.renderer.fitz")
def test_render_pages_returns_page_images(mock_fitz, tmp_path):
    """render_pages returns a list of PageImage objects."""
    pdf_file = tmp_path / "test.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 fake")

    mock_fitz.open.return_value = FakeDocument(str(pdf_file), page_count=3)
    mock_fitz.Matrix.return_value = MagicMock()

    pages = render_pages(pdf_file, dpi=150)

    assert len(pages) == 3
    for i, page in enumerate(pages):
        assert isinstance(page, PageImage)
        assert page.page_number == i + 1
        assert page.width == 300
        assert page.height == 400
        assert page.dpi == 150
        assert len(page.image_bytes) > 0


@patch("pdf_format_analyzer.renderer.fitz")
def test_render_pages_max_pages(mock_fitz, tmp_path):
    """max_pages limits the number of rendered pages."""
    pdf_file = tmp_path / "test.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 fake")

    mock_fitz.open.return_value = FakeDocument(str(pdf_file), page_count=10)
    mock_fitz.Matrix.return_value = MagicMock()

    pages = render_pages(pdf_file, max_pages=3)
    assert len(pages) == 3
    assert pages[0].page_number == 1
    assert pages[2].page_number == 3


@patch("pdf_format_analyzer.renderer.fitz")
def test_render_pages_page_range(mock_fitz, tmp_path):
    """page_range selects specific pages."""
    pdf_file = tmp_path / "test.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 fake")

    mock_fitz.open.return_value = FakeDocument(str(pdf_file), page_count=10)
    mock_fitz.Matrix.return_value = MagicMock()

    pages = render_pages(pdf_file, page_range=(3, 5))
    assert len(pages) == 3
    assert pages[0].page_number == 3
    assert pages[1].page_number == 4
    assert pages[2].page_number == 5


def test_render_pages_missing_file():
    """render_pages raises FileNotFoundError for missing PDFs."""
    with pytest.raises(FileNotFoundError):
        render_pages(Path("/nonexistent/test.pdf"))


@patch("pdf_format_analyzer.renderer.fitz")
def test_get_page_count(mock_fitz, tmp_path):
    """get_page_count returns total pages."""
    pdf_file = tmp_path / "test.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 fake")

    mock_fitz.open.return_value = FakeDocument(str(pdf_file), page_count=42)
    assert get_page_count(pdf_file) == 42


@patch("pdf_format_analyzer.renderer.fitz")
def test_render_custom_dpi(mock_fitz, tmp_path):
    """DPI is correctly stored on rendered pages."""
    pdf_file = tmp_path / "test.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 fake")

    mock_fitz.open.return_value = FakeDocument(str(pdf_file), page_count=1)
    mock_fitz.Matrix.return_value = MagicMock()

    pages = render_pages(pdf_file, dpi=300)
    assert pages[0].dpi == 300

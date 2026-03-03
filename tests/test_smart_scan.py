"""Tests for the smart scan module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from pdf_format_analyzer.smart_scan import (
    log_guided_pages,
    sample_pages,
    smart_page_selection,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

LOG_WITH_WARNINGS = """\
This is pdfTeX
[1]
[2]
Overfull \\hbox (5.0pt too wide) in paragraph at lines 100--101
[3]
[4]
Overfull \\hbox (12.0pt too wide) in paragraph at lines 200--205
[5]
[6]
[7]
Underfull \\hbox (badness 10000) in paragraph at lines 300--310
[8]
[9]
[10]
"""


@pytest.fixture()
def log_file(tmp_path: Path) -> Path:
    p = tmp_path / "thesis.log"
    p.write_text(LOG_WITH_WARNINGS, encoding="utf-8")
    return p


@pytest.fixture()
def empty_log(tmp_path: Path) -> Path:
    p = tmp_path / "clean.log"
    p.write_text("This is pdfTeX\n[1]\n[2]\n[3]\n", encoding="utf-8")
    return p


@pytest.fixture()
def fake_pdf(tmp_path: Path) -> Path:
    p = tmp_path / "thesis.pdf"
    p.write_bytes(b"%PDF-1.4 fake")
    return p


# ---------------------------------------------------------------------------
# Tests: log_guided_pages
# ---------------------------------------------------------------------------


class TestLogGuidedPages:
    def test_returns_unique_sorted_pages(self, log_file: Path) -> None:
        pages = log_guided_pages(log_file)
        assert pages == sorted(set(pages))
        assert len(pages) > 0

    def test_returns_correct_pages(self, log_file: Path) -> None:
        pages = log_guided_pages(log_file)
        # overfull at page 2, overfull at page 4, underfull at page 7
        assert 2 in pages
        assert 4 in pages
        assert 7 in pages

    def test_empty_log_returns_empty(self, empty_log: Path) -> None:
        pages = log_guided_pages(empty_log)
        assert pages == []


# ---------------------------------------------------------------------------
# Tests: sample_pages
# ---------------------------------------------------------------------------


class TestSamplePages:
    def test_includes_first_and_last(self) -> None:
        pages = sample_pages(100, sample_rate=20)
        assert 1 in pages
        assert 100 in pages

    def test_correct_sampling(self) -> None:
        pages = sample_pages(100, sample_rate=25)
        assert pages == [1, 26, 51, 76, 100]

    def test_single_page(self) -> None:
        assert sample_pages(1) == [1]

    def test_zero_pages(self) -> None:
        assert sample_pages(0) == []


# ---------------------------------------------------------------------------
# Tests: smart_page_selection
# ---------------------------------------------------------------------------


class TestSmartPageSelection:
    @patch("pdf_format_analyzer.smart_scan.get_page_count", return_value=100)
    def test_full_strategy(self, _mock, fake_pdf: Path) -> None:
        pages = smart_page_selection(fake_pdf, strategy="full")
        assert len(pages) == 100
        assert pages[0] == 1
        assert pages[-1] == 100

    @patch("pdf_format_analyzer.smart_scan.get_page_count", return_value=100)
    def test_sample_strategy(self, _mock, fake_pdf: Path) -> None:
        pages = smart_page_selection(fake_pdf, strategy="sample", sample_rate=50)
        assert 1 in pages
        assert 100 in pages
        assert len(pages) < 100

    @patch("pdf_format_analyzer.smart_scan.get_page_count", return_value=548)
    def test_log_strategy(self, _mock, fake_pdf: Path, log_file: Path) -> None:
        pages = smart_page_selection(fake_pdf, log_path=log_file, strategy="log")
        assert len(pages) < 548
        assert all(isinstance(p, int) for p in pages)

    @patch("pdf_format_analyzer.smart_scan.get_page_count", return_value=548)
    def test_auto_with_log_uses_log(self, _mock, fake_pdf: Path, log_file: Path) -> None:
        pages = smart_page_selection(fake_pdf, log_path=log_file, strategy="auto")
        assert len(pages) < 548

    @patch("pdf_format_analyzer.smart_scan.get_page_count", return_value=100)
    def test_auto_without_log_falls_back_to_full(self, _mock, fake_pdf: Path) -> None:
        pages = smart_page_selection(fake_pdf, strategy="auto")
        assert len(pages) == 100

    @patch("pdf_format_analyzer.smart_scan.get_page_count", return_value=100)
    def test_log_strategy_requires_log_path(self, _mock, fake_pdf: Path) -> None:
        with pytest.raises(ValueError, match="--log is required"):
            smart_page_selection(fake_pdf, strategy="log")

    @patch("pdf_format_analyzer.smart_scan.get_page_count", return_value=100)
    def test_diff_strategy_requires_source(self, _mock, fake_pdf: Path) -> None:
        with pytest.raises(ValueError, match="--source is required"):
            smart_page_selection(fake_pdf, strategy="diff")

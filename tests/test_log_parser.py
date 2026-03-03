"""Tests for the LaTeX log parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from pdf_format_analyzer.log_parser import parse_latex_log
from pdf_format_analyzer.models import Severity

# ---------------------------------------------------------------------------
# Realistic LaTeX log snippet used by multiple tests
# ---------------------------------------------------------------------------
LOG_SNIPPET = """\
This is pdfTeX, Version 3.141592653-2.6-1.40.25 (TeX Live 2023)
entering extended mode
(./main.tex
LaTeX2e <2023-11-01> patch level 1

[1]
[2]
[3]

Overfull \\hbox (6.71902pt too wide) in paragraph at lines 841--842
[]\\T1/lmr/m/n/10 Some long text here

[4]
[5]

Underfull \\hbox (badness 10000) in paragraph at lines 910--915
[]\\T1/lmr/m/n/10

[6]

Overfull \\hbox (15.2pt too wide) in paragraph at lines 1200--1205
[]\\T1/lmr/m/n/10 Another wide box

[7]

Overfull \\vbox (3.5pt too high) has occurred while \\output is active

[8]

Underfull \\vbox (badness 10000) has occurred while \\output is active

[9]
[10]

LaTeX Font Warning: Font shape `T1/lmr/m/sc' undefined
(Font)              using `T1/lmr/m/n' instead on input line 1500.

[11]
[12]

LaTeX Warning: Reference `fig:missing' on page 12 undefined

[13]
[14]
)
Output written on main.pdf (14 pages, 524288 bytes).
"""


@pytest.fixture()
def log_file(tmp_path: Path) -> Path:
    """Write the log snippet to a temp file."""
    p = tmp_path / "main.log"
    p.write_text(LOG_SNIPPET, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestOverfullHbox:
    def test_detects_overfull_hbox(self, log_file: Path) -> None:
        warnings = parse_latex_log(log_file)
        overfull = [w for w in warnings if w.warning_type == "overfull_hbox"]
        assert len(overfull) == 2

    def test_extracts_amount(self, log_file: Path) -> None:
        warnings = parse_latex_log(log_file)
        overfull = [w for w in warnings if w.warning_type == "overfull_hbox"]
        amounts = sorted(w.amount for w in overfull if w.amount is not None)
        assert amounts == pytest.approx([6.71902, 15.2])

    def test_extracts_line_number(self, log_file: Path) -> None:
        warnings = parse_latex_log(log_file)
        overfull = [w for w in warnings if w.warning_type == "overfull_hbox"]
        lines = sorted(w.line_number for w in overfull)
        assert lines == [841, 1200]

    def test_maps_page_number(self, log_file: Path) -> None:
        warnings = parse_latex_log(log_file)
        overfull = sorted(
            [w for w in warnings if w.warning_type == "overfull_hbox"],
            key=lambda w: w.line_number,
        )
        # First overfull is after [3], so page 3
        assert overfull[0].page_number == 3
        # Second overfull is after [6], so page 6
        assert overfull[1].page_number == 6

    def test_severity_based_on_amount(self, log_file: Path) -> None:
        warnings = parse_latex_log(log_file)
        overfull = sorted(
            [w for w in warnings if w.warning_type == "overfull_hbox"],
            key=lambda w: w.amount or 0,
        )
        assert overfull[0].severity == Severity.WARNING  # 6.71pt
        assert overfull[1].severity == Severity.ERROR  # 15.2pt > 10


class TestUnderfullHbox:
    def test_detects_underfull_hbox(self, log_file: Path) -> None:
        warnings = parse_latex_log(log_file)
        underfull = [w for w in warnings if w.warning_type == "underfull_hbox"]
        assert len(underfull) == 1
        assert underfull[0].page_number == 5
        assert underfull[0].line_number == 910


class TestVboxWarnings:
    def test_detects_overfull_vbox(self, log_file: Path) -> None:
        warnings = parse_latex_log(log_file)
        ovbox = [w for w in warnings if w.warning_type == "overfull_vbox"]
        assert len(ovbox) == 1
        assert ovbox[0].amount == pytest.approx(3.5)
        assert ovbox[0].page_number == 7

    def test_detects_underfull_vbox(self, log_file: Path) -> None:
        warnings = parse_latex_log(log_file)
        uvbox = [w for w in warnings if w.warning_type == "underfull_vbox"]
        assert len(uvbox) == 1
        assert uvbox[0].page_number == 8


class TestFontWarnings:
    def test_detects_font_warning(self, log_file: Path) -> None:
        warnings = parse_latex_log(log_file)
        font = [w for w in warnings if w.warning_type == "font"]
        assert len(font) >= 1
        assert font[0].severity == Severity.INFO
        assert font[0].line_number == 1500


class TestMissingRef:
    def test_detects_missing_reference(self, log_file: Path) -> None:
        warnings = parse_latex_log(log_file)
        refs = [w for w in warnings if w.warning_type == "missing_ref"]
        assert len(refs) == 1
        assert refs[0].page_number == 12
        assert "fig:missing" in refs[0].message


class TestPageMarkers:
    def test_page_numbers_extracted(self, log_file: Path) -> None:
        """All warnings should have a page number from [N] markers."""
        warnings = parse_latex_log(log_file)
        # Every warning in our snippet has a deterministic page
        for w in warnings:
            assert w.page_number is not None, f"Missing page for: {w.message}"


class TestEdgeCases:
    def test_missing_log_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            parse_latex_log(tmp_path / "nonexistent.log")

    def test_empty_log(self, tmp_path: Path) -> None:
        p = tmp_path / "empty.log"
        p.write_text("", encoding="utf-8")
        assert parse_latex_log(p) == []

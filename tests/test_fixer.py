"""Tests for the auto-fix engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from pdf_format_analyzer.fixer import (
    apply_fixes,
    fix_overfull_equation,
    fix_overfull_includegraphics,
    fix_overfull_tikzcd,
    fix_texttt_paths,
    suggest_fixes_for_line,
)
from pdf_format_analyzer.models import (
    IssueCategory,
    MappedIssue,
    PageIssue,
    Severity,
    SourceLocation,
)


class TestFixTikzcd:
    """Tests for tikzcd auto-fix."""

    def test_wraps_tikzcd_in_adjustbox(self):
        lines = [
            r"\begin{tikzcd}",
            r"A \arrow[r] & B \arrow[r] & C \arrow[r] & D",
            r"\end{tikzcd}",
        ]
        fix = fix_overfull_tikzcd(lines[0], lines, 0)
        assert fix is not None
        assert "adjustbox" in fix.new_text
        assert r"\begin{tikzcd}" in fix.new_text
        assert r"\end{tikzcd}" in fix.new_text

    def test_skips_already_wrapped(self):
        lines = [
            r"\adjustbox{max width=\textwidth}{",
            r"\begin{tikzcd}",
            r"A \arrow[r] & B",
            r"\end{tikzcd}",
            r"}",
        ]
        fix = fix_overfull_tikzcd(lines[1], lines, 1)
        assert fix is None

    def test_no_match_returns_none(self):
        lines = [r"Just a normal line of text."]
        fix = fix_overfull_tikzcd(lines[0], lines, 0)
        assert fix is None


class TestFixEquation:
    """Tests for equation auto-fix."""

    def test_wraps_equation_in_adjustbox(self):
        lines = [
            r"\begin{equation}",
            r"a + b + c + d + e + f + g + h = z",
            r"\end{equation}",
        ]
        fix = fix_overfull_equation(lines[0], lines, 0)
        assert fix is not None
        assert "adjustbox" in fix.new_text

    def test_wraps_align_in_adjustbox(self):
        lines = [
            r"\begin{align*}",
            r"x &= a + b \\",
            r"y &= c + d",
            r"\end{align*}",
        ]
        fix = fix_overfull_equation(lines[0], lines, 0)
        assert fix is not None
        assert "adjustbox" in fix.new_text

    def test_skips_already_wrapped(self):
        lines = [
            r"\resizebox{\textwidth}{!}{",
            r"\begin{equation}",
            r"x = y",
            r"\end{equation}",
            r"}",
        ]
        fix = fix_overfull_equation(lines[1], lines, 1)
        assert fix is None


class TestFixTexttt:
    """Tests for texttt path breaking."""

    def test_adds_allowbreak_to_paths(self):
        line = r"\texttt{/usr/local/bin/my-program}"
        fix = fix_texttt_paths(line)
        assert fix is not None
        assert r"\allowbreak" in fix.new_text
        assert r"\texttt{" in fix.new_text

    def test_handles_backslash_paths(self):
        line = r"\texttt{C:\Users\docs\file.txt}"
        fix = fix_texttt_paths(line)
        assert fix is not None
        assert r"\allowbreak" in fix.new_text

    def test_skips_already_broken(self):
        line = r"\texttt{/usr/\allowbreak local/\allowbreak bin}"
        fix = fix_texttt_paths(line)
        assert fix is None

    def test_skips_no_path(self):
        line = r"\texttt{simple-text}"
        fix = fix_texttt_paths(line)
        assert fix is None


class TestFixIncludegraphics:
    """Tests for includegraphics auto-fix."""

    def test_adds_width_to_bare_includegraphics(self):
        line = r"\includegraphics{figure.png}"
        fix = fix_overfull_includegraphics(line)
        assert fix is not None
        assert r"width=\textwidth" in fix.new_text

    def test_adds_width_to_existing_options(self):
        line = r"\includegraphics[height=5cm]{figure.png}"
        fix = fix_overfull_includegraphics(line)
        assert fix is not None
        assert r"width=\textwidth" in fix.new_text

    def test_skips_if_width_present(self):
        line = r"\includegraphics[width=0.8\textwidth]{figure.png}"
        fix = fix_overfull_includegraphics(line)
        assert fix is None

    def test_skips_if_scale_present(self):
        line = r"\includegraphics[scale=0.5]{figure.png}"
        fix = fix_overfull_includegraphics(line)
        assert fix is None


class TestSuggestFixes:
    """Tests for the suggest_fixes_for_line dispatcher."""

    def test_suggests_for_overfull_tikzcd(self):
        lines = [
            r"\begin{tikzcd}",
            r"A \arrow[r] & B",
            r"\end{tikzcd}",
        ]
        fixes = suggest_fixes_for_line(lines[0], lines, 0, IssueCategory.OVERFULL_BOX)
        assert len(fixes) >= 1

    def test_no_suggestions_for_clean_line(self):
        lines = ["This is a perfectly normal paragraph."]
        fixes = suggest_fixes_for_line(lines[0], lines, 0, IssueCategory.OVERFULL_BOX)
        assert fixes == []


class TestApplyFixes:
    """Tests for the full apply_fixes pipeline."""

    def test_applies_fix_to_file(self, tmp_path):
        # Create a source file with a wide tikzcd
        source = tmp_path / "chapter.tex"
        source.write_text(
            "Some text before.\n"
            "\\begin{tikzcd}\n"
            "A \\arrow[r] & B \\arrow[r] & C \\arrow[r] & D\n"
            "\\end{tikzcd}\n"
            "Some text after.\n",
            encoding="utf-8",
        )

        issues = [
            MappedIssue(
                issue=PageIssue(
                    page_number=1,
                    severity=Severity.WARNING,
                    category=IssueCategory.OVERFULL_BOX,
                    description="Overfull tikzcd",
                ),
                source=SourceLocation(
                    file_path=Path("chapter.tex"),
                    line_number=2,
                ),
            )
        ]

        fixes = apply_fixes(issues, tmp_path)

        assert len(fixes) >= 1
        content = source.read_text(encoding="utf-8")
        assert "adjustbox" in content
        assert "Some text before." in content
        assert "Some text after." in content

    def test_skips_missing_files(self, tmp_path):
        issues = [
            MappedIssue(
                issue=PageIssue(
                    page_number=1,
                    severity=Severity.WARNING,
                    category=IssueCategory.OVERFULL_BOX,
                    description="test",
                ),
                source=SourceLocation(
                    file_path=Path("nonexistent.tex"),
                    line_number=1,
                ),
            )
        ]

        fixes = apply_fixes(issues, tmp_path)
        assert fixes == []

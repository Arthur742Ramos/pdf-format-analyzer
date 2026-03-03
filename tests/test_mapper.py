"""Tests for the SyncTeX mapper module."""

from __future__ import annotations

import gzip

from pdf_format_analyzer.mapper import SyncTeXData, find_synctex_file, map_issues
from pdf_format_analyzer.models import (
    BoundingBox,
    IssueCategory,
    PageIssue,
    Severity,
)


def _make_issue(
    page: int = 1,
    category: IssueCategory = IssueCategory.OVERFULL_BOX,
    bbox: BoundingBox | None = None,
) -> PageIssue:
    return PageIssue(
        page_number=page,
        severity=Severity.WARNING,
        category=category,
        description="Test issue",
        bounding_box=bbox,
    )


SAMPLE_SYNCTEX = """\
SyncTeX Version:1
Input:1:./main.tex
Input:2:./chapters/intro.tex
Input:3:./chapters/methods.tex
Output:./main.pdf
Magnification:1000
Unit:1
X Offset:0
Y Offset:0
Content:
{1
[1,1:10,0:3276800,5242880,4718592
(1,1:15,3:3276800,5242880,4718592
(1,2:5,0:3276800,6291456,4718592
}1
{2
[2,2:20,0:3276800,5242880,4718592
(2,3:8,0:3276800,5242880,4718592
}2
"""


class TestSyncTeXData:
    """Tests for SyncTeX parsing."""

    def test_parse_plaintext(self, tmp_path):
        synctex_file = tmp_path / "main.synctex"
        synctex_file.write_text(SAMPLE_SYNCTEX, encoding="utf-8")

        data = SyncTeXData.parse(synctex_file)
        assert len(data.inputs) == 3
        assert data.inputs[1] == "./main.tex"
        assert data.inputs[2] == "./chapters/intro.tex"
        assert data.inputs[3] == "./chapters/methods.tex"
        assert len(data.records) > 0

    def test_parse_gzipped(self, tmp_path):
        synctex_file = tmp_path / "main.synctex.gz"
        with gzip.open(synctex_file, "wt", encoding="utf-8") as f:
            f.write(SAMPLE_SYNCTEX)

        data = SyncTeXData.parse(synctex_file)
        assert len(data.inputs) == 3
        assert len(data.records) > 0

    def test_parse_records_have_page(self, tmp_path):
        synctex_file = tmp_path / "main.synctex"
        synctex_file.write_text(SAMPLE_SYNCTEX, encoding="utf-8")

        data = SyncTeXData.parse(synctex_file)
        pages = {r["page"] for r in data.records}
        assert 1 in pages
        assert 2 in pages


class TestFindSynctexFile:
    """Tests for find_synctex_file."""

    def test_finds_gz(self, tmp_path):
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"")
        gz = tmp_path / "doc.synctex.gz"
        gz.write_bytes(b"")

        result = find_synctex_file(pdf)
        assert result == gz

    def test_finds_plain(self, tmp_path):
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"")
        st = tmp_path / "doc.synctex"
        st.write_text("", encoding="utf-8")

        result = find_synctex_file(pdf)
        assert result == st

    def test_returns_none_when_missing(self, tmp_path):
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"")

        result = find_synctex_file(pdf)
        assert result is None

    def test_prefers_gz_over_plain(self, tmp_path):
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"")
        gz = tmp_path / "doc.synctex.gz"
        gz.write_bytes(b"")
        st = tmp_path / "doc.synctex"
        st.write_text("", encoding="utf-8")

        result = find_synctex_file(pdf)
        assert result == gz


class TestMapIssues:
    """Tests for map_issues integration."""

    def test_maps_with_synctex(self, tmp_path):
        pdf = tmp_path / "main.pdf"
        pdf.write_bytes(b"")
        synctex_file = tmp_path / "main.synctex"
        synctex_file.write_text(SAMPLE_SYNCTEX, encoding="utf-8")

        issues = [_make_issue(page=1), _make_issue(page=2)]
        mapped = map_issues(issues, pdf, source_dir=tmp_path)

        assert len(mapped) == 2
        # At least one should have a source location
        has_source = any(m.source is not None for m in mapped)
        assert has_source

    def test_maps_without_synctex(self, tmp_path):
        pdf = tmp_path / "main.pdf"
        pdf.write_bytes(b"")

        issues = [_make_issue(page=1)]
        mapped = map_issues(issues, pdf)

        assert len(mapped) == 1
        assert mapped[0].source is None

    def test_maps_all_issues_even_without_match(self, tmp_path):
        pdf = tmp_path / "main.pdf"
        pdf.write_bytes(b"")
        synctex_file = tmp_path / "main.synctex"
        synctex_file.write_text(SAMPLE_SYNCTEX, encoding="utf-8")

        issues = [_make_issue(page=999)]  # page not in synctex
        mapped = map_issues(issues, pdf, source_dir=tmp_path)

        assert len(mapped) == 1
        assert mapped[0].source is None

"""Tests for the analyzer module."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pdf_format_analyzer.analyzer import _build_vision_messages, _parse_issues_response
from pdf_format_analyzer.models import IssueCategory, PageImage, Severity


def _make_page(page_number: int = 1) -> PageImage:
    return PageImage(
        page_number=page_number,
        image_bytes=b"\x89PNG\r\n\x1a\n" + b"\x00" * 20,
        width=300,
        height=400,
        dpi=150,
    )


class TestParseIssuesResponse:
    """Tests for _parse_issues_response."""

    def test_valid_json_array(self):
        pages = [_make_page(1), _make_page(2)]
        raw = json.dumps([
            {
                "page_number": 1,
                "severity": "error",
                "category": "overfull_box",
                "description": "Text extends into right margin",
                "confidence": 0.95,
            },
            {
                "page_number": 2,
                "severity": "warning",
                "category": "widow",
                "description": "Single line at top of page",
                "confidence": 0.7,
            },
        ])
        issues = _parse_issues_response(raw, pages)
        assert len(issues) == 2
        assert issues[0].severity == Severity.ERROR
        assert issues[0].category == IssueCategory.OVERFULL_BOX
        assert issues[0].page_number == 1
        assert issues[1].severity == Severity.WARNING
        assert issues[1].category == IssueCategory.WIDOW

    def test_with_bounding_box(self):
        pages = [_make_page(1)]
        raw = json.dumps([{
            "page_number": 1,
            "severity": "error",
            "category": "cutoff",
            "description": "Figure cut off",
            "bounding_box": {"x": 0.1, "y": 0.8, "width": 0.8, "height": 0.15},
            "confidence": 0.9,
        }])
        issues = _parse_issues_response(raw, pages)
        assert len(issues) == 1
        assert issues[0].bounding_box is not None
        assert issues[0].bounding_box.x == 0.1
        assert issues[0].bounding_box.y == 0.8

    def test_markdown_fenced_json(self):
        pages = [_make_page(1)]
        raw = '```json\n[{"page_number": 1, "severity": "info", "category": "bad_spacing", "description": "Extra space"}]\n```'
        issues = _parse_issues_response(raw, pages)
        assert len(issues) == 1
        assert issues[0].category == IssueCategory.BAD_SPACING

    def test_empty_array(self):
        pages = [_make_page(1)]
        issues = _parse_issues_response("[]", pages)
        assert issues == []

    def test_invalid_json(self):
        pages = [_make_page(1)]
        issues = _parse_issues_response("not valid json at all", pages)
        assert issues == []

    def test_unknown_category_falls_back(self):
        pages = [_make_page(1)]
        raw = json.dumps([{
            "page_number": 1,
            "severity": "warning",
            "category": "unknown_thing",
            "description": "Something weird",
        }])
        issues = _parse_issues_response(raw, pages)
        assert len(issues) == 1
        assert issues[0].category == IssueCategory.OTHER

    def test_filters_invalid_page_numbers(self):
        pages = [_make_page(1)]
        raw = json.dumps([
            {"page_number": 1, "severity": "error", "category": "cutoff", "description": "ok"},
            {"page_number": 99, "severity": "error", "category": "cutoff", "description": "bad page"},
        ])
        issues = _parse_issues_response(raw, pages)
        assert len(issues) == 1
        assert issues[0].page_number == 1

    def test_single_object_wrapped(self):
        """A single object (not array) is handled gracefully."""
        pages = [_make_page(1)]
        raw = json.dumps({
            "page_number": 1,
            "severity": "warning",
            "category": "orphan",
            "description": "Orphaned line",
        })
        issues = _parse_issues_response(raw, pages)
        assert len(issues) == 1


class TestBuildVisionMessages:
    """Tests for _build_vision_messages."""

    def test_builds_messages_with_images(self):
        pages = [_make_page(1), _make_page(2)]
        messages = _build_vision_messages(pages)

        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

        # User message should have text + image parts
        content = messages[1]["content"]
        assert isinstance(content, list)
        # 1 intro text + 2 pages * (1 label text + 1 image) = 5 parts
        assert len(content) == 5
        assert content[0]["type"] == "text"
        assert content[1]["type"] == "text"
        assert "Page 1" in content[1]["text"]
        assert content[2]["type"] == "image_url"
        assert content[2]["image_url"]["url"].startswith("data:image/png;base64,")

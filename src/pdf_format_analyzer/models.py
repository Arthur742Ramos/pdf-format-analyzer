"""Pydantic models for PDF format analysis results."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class Severity(str, Enum):
    """Issue severity levels."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class IssueCategory(str, Enum):
    """Categories of formatting issues."""

    OVERFULL_BOX = "overfull_box"
    UNDERFULL_BOX = "underfull_box"
    ORPHAN = "orphan"
    WIDOW = "widow"
    MISALIGNED = "misaligned"
    OVERLAP = "overlap"
    CUTOFF = "cutoff"
    BAD_SPACING = "bad_spacing"
    TABLE_BREAK = "table_break"
    EQUATION_BREAK = "equation_break"
    MARGIN_VIOLATION = "margin_violation"
    OTHER = "other"


class BoundingBox(BaseModel):
    """Bounding box for a detected issue on a page (normalized 0-1 coordinates)."""

    x: float = Field(ge=0, le=1, description="Left edge (0=left margin)")
    y: float = Field(ge=0, le=1, description="Top edge (0=top margin)")
    width: float = Field(ge=0, le=1)
    height: float = Field(ge=0, le=1)


class PageImage(BaseModel):
    """A rendered page image."""

    page_number: int = Field(ge=1)
    image_bytes: bytes
    width: int
    height: int
    dpi: int = 150

    model_config = {"arbitrary_types_allowed": True}


class PageIssue(BaseModel):
    """A formatting issue detected on a specific page."""

    page_number: int = Field(ge=1)
    severity: Severity
    category: IssueCategory
    description: str
    bounding_box: Optional[BoundingBox] = None
    confidence: float = Field(default=0.8, ge=0, le=1)


class SourceLocation(BaseModel):
    """A location in a LaTeX source file."""

    file_path: Path
    line_number: int = Field(ge=1)
    column: Optional[int] = None


class MappedIssue(BaseModel):
    """A page issue mapped back to its source location."""

    issue: PageIssue
    source: Optional[SourceLocation] = None


class Fix(BaseModel):
    """A fix applied to a source file."""

    file_path: Path
    line_number: int
    old_text: str
    new_text: str
    issue_category: IssueCategory
    description: str


class ScanReport(BaseModel):
    """Top-level scan report."""

    pdf_path: str
    total_pages: int
    issues: list[MappedIssue] = Field(default_factory=list)
    fixes_applied: list[Fix] = Field(default_factory=list)
    pages_scanned: int = 0
    error_count: int = 0
    warning_count: int = 0
    info_count: int = 0

    def compute_counts(self) -> None:
        """Recompute severity counts from issues list."""
        self.error_count = sum(
            1 for i in self.issues if i.issue.severity == Severity.ERROR
        )
        self.warning_count = sum(
            1 for i in self.issues if i.issue.severity == Severity.WARNING
        )
        self.info_count = sum(
            1 for i in self.issues if i.issue.severity == Severity.INFO
        )

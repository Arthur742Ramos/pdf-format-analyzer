"""SyncTeX mapping: page coordinates → source file + line number."""

from __future__ import annotations

import gzip
import logging
import re
from pathlib import Path

from pdf_format_analyzer.models import MappedIssue, PageIssue, SourceLocation

logger = logging.getLogger(__name__)

# SyncTeX record patterns
_INPUT_RE = re.compile(r"^Input:(\d+):(.+)$")
_VBOX_RE = re.compile(r"^\[(\d+),(\d+):(-?\d+),(-?\d+):(-?\d+),(-?\d+),(-?\d+)$")
_HBOX_RE = re.compile(r"^\((\d+),(\d+):(-?\d+),(-?\d+):(-?\d+),(-?\d+),(-?\d+)$")
_PAGE_RE = re.compile(r"^\{(\d+)$")


class SyncTeXData:
    """Parsed SyncTeX data for mapping page positions to source lines."""

    def __init__(self) -> None:
        self.inputs: dict[int, str] = {}  # input_id -> file_path
        self.records: list[dict] = []     # parsed box records

    @classmethod
    def parse(cls, synctex_path: Path) -> SyncTeXData:
        """Parse a .synctex or .synctex.gz file."""
        data = cls()

        if synctex_path.suffix == ".gz":
            with gzip.open(synctex_path, "rt", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        else:
            with open(synctex_path, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

        current_page = 0

        for line in lines:
            line = line.rstrip("\n")

            # Input file declarations
            m = _INPUT_RE.match(line)
            if m:
                data.inputs[int(m.group(1))] = m.group(2)
                continue

            # Page start
            m = _PAGE_RE.match(line)
            if m:
                current_page = int(m.group(1))
                continue

            # Box records (vertical and horizontal)
            # Format: [page,input:line,column:x,y,w (for vbox)
            #          (page,input:line,column:x,y,w (for hbox)
            for pattern, box_type in [(_VBOX_RE, "vbox"), (_HBOX_RE, "hbox")]:
                m = pattern.match(line)
                if m:
                    data.records.append({
                        "type": box_type,
                        "page": int(m.group(1)),
                        "input_id": int(m.group(2)),
                        "line": int(m.group(3)),
                        "column": int(m.group(4)),
                        "x": int(m.group(5)),
                        "y": int(m.group(6)),
                        "w": int(m.group(7)),
                    })
                    break

            # Simple line records: v/h + page,input:line,column:x,y
            if line.startswith(("v", "h")) and "," in line:
                parts = line[1:].split(",", 1)
                if len(parts) == 2 and ":" in parts[1]:
                    try:
                        page_str = parts[0]
                        rest = parts[1]
                        input_line = rest.split(":", 1)
                        if len(input_line) >= 2:
                            input_id = int(input_line[0])
                            line_num = int(input_line[1].split(",")[0].split(":")[0])
                            data.records.append({
                                "type": "point",
                                "page": int(page_str) if page_str.isdigit() else current_page,
                                "input_id": input_id,
                                "line": line_num,
                                "column": 0,
                                "x": 0,
                                "y": 0,
                                "w": 0,
                            })
                    except (ValueError, IndexError):
                        continue

        logger.info(
            "Parsed SyncTeX: %d inputs, %d records",
            len(data.inputs),
            len(data.records),
        )
        return data


def find_synctex_file(pdf_path: Path) -> Path | None:
    """Find the .synctex.gz or .synctex file for a given PDF."""
    stem = pdf_path.stem
    parent = pdf_path.parent

    for suffix in [".synctex.gz", ".synctex"]:
        candidate = parent / (stem + suffix)
        if candidate.exists():
            return candidate

    return None


def map_issue_to_source(
    issue: PageIssue,
    synctex_data: SyncTeXData,
    source_dir: Path | None = None,
) -> SourceLocation | None:
    """Map a page issue to a source file location using SyncTeX data.

    Args:
        issue: The formatting issue to map.
        synctex_data: Parsed SyncTeX data.
        source_dir: Base directory for resolving relative source paths.

    Returns:
        SourceLocation if mapping found, None otherwise.
    """
    page = issue.page_number

    # Find records on this page
    page_records = [r for r in synctex_data.records if r["page"] == page]
    if not page_records:
        return None

    # If we have bounding box info, try to find the closest record by position
    if issue.bounding_box:
        # Normalize issue position (bounding box is 0-1, synctex uses absolute)
        target_y = issue.bounding_box.y
        best_record = None
        best_dist = float("inf")

        for rec in page_records:
            if rec["y"] == 0 and rec["x"] == 0:
                continue
            # Simple distance metric (rough approximation)
            dist = abs(rec["y"] - target_y * 1e6)
            if dist < best_dist:
                best_dist = dist
                best_record = rec

        if best_record:
            return _record_to_location(best_record, synctex_data, source_dir)

    # Fallback: return the first record on this page with a valid line
    for rec in page_records:
        if rec["line"] > 0:
            return _record_to_location(rec, synctex_data, source_dir)

    return None


def _record_to_location(
    record: dict,
    synctex_data: SyncTeXData,
    source_dir: Path | None,
) -> SourceLocation | None:
    """Convert a SyncTeX record to a SourceLocation."""
    input_id = record.get("input_id", 0)
    file_path_str = synctex_data.inputs.get(input_id)
    if not file_path_str:
        return None

    file_path = Path(file_path_str)
    if source_dir and not file_path.is_absolute():
        file_path = source_dir / file_path

    line_number = record.get("line", 1)
    column = record.get("column", 0)

    return SourceLocation(
        file_path=file_path,
        line_number=max(1, line_number),
        column=column if column > 0 else None,
    )


def map_issues(
    issues: list[PageIssue],
    pdf_path: Path,
    source_dir: Path | None = None,
) -> list[MappedIssue]:
    """Map a list of issues to source locations.

    Args:
        issues: List of detected page issues.
        pdf_path: Path to the PDF file (used to find synctex).
        source_dir: Optional base directory for source files.

    Returns:
        List of MappedIssue objects.
    """
    synctex_file = find_synctex_file(pdf_path)
    synctex_data = None

    if synctex_file:
        try:
            synctex_data = SyncTeXData.parse(synctex_file)
        except Exception as exc:
            logger.warning("Failed to parse SyncTeX file: %s", exc)

    mapped: list[MappedIssue] = []
    for issue in issues:
        source = None
        if synctex_data:
            source = map_issue_to_source(issue, synctex_data, source_dir)
        mapped.append(MappedIssue(issue=issue, source=source))

    return mapped

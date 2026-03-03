"""Parse LaTeX .log files to extract warnings with page number mapping."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from pdf_format_analyzer.models import LogWarning, Severity

logger = logging.getLogger(__name__)

# Patterns for LaTeX log warnings
_OVERFULL_HBOX = re.compile(
    r"Overfull \\hbox \((\d+(?:\.\d+)?)pt too wide\).*?(?:at lines? (\d+)(?:--(\d+))?|in paragraph at lines? (\d+)(?:--(\d+))?)",
    re.IGNORECASE,
)
_UNDERFULL_HBOX = re.compile(
    r"Underfull \\hbox.*?(?:badness \d+).*?(?:at lines? (\d+)(?:--(\d+))?|in paragraph at lines? (\d+)(?:--(\d+))?)",
    re.IGNORECASE,
)
_OVERFULL_VBOX = re.compile(
    r"Overfull \\vbox \((\d+(?:\.\d+)?)pt too high\).*?(?:at lines? (\d+)(?:--(\d+))?|has occurred while \\output is active)?",
    re.IGNORECASE,
)
_UNDERFULL_VBOX = re.compile(
    r"Underfull \\vbox.*?(?:badness \d+).*?(?:at lines? (\d+)(?:--(\d+))?|has occurred while \\output is active)?",
    re.IGNORECASE,
)
_FONT_WARNING = re.compile(
    r"LaTeX Font Warning:\s*(.+?)(?:\s+on input line (\d+))?\.?\s*\n"
    r"(?:\(Font\)\s+.*?(?:\s+on input line (\d+))?\.?\s*\n)*",
    re.IGNORECASE,
)
_MISSING_REF = re.compile(
    r"LaTeX Warning: (?:Reference|Citation)\s+[`'](.+?)'?\s+on page\s+(\d+)\s+undefined",
    re.IGNORECASE,
)
# Page markers: [1], [2], ..., [10], etc.
_PAGE_MARKER = re.compile(r"\[(\d+)(?:\s*\{[^}]*\})*\]")


def _extract_page_numbers(log_text: str) -> list[tuple[int, int]]:
    """Build a list of (char_offset, page_number) from page markers in the log.

    LaTeX writes ``[N]`` when it ships out page N.  We record the character
    offset of each marker so that warnings appearing *after* marker ``[N]``
    but *before* ``[N+1]`` are attributed to page N.
    """
    markers: list[tuple[int, int]] = []
    for m in _PAGE_MARKER.finditer(log_text):
        page_num = int(m.group(1))
        if page_num > 0:
            markers.append((m.start(), page_num))
    return markers


def _page_at_offset(markers: list[tuple[int, int]], offset: int) -> int | None:
    """Return the page number for a given character offset in the log."""
    page: int | None = None
    for marker_offset, marker_page in markers:
        if marker_offset > offset:
            break
        page = marker_page
    return page


def parse_latex_log(log_path: Path) -> list[LogWarning]:
    """Parse a LaTeX ``.log`` file and extract warnings.

    Returns a list of :class:`LogWarning` objects with page numbers derived
    from ``[N]`` page markers in the log.
    """
    log_path = Path(log_path)
    if not log_path.exists():
        raise FileNotFoundError(f"Log file not found: {log_path}")

    log_text = log_path.read_text(encoding="utf-8", errors="replace")
    markers = _extract_page_numbers(log_text)
    warnings: list[LogWarning] = []

    # --- Overfull \hbox ---
    for m in _OVERFULL_HBOX.finditer(log_text):
        amount = float(m.group(1))
        line_num = int(m.group(2) or m.group(4) or 0)
        page = _page_at_offset(markers, m.start())
        severity = Severity.ERROR if amount > 10.0 else Severity.WARNING
        warnings.append(
            LogWarning(
                line_number=line_num,
                page_number=page,
                warning_type="overfull_hbox",
                severity=severity,
                amount=amount,
                message=m.group(0).strip(),
            )
        )

    # --- Underfull \hbox ---
    for m in _UNDERFULL_HBOX.finditer(log_text):
        line_num = int(m.group(1) or m.group(3) or 0)
        page = _page_at_offset(markers, m.start())
        warnings.append(
            LogWarning(
                line_number=line_num,
                page_number=page,
                warning_type="underfull_hbox",
                severity=Severity.WARNING,
                amount=None,
                message=m.group(0).strip(),
            )
        )

    # --- Overfull \vbox ---
    for m in _OVERFULL_VBOX.finditer(log_text):
        amount = float(m.group(1))
        line_num = int(m.group(2) or 0)
        page = _page_at_offset(markers, m.start())
        severity = Severity.WARNING
        warnings.append(
            LogWarning(
                line_number=line_num,
                page_number=page,
                warning_type="overfull_vbox",
                severity=severity,
                amount=amount,
                message=m.group(0).strip(),
            )
        )

    # --- Underfull \vbox ---
    for m in _UNDERFULL_VBOX.finditer(log_text):
        line_num = int(m.group(1) or 0)
        page = _page_at_offset(markers, m.start())
        warnings.append(
            LogWarning(
                line_number=line_num,
                page_number=page,
                warning_type="underfull_vbox",
                severity=Severity.WARNING,
                amount=None,
                message=m.group(0).strip(),
            )
        )

    # --- Font warnings ---
    for m in _FONT_WARNING.finditer(log_text):
        # Line number can be on the first line (group 2) or a continuation line (group 3)
        line_str = m.group(2) or m.group(3)
        line_num = int(line_str) if line_str else 0
        page = _page_at_offset(markers, m.start())
        warnings.append(
            LogWarning(
                line_number=line_num,
                page_number=page,
                warning_type="font",
                severity=Severity.INFO,
                amount=None,
                message=m.group(0).strip(),
            )
        )

    # --- Missing references / citations ---
    for m in _MISSING_REF.finditer(log_text):
        page = int(m.group(2))
        warnings.append(
            LogWarning(
                line_number=0,
                page_number=page,
                warning_type="missing_ref",
                severity=Severity.WARNING,
                amount=None,
                message=m.group(0).strip(),
            )
        )

    logger.info("Parsed %d warnings from %s", len(warnings), log_path.name)
    return warnings

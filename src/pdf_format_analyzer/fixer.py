"""Auto-fix engine for common LaTeX formatting issues."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from pdf_format_analyzer.models import Fix, IssueCategory, MappedIssue

logger = logging.getLogger(__name__)

# Patterns for detecting fixable constructs
_TIKZCD_RE = re.compile(
    r"(\\begin\{tikzcd\}.*?\\end\{tikzcd\})",
    re.DOTALL,
)
_WIDE_EQUATION_RE = re.compile(
    r"(\\begin\{(equation|align|gather|multline)\*?\}.*?"
    r"\\end\{\2\*?\})",
    re.DOTALL,
)
_TEXTTT_PATH_RE = re.compile(
    r"\\texttt\{([^}]*[/\\][^}]*)\}",
)
_INCLUDEGRAPHICS_RE = re.compile(
    r"(\\includegraphics(?:\[[^\]]*\])?\{[^}]+\})",
)


def _wrap_adjustbox(content: str, max_width: str = r"\textwidth") -> str:
    """Wrap content in an adjustbox environment."""
    return (
        f"\\adjustbox{{max width={max_width}}}{{\n"
        f"{content}\n"
        f"}}"
    )


def _add_texttt_breaks(match: re.Match) -> str:
    """Add \\allowbreak at path separators in \\texttt."""
    path = match.group(1)
    # Add \allowbreak after each path separator
    broken = re.sub(r"([/\\])", r"\1\\allowbreak ", path)
    return f"\\texttt{{{broken}}}"


def fix_overfull_tikzcd(line: str, lines: list[str], line_idx: int) -> Fix | None:
    """Fix overfull tikzcd diagrams by wrapping in adjustbox."""
    # Look for tikzcd environment starting at or near this line
    # Join surrounding lines to capture the full environment
    context_start = max(0, line_idx - 2)
    context_end = min(len(lines), line_idx + 30)
    context = "\n".join(lines[context_start:context_end])

    m = _TIKZCD_RE.search(context)
    if not m:
        return None

    tikzcd = m.group(1)
    # Check if already wrapped
    prefix_start = max(0, context.find(tikzcd) - 40)
    prefix = context[prefix_start : context.find(tikzcd)]
    if "adjustbox" in prefix:
        return None

    new_tikzcd = _wrap_adjustbox(tikzcd)
    return Fix(
        file_path=Path(""),  # filled by caller
        line_number=line_idx + 1,
        old_text=tikzcd,
        new_text=new_tikzcd,
        issue_category=IssueCategory.OVERFULL_BOX,
        description="Wrapped overfull tikzcd diagram in adjustbox",
    )


def fix_overfull_equation(line: str, lines: list[str], line_idx: int) -> Fix | None:
    """Fix overfull equations by wrapping in adjustbox."""
    context_start = max(0, line_idx - 2)
    context_end = min(len(lines), line_idx + 20)
    context = "\n".join(lines[context_start:context_end])

    m = _WIDE_EQUATION_RE.search(context)
    if not m:
        return None

    equation = m.group(1)
    prefix_start = max(0, context.find(equation) - 40)
    prefix = context[prefix_start : context.find(equation)]
    if "adjustbox" in prefix or "resizebox" in prefix:
        return None

    new_equation = _wrap_adjustbox(equation)
    return Fix(
        file_path=Path(""),
        line_number=line_idx + 1,
        old_text=equation,
        new_text=new_equation,
        issue_category=IssueCategory.OVERFULL_BOX,
        description="Wrapped overfull equation in adjustbox",
    )


def fix_texttt_paths(line: str) -> Fix | None:
    """Fix overfull \\texttt with file paths by adding \\allowbreak."""
    m = _TEXTTT_PATH_RE.search(line)
    if not m:
        return None

    # Check if already has \allowbreak
    if r"\allowbreak" in m.group(0):
        return None

    old = m.group(0)
    new = _add_texttt_breaks(m)

    if old == new:
        return None

    return Fix(
        file_path=Path(""),
        line_number=0,
        old_text=old,
        new_text=new,
        issue_category=IssueCategory.OVERFULL_BOX,
        description="Added \\allowbreak to long file path in \\texttt",
    )


def fix_overfull_includegraphics(line: str) -> Fix | None:
    """Fix overfull images by adding max width option."""
    m = _INCLUDEGRAPHICS_RE.search(line)
    if not m:
        return None

    cmd = m.group(1)
    # Check if already has width constraint
    if "width=" in cmd or "max width" in cmd or "scale=" in cmd:
        return None

    # Add width=\textwidth option
    if r"\includegraphics[" in cmd:
        new_cmd = cmd.replace(r"\includegraphics[", r"\includegraphics[width=\textwidth,")
    else:
        new_cmd = cmd.replace(r"\includegraphics{", r"\includegraphics[width=\textwidth]{")

    return Fix(
        file_path=Path(""),
        line_number=0,
        old_text=cmd,
        new_text=new_cmd,
        issue_category=IssueCategory.CUTOFF,
        description="Added width=\\textwidth to unconstrained \\includegraphics",
    )


def suggest_fixes_for_line(
    line: str,
    lines: list[str],
    line_idx: int,
    category: IssueCategory,
) -> list[Fix]:
    """Suggest fixes for a specific line based on issue category."""
    fixes: list[Fix] = []

    if category in (IssueCategory.OVERFULL_BOX, IssueCategory.MARGIN_VIOLATION):
        fix = fix_overfull_tikzcd(line, lines, line_idx)
        if fix:
            fixes.append(fix)

        fix = fix_overfull_equation(line, lines, line_idx)
        if fix:
            fixes.append(fix)

        fix = fix_texttt_paths(line)
        if fix:
            fixes.append(fix)

    if category in (IssueCategory.CUTOFF, IssueCategory.OVERFULL_BOX):
        fix = fix_overfull_includegraphics(line)
        if fix:
            fixes.append(fix)

    return fixes


def apply_fixes(
    issues: list[MappedIssue],
    source_dir: Path,
) -> list[Fix]:
    """Analyze mapped issues and apply auto-fixes where possible.

    Args:
        issues: List of issues mapped to source locations.
        source_dir: Root directory containing LaTeX source files.

    Returns:
        List of Fix objects describing changes made.
    """
    applied: list[Fix] = []

    # Group issues by file
    by_file: dict[Path, list[MappedIssue]] = {}
    for mi in issues:
        if mi.source and mi.source.file_path:
            fp = mi.source.file_path
            if not fp.is_absolute():
                fp = source_dir / fp
            by_file.setdefault(fp, []).append(mi)

    for file_path, file_issues in by_file.items():
        if not file_path.exists():
            logger.warning("Source file not found: %s", file_path)
            continue

        try:
            content = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("Cannot read %s: %s", file_path, exc)
            continue

        lines = content.split("\n")
        modified = False

        for mi in file_issues:
            line_num = mi.source.line_number if mi.source else 0
            if line_num < 1 or line_num > len(lines):
                continue

            line_idx = line_num - 1
            fixes = suggest_fixes_for_line(
                lines[line_idx], lines, line_idx, mi.issue.category
            )

            for fix in fixes:
                fix.file_path = file_path
                fix.line_number = line_num
                # Apply the fix to content
                if fix.old_text in content:
                    content = content.replace(fix.old_text, fix.new_text, 1)
                    lines = content.split("\n")
                    modified = True
                    applied.append(fix)
                    logger.info("Applied fix at %s:%d — %s", file_path.name, line_num, fix.description)

        if modified:
            file_path.write_text(content, encoding="utf-8")

    logger.info("Applied %d fixes across %d files", len(applied), len(by_file))
    return applied

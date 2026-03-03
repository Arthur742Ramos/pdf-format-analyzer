"""Smart page selection strategies to minimize scanning cost."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from pdf_format_analyzer.log_parser import parse_latex_log
from pdf_format_analyzer.renderer import get_page_count

logger = logging.getLogger(__name__)


def log_guided_pages(log_path: Path) -> list[int]:
    """Parse a LaTeX log and return sorted, unique page numbers with warnings."""
    warnings = parse_latex_log(log_path)
    pages: set[int] = set()
    for w in warnings:
        if w.page_number is not None:
            pages.add(w.page_number)
    result = sorted(pages)
    logger.info("Log-guided: %d pages with warnings", len(result))
    return result


def diff_guided_pages(source_dir: Path, since: str = "HEAD~1") -> list[int]:
    """Use ``git diff`` to find changed ``.tex`` files since *since*.

    This is a best-effort heuristic: it returns an empty list if git is
    unavailable or synctex mapping is not set up.  The caller should fall
    back to a full scan in that case.
    """
    source_dir = Path(source_dir)
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", since, "--", "*.tex"],
            capture_output=True,
            text=True,
            cwd=str(source_dir),
            timeout=10,
        )
        if result.returncode != 0:
            logger.debug("git diff failed: %s", result.stderr.strip())
            return []
        changed_files = [f.strip() for f in result.stdout.splitlines() if f.strip()]
        if changed_files:
            logger.info("Diff-guided: %d .tex files changed since %s", len(changed_files), since)
        # Without synctex, we can't map files→pages, so return empty
        # to signal the caller should use another strategy.
        return []
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        logger.debug("diff_guided_pages unavailable: %s", exc)
        return []


def sample_pages(total_pages: int, sample_rate: int = 10) -> list[int]:
    """Return every Nth page (1-based), always including first and last."""
    if total_pages <= 0:
        return []
    pages: set[int] = {1, total_pages}
    for p in range(1, total_pages + 1, sample_rate):
        pages.add(p)
    return sorted(pages)


def smart_page_selection(
    pdf_path: Path,
    log_path: Path | None = None,
    source_dir: Path | None = None,
    strategy: str = "auto",
    sample_rate: int = 10,
) -> list[int]:
    """Select which pages to scan based on *strategy*.

    Strategies
    ----------
    auto
        1. If *log_path* has warnings with page numbers → log-guided.
        2. If *source_dir* is a git repo → diff-guided.
        3. Fallback → full scan.
    log
        Parse *log_path* and scan only warning pages.
    diff
        Use git diff + synctex (best-effort).
    sample
        Every *sample_rate*-th page.
    full
        All pages (current default behaviour).
    """
    total = get_page_count(pdf_path)

    if strategy == "full":
        return list(range(1, total + 1))

    if strategy == "sample":
        return sample_pages(total, sample_rate)

    if strategy == "log":
        if log_path is None:
            raise ValueError("--log is required when using strategy='log'")
        pages = log_guided_pages(log_path)
        if not pages:
            logger.warning("No page-level warnings found in log; falling back to full scan")
            return list(range(1, total + 1))
        return pages

    if strategy == "diff":
        if source_dir is None:
            raise ValueError("--source is required when using strategy='diff'")
        pages = diff_guided_pages(source_dir)
        if not pages:
            logger.warning("Diff-guided returned no pages; falling back to full scan")
            return list(range(1, total + 1))
        return pages

    # strategy == "auto"
    if log_path is not None:
        pages = log_guided_pages(log_path)
        if pages:
            logger.info("Auto strategy: using log-guided (%d pages)", len(pages))
            return pages

    if source_dir is not None:
        pages = diff_guided_pages(source_dir)
        if pages:
            logger.info("Auto strategy: using diff-guided (%d pages)", len(pages))
            return pages

    logger.info("Auto strategy: falling back to full scan (%d pages)", total)
    return list(range(1, total + 1))

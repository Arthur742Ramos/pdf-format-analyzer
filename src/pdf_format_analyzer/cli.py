"""CLI interface for PDF Format Analyzer."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from pdf_format_analyzer import __version__
from pdf_format_analyzer.config import PFAConfig
from pdf_format_analyzer.models import ScanReport, Severity

app = typer.Typer(
    name="pfa",
    help="PDF Format Analyzer — detect and fix LaTeX formatting issues using vision LLM.",
    no_args_is_help=True,
)
console = Console()


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
        force=True,
    )


def _run_scan(
    pdf_path: Path,
    source_dir: Path | None,
    apply_fix: bool,
    config: PFAConfig,
    *,
    strategy: str = "full",
    log_path: Path | None = None,
    sample_rate: int = 10,
) -> ScanReport:
    """Core scan logic shared by scan and report commands."""
    from pdf_format_analyzer.analyzer import analyze_pages_sync
    from pdf_format_analyzer.fixer import apply_fixes
    from pdf_format_analyzer.mapper import map_issues
    from pdf_format_analyzer.renderer import get_page_count, render_pages, render_specific_pages
    from pdf_format_analyzer.smart_scan import smart_page_selection

    total_pages = get_page_count(pdf_path)

    # Determine pages to scan
    if strategy != "full":
        with console.status("[bold cyan]Selecting pages to scan..."):
            selected_pages = smart_page_selection(
                pdf_path,
                log_path=log_path,
                source_dir=source_dir,
                strategy=strategy,
                sample_rate=sample_rate,
            )
        console.print(
            f"[cyan]Strategy '{strategy}':[/cyan] scanning {len(selected_pages)}"
            f" / {total_pages} pages"
        )
        with console.status("[bold green]Rendering selected pages..."):
            pages = render_specific_pages(pdf_path, selected_pages, dpi=config.dpi)
            if config.max_pages and len(pages) > config.max_pages:
                pages = pages[: config.max_pages]
    else:
        with console.status("[bold green]Rendering PDF pages..."):
            pages = render_pages(pdf_path, dpi=config.dpi, max_pages=config.max_pages)

    with console.status("[bold blue]Analyzing pages with vision LLM..."):
        issues = analyze_pages_sync(pages, config)

    mapped = map_issues(issues, pdf_path, source_dir)

    fixes = []
    if apply_fix and source_dir:
        with console.status("[bold yellow]Applying auto-fixes..."):
            fixes = apply_fixes(mapped, source_dir)

    # Collect log warnings if a log file was provided
    log_warnings_list = []
    if log_path is not None:
        from pdf_format_analyzer.log_parser import parse_latex_log

        try:
            log_warnings_list = parse_latex_log(log_path)
        except FileNotFoundError:
            pass

    report = ScanReport(
        pdf_path=str(pdf_path),
        total_pages=total_pages,
        issues=mapped,
        fixes_applied=fixes,
        pages_scanned=len(pages),
        scan_strategy=strategy,
        log_warnings=log_warnings_list,
    )
    report.compute_counts()
    return report


@app.command()
def scan(
    pdf_path: Annotated[Path, typer.Argument(help="Path to the PDF file to analyze")],
    source: Annotated[
        Path | None,
        typer.Option("--source", "-s", help="LaTeX source directory for synctex mapping"),
    ] = None,
    fix: Annotated[
        bool,
        typer.Option("--fix", "-f", help="Auto-fix detected issues in source files"),
    ] = False,
    dpi: Annotated[
        int,
        typer.Option("--dpi", help="Rendering DPI (default: 150)"),
    ] = 150,
    batch_size: Annotated[
        int,
        typer.Option("--batch-size", "-b", help="Pages per LLM batch"),
    ] = 5,
    model: Annotated[
        str | None,
        typer.Option("--model", "-m", help="Vision model to use"),
    ] = None,
    max_pages: Annotated[
        int | None,
        typer.Option("--max-pages", help="Maximum pages to scan"),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output file path (default: stdout)"),
    ] = None,
    strategy: Annotated[
        str,
        typer.Option("--strategy", help="Scan strategy: auto, log, diff, sample, full"),
    ] = "full",
    log: Annotated[
        Path | None,
        typer.Option("--log", help="LaTeX .log file for log-guided scanning"),
    ] = None,
    sample_rate: Annotated[
        int,
        typer.Option("--sample-rate", help="Every Nth page for sample strategy"),
    ] = 10,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Enable verbose logging"),
    ] = False,
) -> None:
    """Scan a PDF for formatting issues and output a JSON report."""
    _setup_logging(verbose)

    if not pdf_path.exists():
        console.print(f"[red]Error:[/red] PDF not found: {pdf_path}")
        raise typer.Exit(1)

    if fix and not source:
        console.print("[red]Error:[/red] --fix requires --source directory")
        raise typer.Exit(1)

    if strategy not in ("auto", "log", "diff", "sample", "full"):
        console.print(f"[red]Error:[/red] Unknown strategy: {strategy}")
        raise typer.Exit(1)

    # Default to auto when --log is provided but no explicit strategy
    effective_strategy = strategy
    if log is not None and strategy == "full":
        effective_strategy = "auto"

    config = PFAConfig(
        dpi=dpi,
        batch_size=batch_size,
        model=model or PFAConfig.load().model,
        max_pages=max_pages,
        verbose=verbose,
    )

    report = _run_scan(
        pdf_path,
        source,
        fix,
        config,
        strategy=effective_strategy,
        log_path=log,
        sample_rate=sample_rate,
    )

    # Output JSON report
    report_json = report.model_dump_json(indent=2)
    if output:
        output.write_text(report_json, encoding="utf-8")
        console.print(f"[green]Report written to {output}")
    else:
        typer.echo(report_json)

    # Exit with error code if issues found
    if report.error_count > 0:
        raise typer.Exit(1)


@app.command()
def report(
    pdf_path: Annotated[Path, typer.Argument(help="Path to the PDF file to analyze")],
    source: Annotated[
        Path | None,
        typer.Option("--source", "-s", help="LaTeX source directory"),
    ] = None,
    dpi: Annotated[int, typer.Option("--dpi")] = 150,
    batch_size: Annotated[int, typer.Option("--batch-size", "-b")] = 5,
    model: Annotated[str | None, typer.Option("--model", "-m")] = None,
    max_pages: Annotated[int | None, typer.Option("--max-pages")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Scan a PDF and display a rich terminal report."""
    _setup_logging(verbose)

    if not pdf_path.exists():
        console.print(f"[red]Error:[/red] PDF not found: {pdf_path}")
        raise typer.Exit(1)

    config = PFAConfig(
        dpi=dpi,
        batch_size=batch_size,
        model=model or PFAConfig.load().model,
        max_pages=max_pages,
        verbose=verbose,
    )

    report_data = _run_scan(pdf_path, source, False, config)
    _display_report(report_data)


def _display_report(report: ScanReport) -> None:
    """Display a rich formatted report in the terminal."""
    # Summary panel
    summary = (
        f"PDF: [bold]{report.pdf_path}[/bold]\n"
        f"Pages scanned: {report.pages_scanned} / {report.total_pages}\n"
        f"Issues found: "
        f"[red]{report.error_count} errors[/red], "
        f"[yellow]{report.warning_count} warnings[/yellow], "
        f"[blue]{report.info_count} info[/blue]"
    )
    if report.fixes_applied:
        summary += f"\nFixes applied: [green]{len(report.fixes_applied)}[/green]"

    console.print(Panel(summary, title="PDF Format Analysis", border_style="blue"))

    if not report.issues:
        console.print("\n[green]✓ No formatting issues detected![/green]")
        return

    # Issues table
    table = Table(title="Detected Issues", show_lines=True)
    table.add_column("Page", style="cyan", width=6, justify="right")
    table.add_column("Severity", width=10)
    table.add_column("Category", style="magenta", width=18)
    table.add_column("Description", style="white")
    table.add_column("Source", style="dim", width=30)

    severity_styles = {
        Severity.ERROR: "[bold red]ERROR[/bold red]",
        Severity.WARNING: "[yellow]WARNING[/yellow]",
        Severity.INFO: "[blue]INFO[/blue]",
    }

    for mi in report.issues:
        issue = mi.issue
        source_str = ""
        if mi.source:
            source_str = f"{mi.source.file_path.name}:{mi.source.line_number}"

        table.add_row(
            str(issue.page_number),
            severity_styles.get(issue.severity, str(issue.severity)),
            issue.category.value.replace("_", " "),
            issue.description,
            source_str,
        )

    console.print(table)

    # Fixes table
    if report.fixes_applied:
        fixes_table = Table(title="Applied Fixes", show_lines=True)
        fixes_table.add_column("File", style="cyan")
        fixes_table.add_column("Line", width=6, justify="right")
        fixes_table.add_column("Description", style="green")

        for fix in report.fixes_applied:
            fixes_table.add_row(
                fix.file_path.name,
                str(fix.line_number),
                fix.description,
            )

        console.print(fixes_table)


@app.command()
def version() -> None:
    """Show the version."""
    console.print(f"pdf-format-analyzer v{__version__}")


def main() -> None:
    """Entry point."""
    app()


if __name__ == "__main__":
    main()

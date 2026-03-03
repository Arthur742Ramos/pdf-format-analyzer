# PDF Format Analyzer

> Detect and fix LaTeX formatting issues in compiled PDFs using vision LLM analysis via GitHub Copilot SDK.

**pdf-format-analyzer** (`pfa`) renders your PDF pages to images, sends them to a vision-capable LLM through the GitHub Copilot SDK, and identifies formatting problems that are hard to catch by reading `.log` files alone — overfull boxes bleeding into margins, orphaned lines, cut-off diagrams, overlapping elements, and more. It can then map those findings back to your `.tex` source files (via SyncTeX) and even auto-fix common issues.

## Features

- 🔍 **Vision-based analysis** — catches issues that log-file grep misses
- 📄 **Full PDF scanning** — renders every page at configurable DPI
- 🗺️ **SyncTeX mapping** — traces issues back to exact source lines
- 🔧 **Auto-fix engine** — wraps wide tikzcd/equations in `\adjustbox`, adds `\allowbreak` to long paths
- 📊 **Rich terminal reports** — color-coded severity, page numbers, source locations
- 📦 **JSON output** — machine-readable reports for CI pipelines

## Installation

```bash
pip install pdf-format-analyzer
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv pip install pdf-format-analyzer
```

### Requirements

- Python ≥ 3.10
- GitHub Copilot SDK (`github-copilot-sdk`) — requires an active Copilot subscription
- No system dependencies needed (uses PyMuPDF for rendering, which is pure Python)

## Quick Start

### Scan a PDF and get a JSON report

```bash
pfa scan thesis.pdf
```

### Scan with source mapping

```bash
pfa scan thesis.pdf --source ./src/
```

### Scan and auto-fix issues

```bash
pfa scan thesis.pdf --source ./src/ --fix
```

### Rich terminal report

```bash
pfa report thesis.pdf --source ./src/
```

### Limit to specific pages

```bash
pfa scan thesis.pdf --max-pages 10
```

## CLI Reference

### `pfa scan`

Scan a PDF for formatting issues and output a JSON report.

```
pfa scan <pdf-path> [OPTIONS]

Options:
  --source, -s PATH       LaTeX source directory (enables SyncTeX mapping)
  --fix, -f               Auto-fix detected issues (requires --source)
  --dpi INT               Rendering DPI [default: 150]
  --batch-size, -b INT    Pages per LLM batch [default: 5]
  --model, -m TEXT        Vision model to use [default: gpt-4.1]
  --max-pages INT         Maximum pages to scan
  --output, -o PATH       Output file (default: stdout)
  --verbose, -v           Enable verbose logging
```

### `pfa report`

Scan a PDF and display a rich terminal report with colored severity indicators.

```
pfa report <pdf-path> [OPTIONS]

Options:
  --source, -s PATH       LaTeX source directory
  --dpi INT               Rendering DPI [default: 150]
  --batch-size, -b INT    Pages per LLM batch [default: 5]
  --model, -m TEXT        Vision model to use
  --max-pages INT         Maximum pages to scan
  --verbose, -v           Enable verbose logging
```

### `pfa version`

Show the installed version.

## How It Works

```
┌─────────────┐     ┌──────────────┐     ┌───────────────┐
│  PDF File   │────▶│   Renderer   │────▶│   Analyzer    │
│             │     │  (PyMuPDF)   │     │ (Copilot SDK) │
└─────────────┘     └──────────────┘     └───────┬───────┘
                                                 │
                    ┌──────────────┐              │
                    │   SyncTeX    │◀─────────────┘
                    │   Mapper     │     ┌───────────────┐
                    └──────┬───────┘────▶│    Report     │
                           │             │  (JSON/Rich)  │
                    ┌──────▼───────┐     └───────────────┘
                    │  Auto-Fixer  │
                    │  (optional)  │
                    └──────────────┘
```

1. **Renderer** — Uses PyMuPDF to render each PDF page to a PNG image at the configured DPI.
2. **Analyzer** — Sends page images to a vision LLM (via `github-copilot-sdk`) in batches. The LLM identifies formatting issues and returns structured JSON.
3. **Mapper** — Parses `.synctex.gz` files to map page-level findings back to source `.tex` file and line number.
4. **Fixer** — Applies automatic fixes for common patterns (wide diagrams → `\adjustbox`, long paths → `\allowbreak`).
5. **Reporter** — Outputs results as JSON (for CI) or a rich terminal table.

## Issue Categories

| Category | Severity | Description |
|----------|----------|-------------|
| `overfull_box` | error/warning | Text extending beyond margins |
| `underfull_box` | warning | Excessive word spacing |
| `orphan` | warning | Single paragraph line at page bottom |
| `widow` | warning | Single paragraph line at page top |
| `misaligned` | warning | Improperly centered/aligned elements |
| `overlap` | error | Elements overlapping each other |
| `cutoff` | error | Figures/tables cut off at page boundary |
| `bad_spacing` | info/warning | Inconsistent spacing |
| `table_break` | warning | Awkward table page break |
| `equation_break` | warning | Equation split across pages |
| `margin_violation` | error | Content in margin area |

## Configuration

Create `~/.config/pfa/config.toml`:

```toml
[scan]
dpi = 150
batch_size = 5
model = "gpt-4.1"
output_format = "json"

[fix]
overfull = true
tikzcd = true
equations = true
texttt = true
```

## GitHub Actions Usage

```yaml
- name: Check PDF formatting
  run: |
    pip install pdf-format-analyzer
    pfa scan output/thesis.pdf --source src/ -o report.json

- name: Upload report
  if: always()
  uses: actions/upload-artifact@v4
  with:
    name: format-report
    path: report.json
```

## Auto-Fix Patterns

The fixer handles these common issues:

| Pattern | Fix Applied |
|---------|------------|
| Wide `tikzcd` diagrams | Wrap in `\adjustbox{max width=\textwidth}` |
| Wide equations/align | Wrap in `\adjustbox{max width=\textwidth}` |
| Long `\texttt` file paths | Add `\allowbreak` at path separators |
| Unconstrained `\includegraphics` | Add `width=\textwidth` option |

## Contributing

1. Clone the repository
2. Install in development mode: `pip install -e ".[dev]"`
3. Run tests: `pytest tests/ -v`
4. Lint: `ruff check src/ tests/`

## License

MIT — see [LICENSE](LICENSE).

"""Configuration management for PDF Format Analyzer."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[no-redefine]


DEFAULT_CONFIG_DIR = Path.home() / ".config" / "pfa"
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.toml"

DEFAULT_DPI = 150
DEFAULT_BATCH_SIZE = 5
DEFAULT_MODEL = "gpt-4.1"


@dataclass
class PFAConfig:
    """Runtime configuration for the analyzer."""

    dpi: int = DEFAULT_DPI
    batch_size: int = DEFAULT_BATCH_SIZE
    model: str = DEFAULT_MODEL
    max_pages: int | None = None
    output_format: str = "json"
    verbose: bool = False

    # Auto-fix settings
    fix_overfull: bool = True
    fix_tikzcd: bool = True
    fix_equations: bool = True
    fix_texttt: bool = True

    # Paths
    synctex_path: Path | None = None

    @classmethod
    def load(cls, path: Path | None = None) -> PFAConfig:
        """Load configuration from TOML file, falling back to defaults."""
        config_path = path or DEFAULT_CONFIG_PATH
        if not config_path.exists():
            return cls()

        with open(config_path, "rb") as f:
            data = tomllib.load(f)

        scan = data.get("scan", {})
        fix = data.get("fix", {})
        return cls(
            dpi=scan.get("dpi", DEFAULT_DPI),
            batch_size=scan.get("batch_size", DEFAULT_BATCH_SIZE),
            model=scan.get("model", DEFAULT_MODEL),
            max_pages=scan.get("max_pages"),
            output_format=scan.get("output_format", "json"),
            verbose=scan.get("verbose", False),
            fix_overfull=fix.get("overfull", True),
            fix_tikzcd=fix.get("tikzcd", True),
            fix_equations=fix.get("equations", True),
            fix_texttt=fix.get("texttt", True),
        )

from __future__ import annotations

import sys
from pathlib import Path

# Ensure 'src' is importable when running as a script
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from cv_search.cli import main as cli_main  # noqa: E402


if __name__ == "__main__":
    cli_main()

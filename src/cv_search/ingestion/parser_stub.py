from __future__ import annotations

from pathlib import Path


class StubCVParser:
    """
    Minimal parser for agentic/offline runs.
    Reads plain text files and returns their content.
    """

    def extract_text(self, file_path: Path) -> str:
        if not file_path.exists():
            raise FileNotFoundError(f"File not found at: {file_path}")
        return file_path.read_text(encoding="utf-8")

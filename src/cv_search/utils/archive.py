from __future__ import annotations

import io
import zipfile
from pathlib import Path


def zip_directory(path: str | Path) -> bytes:
    """Create a zip archive (bytes) from a directory, preserving relative paths."""

    root = Path(path)
    if not root.exists():
        raise FileNotFoundError(str(root))
    if not root.is_dir():
        raise NotADirectoryError(str(root))

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for item in sorted(root.rglob("*")):
            if item.is_file():
                zf.write(item, arcname=str(item.relative_to(root)))

    return buffer.getvalue()

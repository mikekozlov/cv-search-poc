from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def mask_secret(value: str | None) -> str:
    if not value:
        return "(unset)"
    return (value[:4] + "..." + value[-4:]) if len(value) > 8 else "***"


def load_json_file(path: str | Path) -> Any:
    with open(Path(path), "r", encoding="utf-8") as handle:
        return json.load(handle)

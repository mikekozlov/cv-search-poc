from __future__ import annotations
import json
import uuid
import threading
import contextvars
from datetime import datetime, timezone
from pathlib import Path
from cv_search.config.settings import REPO_ROOT

_RUN_DIR = contextvars.ContextVar("cv_search_llm_run_dir", default=None)
_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()

def set_run_dir(run_dir: str | Path):
    p = Path(run_dir)
    p.mkdir(parents=True, exist_ok=True)
    return _RUN_DIR.set(str(p))

def reset_run_dir(token):
    _RUN_DIR.reset(token)

def _resolve_log_path() -> Path:
    run_dir = _RUN_DIR.get()
    if run_dir:
        p = Path(run_dir) / "llm.prompts.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    base = REPO_ROOT / "runs" / "llm" / day
    base.mkdir(parents=True, exist_ok=True)
    return base / "llm.jsonl"

def _lock_for(path: Path) -> threading.Lock:
    key = str(path)
    with _LOCKS_GUARD:
        if key not in _LOCKS:
            _LOCKS[key] = threading.Lock()
        return _LOCKS[key]

def log_chat(*, messages: list[dict], model: str, response_content: str, provider: str, usage: dict | None = None, meta: dict | None = None) -> None:
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "provider": provider,
        "model": model,
        "meta": meta or {},
        "request": {"messages": messages},
        "response": {"content": response_content},
        "usage": usage,
        "run_dir": _RUN_DIR.get(),
        "id": str(uuid.uuid4()),
    }
    path = _resolve_log_path()
    line = json.dumps(entry, ensure_ascii=False)
    lock = _lock_for(path)
    with lock:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

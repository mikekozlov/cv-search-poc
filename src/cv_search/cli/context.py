from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from cv_search.clients.openai_client import OpenAIClient
from cv_search.config.settings import Settings
from cv_search.db.database import CVDatabase


def load_default_env() -> None:
    """
    Load a project-level .env if present.
    Resolves to the repository root (two levels up from this file).
    """
    project_root = Path(__file__).resolve().parents[3]
    env_path = project_root / ".env"
    load_dotenv(dotenv_path=env_path, override=False)


@dataclass
class CLIContext:
    settings: Settings
    client: OpenAIClient
    db: CVDatabase


def build_context(db_url: Optional[str] = None) -> CLIContext:
    load_default_env()

    settings = Settings()
    if db_url:
        settings.db_url = db_url

    client = OpenAIClient(settings)
    db = CVDatabase(settings)

    return CLIContext(settings=settings, client=client, db=db)

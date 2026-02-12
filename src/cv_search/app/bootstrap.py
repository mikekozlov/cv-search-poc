from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List

from dotenv import load_dotenv

from cv_search.clients.openai_client import LiveOpenAIBackend, OpenAIClient, StubOpenAIBackend
from cv_search.config.settings import Settings
from cv_search.lexicon.loader import (
    load_domain_lexicon,
    load_expertise_lexicon,
    load_role_lexicon,
    load_tech_lexicon,
)
from cv_search.planner.service import Planner


def _load_default_env() -> None:
    project_root = Path(__file__).resolve().parents[3]
    load_dotenv(dotenv_path=project_root / ".env", override=False)


def load_stateless_services() -> Dict[str, object]:
    _load_default_env()

    settings = Settings()
    use_stub_flag = os.environ.get("USE_OPENAI_STUB") or os.environ.get("HF_HUB_OFFLINE")
    force_stub = use_stub_flag and str(use_stub_flag).lower() in {"1", "true", "yes", "on"}
    backend = (
        StubOpenAIBackend(settings)
        if force_stub or not settings.openai_api_key_str
        else LiveOpenAIBackend(settings)
    )
    client = OpenAIClient(settings, backend=backend)
    planner = Planner()

    lexicon_dir = settings.lexicon_dir
    role_lex: List[str] = load_role_lexicon(lexicon_dir)
    tech_lex: List[str] = load_tech_lexicon(lexicon_dir)
    domain_lex: List[str] = load_domain_lexicon(lexicon_dir)
    expertise_lex: List[str] = load_expertise_lexicon(lexicon_dir)

    return {
        "settings": settings,
        "client": client,
        "planner": planner,
        "role_lex": role_lex,
        "tech_lex": tech_lex,
        "domain_lex": domain_lex,
        "expertise_lex": expertise_lex,
    }

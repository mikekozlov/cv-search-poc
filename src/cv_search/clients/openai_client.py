from __future__ import annotations

import json
import os
import re
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Protocol, Type

from openai import AzureOpenAI, OpenAI

from cv_search.config.settings import Settings
from cv_search.lexicon.loader import (
    load_domain_lexicon,
    load_expertise_lexicon,
    load_role_lexicon,
    load_tech_synonyms,
)
from cv_search.llm.schemas import CandidateJustification
from cv_search.llm.logger import log_chat

try:
    from pydantic.v1 import BaseModel, Field
except ImportError:  # pragma: no cover
    from pydantic import BaseModel, Field


_TRUTHY = {"1", "true", "yes", "on"}


def _env_flag(name: str) -> bool:
    value = os.environ.get(name)
    return value is not None and str(value).lower() in _TRUTHY


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower()).strip()


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_+#\.]+", text.lower()))


def _candidate_score(canonical: str, text_lower: str, tokens: set[str]) -> int:
    """Score how well a canonical lexicon entry matches the text/hint."""
    c_lower = canonical.lower()
    score = 0
    alt = c_lower.replace("_", " ")
    if c_lower in text_lower:
        score += 3
    if alt in text_lower and alt != c_lower:
        score += 2
    parts = re.split(r"[_\s/\-\.]+", c_lower)
    for part in parts:
        if len(part) < 3:
            continue
        if part in tokens:
            score += 1
    return score


def _select_candidates(
        lexicon: List[str],
        text: str,
        role_hint: str,
        *,
        max_candidates: int,
        fallback: int | None = None,
) -> List[str]:
    combined = _normalize_text(f"{text} {role_hint}")
    tokens = _tokenize(combined)
    scored: List[tuple[int, str]] = []
    for item in lexicon:
        score = _candidate_score(item, combined, tokens)
        if score > 0:
            scored.append((score, item))
    if scored:
        scored.sort(key=lambda pair: (-pair[0], pair[1]))
        return [item for _, item in scored[:max_candidates]]
    limit = fallback or max_candidates
    return list(lexicon[:limit])


def _lexicon_fingerprint(*lexicons: List[str]) -> str:
    payload = json.dumps([sorted(lex) for lex in lexicons], separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


class LLMCriteria(BaseModel):
    domain: List[str]
    tech_stack: List[str]
    expert_roles: List[str]
    project_type: str | None = None
    team_size: Dict[str, Any] | None = None


class LLMCV(BaseModel):
    name: str | None = None
    location: str | None = None
    seniority: str
    role_tags: List[str]
    expertise_tags: List[str] = Field(default_factory=list)
    summary: str | None = None
    experience: List[Dict[str, Any]]
    tech_tags: List[str]
    qualifications: Dict[str, List[str]] = Field(default_factory=dict)
    unmapped_tags: str | None = None
    source_folder_role_hint: str | None = None


class OpenAIBackendProtocol(Protocol):
    def get_structured_criteria(self, text: str, model: str, settings: Settings) -> Dict[str, Any]:
        ...

    def get_structured_cv(self, raw_text: str, role_folder_hint: str, model: str, settings: Settings) -> Dict[str, Any]:
        ...

    def get_candidate_justification(self, seat_details: str, cv_context: str) -> Dict[str, Any]:
        ...

    def transcribe_audio(self, audio_path: Path, model: str, prompt: str | None = None) -> str:
        ...


class LiveOpenAIBackend(OpenAIBackendProtocol):
    """Live backend that talks to OpenAI/Azure."""

    def __init__(self, settings: Settings):
        self.settings = settings
        if settings.use_azure_openai:
            if not all([settings.azure_endpoint, settings.azure_api_version, settings.openai_api_key_str]):
                raise ValueError("Azure settings (endpoint, version, key) are not fully configured.")
            self.client = AzureOpenAI(
                api_key=settings.openai_api_key_str,
                api_version=settings.azure_api_version,
                azure_endpoint=settings.azure_endpoint,
            )
        else:
            if not settings.openai_api_key_str:
                raise ValueError("OPENAI_API_KEY is not set.")
            self.client = OpenAI(api_key=settings.openai_api_key_str)

    def transcribe_audio(self, audio_path: Path, model: str, prompt: str | None = None) -> str:
        with open(audio_path, "rb") as audio_file:
            response = self.client.audio.transcriptions.create(
                model=model,
                file=audio_file,
                prompt=prompt,
                response_format="text",
            )
        if hasattr(response, "text"):
            return response.text
        return str(response)

    def _schema_json(self, model_cls: Type[BaseModel]) -> str:
        if hasattr(model_cls, "schema_json"):
            return model_cls.schema_json(indent=2)  # pydantic v1
        if hasattr(model_cls, "model_json_schema"):
            return json.dumps(model_cls.model_json_schema(), indent=2)  # pydantic v2
        return "{}"

    def _get_structured_response(
            self,
            prompt: str,
            system_prompt: str,
            model: str,
            pydantic_model: Type[BaseModel],
    ) -> Dict[str, Any]:
        messages = [
            {
                "role": "system",
                "content": (
                    f"{system_prompt}\n\n"
                    "You must respond with JSON matching the following Pydantic schema:\n"
                    f"{self._schema_json(pydantic_model)}"
                ),
            },
            {"role": "user", "content": prompt},
        ]
        response = self.client.chat.completions.create(
            model=model,
            response_format={"type": "json_object"},
            messages=messages,
        )
        content = response.choices[0].message.content
        usage_obj = getattr(response, "usage", None)
        usage = usage_obj.model_dump() if hasattr(usage_obj, "model_dump") else None
        provider = "azure_openai" if self.settings.use_azure_openai else "openai"
        log_chat(
            messages=messages,
            model=model,
            response_content=content,
            provider=provider,
            usage=usage,
            meta={"pydantic_model": getattr(pydantic_model, "__name__", "Unknown")},
        )
        return json.loads(content)

    def get_structured_criteria(self, text: str, model: str, settings: Settings) -> Dict[str, Any]:
        role_lex_list = load_role_lexicon(settings.lexicon_dir)
        tech_lex_list = load_tech_synonyms(settings.lexicon_dir)
        domain_lex_list = load_domain_lexicon(settings.lexicon_dir)

        system_prompt = f"""
        You are a TA (Talent Acquisition) expert. Your task is to parse a user's free-text project brief
        into a structured JSON object.

        Available Role Lexicon: {json.dumps(role_lex_list, indent=2)}
        Available Tech Lexicon: {json.dumps(tech_lex_list, indent=2)}
        Available Domain Lexicon: {json.dumps(domain_lex_list, indent=2)}

        Strictly follow these rules:
        1.  Map all found skills, roles, and domains to their *canonical* keys from the lexicons provided.
        2.  If a `team_size` or specific roles (e.g., "2 .net devs") are mentioned, populate the `team_size.members` list.
        3.  `tech_stack` should be a rollup of *all* technologies mentioned in the brief.
        """
        return self._get_structured_response(
            prompt=text,
            system_prompt=system_prompt,
            model=model,
            pydantic_model=LLMCriteria,
        )

    def get_candidate_justification(self, seat_details: str, cv_context: str) -> Dict[str, Any]:
        system_prompt = """
        You are an expert Talent Acquisition manager. Your task is to evaluate a candidate's CV
        against a specific role's requirements.

        You will be given:
        1.  [ROLE]: A JSON object describing the role's requirements (role, seniority, must-have tech, nice-to-have tech, domains).
        2.  [CV]: The candidate's CV context (summary, experience, and tags).

        Your task is to provide a structured JSON justification.
        - `match_summary`: A 1-2 sentence executive summary.
        - `strength_analysis`: Bullet points of specific strengths, citing CV evidence.
        - `gap_analysis`: Bullet points of missing skills or gaps.
        - `overall_match_score`: A float from 0.0 to 1.0.
        """

        prompt = f"[ROLE]\n{seat_details}\n\n[CV]\n{cv_context}"

        return self._get_structured_response(
            prompt=prompt,
            system_prompt=system_prompt,
            model=self.settings.openai_model,
            pydantic_model=CandidateJustification,
        )

    def get_structured_cv(
            self,
            raw_text: str,
            role_folder_hint: str,
            model: str,
            settings: Settings,
    ) -> Dict[str, Any]:
        role_lex_list = load_role_lexicon(settings.lexicon_dir)
        tech_lex_list = load_tech_synonyms(settings.lexicon_dir)
        domain_lex_list = load_domain_lexicon(settings.lexicon_dir)
        expertise_lex_list = load_expertise_lexicon(settings.lexicon_dir)

        role_candidates = _select_candidates(role_lex_list, raw_text, role_folder_hint, max_candidates=25, fallback=25)
        domain_candidates = _select_candidates(domain_lex_list, raw_text, role_folder_hint, max_candidates=30, fallback=30)
        tech_candidates = _select_candidates(tech_lex_list, raw_text, role_folder_hint, max_candidates=80, fallback=80)
        expertise_candidates = _select_candidates(expertise_lex_list, raw_text, role_folder_hint, max_candidates=30, fallback=30)
        lexicon_hash = _lexicon_fingerprint(role_lex_list, tech_lex_list, domain_lex_list, expertise_lex_list)

        system_prompt = f"""
        You are an expert CV parser. Your task is to parse raw text from a CV slide deck
        into a structured JSON object.

        You are given a HINT: the normalized parent folder for this CV is '{role_folder_hint}'.

        Lexicon snapshot hash: {lexicon_hash}
        Role candidates (canonical keys): {json.dumps(role_candidates, indent=2)}
        Domain candidates (canonical keys): {json.dumps(domain_candidates, indent=2)}
        Tech candidates (canonical keys, truncated to most likely matches): {json.dumps(tech_candidates, indent=2)}
        Expertise candidates (canonical keys): {json.dumps(expertise_candidates, indent=2)}

        Strictly follow these rules:
        1.  `source_folder_role_hint`:
            * Analyze the HINT: `{role_folder_hint}`.
            * Determine if this hint represents a valid professional role.
            * If it **is** a valid role, find the **best matching canonical key** from the Role candidates.
            * If the HINT is **not** a valid role, you **MUST** set this field to `null`.

        2.  `role_tags`: Extract roles from the CV text and map them ONLY to the Role candidates.
        3.  `expertise_tags`: Infer expertise areas and map them ONLY to the Expertise candidates.
        4.  `tech_tags`: Extract technologies from the CV text and map them ONLY to the Tech candidates.
        5.  `qualifications`: Build a dictionary of lists using these keys: `programming_languages`, `databases`, `devops_tools`, `tools_and_technologies`, `other`. Normalize items to lowercase text; when a value is in Tech candidates, use the canonical key.
        6.  `experience` entries must include:
            * `project_description`: 1-3 sentences summarizing the project/product.
            * `responsibilities`: list of bullet strings preserving the candidate's described duties.
            * `domain_tags` / `tech_tags`: map ONLY to the provided Domain/Tech candidates.
        7.  `unmapped_tags`: List any tech/tools found but *not* in the Tech candidates as a comma-separated string.

        Additional guardrails:
        - Only use canonical keys shown in the candidate lists. Do NOT invent or rephrase keys.
        - If no candidate fits, leave the field empty (or null where allowed) instead of guessing.
        - Prefer precision over recall; incorrect mappings are worse than leaving a field empty.
        """

        return self._get_structured_response(
            prompt=raw_text,
            system_prompt=system_prompt,
            model=model,
            pydantic_model=LLMCV,
        )


class StubOpenAIBackend(OpenAIBackendProtocol):
    """Fixture-backed backend for deterministic, offline runs."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.fixture_dir = settings.llm_stub_dir

    def _fixture_path(self, name: str) -> Any:
        return self.fixture_dir / name

    def _load_fixture(self, name: str) -> Dict[str, Any]:
        path = self._fixture_path(name)
        if not path.exists():
            raise FileNotFoundError(f"Stub LLM fixture missing: {path}")
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    def _pick_cv_fixture(self, raw_text: str, role_folder_hint: str) -> str:
        text = f"{raw_text} {role_folder_hint}".lower()
        if "front" in text and self._fixture_path("structured_cv_frontend.json").exists():
            return "structured_cv_frontend.json"
        if "back" in text and self._fixture_path("structured_cv_backend.json").exists():
            return "structured_cv_backend.json"
        return "structured_cv.json"

    def get_structured_criteria(self, text: str, model: str, settings: Settings) -> Dict[str, Any]:
        return self._load_fixture("structured_criteria.json")

    def get_structured_cv(self, raw_text: str, role_folder_hint: str, model: str, settings: Settings) -> Dict[str, Any]:
        fixture_name = self._pick_cv_fixture(raw_text, role_folder_hint)
        return self._load_fixture(fixture_name)

    def get_candidate_justification(self, seat_details: str, cv_context: str) -> Dict[str, Any]:
        return self._load_fixture("candidate_justification.json")

    def transcribe_audio(self, audio_path: Path, model: str, prompt: str | None = None) -> str:
        fixture_path = self._fixture_path("audio_transcription.txt")
        if fixture_path.exists():
            return fixture_path.read_text(encoding="utf-8").strip()
        return f"Stub transcript for {audio_path.name}"


class OpenAIClient:
    """Adapter around OpenAI/Azure with optional stub backend for explicit tests."""

    def __init__(self, settings: Settings, backend: OpenAIBackendProtocol | None = None):
        self.settings = settings
        self.backend = backend or LiveOpenAIBackend(settings)

    def get_structured_criteria(self, text: str, model: str, settings: Settings) -> Dict[str, Any]:
        return self.backend.get_structured_criteria(text, model, settings)

    def get_candidate_justification(self, seat_details: str, cv_context: str) -> Dict[str, Any]:
        return self.backend.get_candidate_justification(seat_details, cv_context)

    def get_structured_cv(
            self,
            raw_text: str,
            role_folder_hint: str,
            model: str,
            settings: Settings,
    ) -> Dict[str, Any]:
        return self.backend.get_structured_cv(raw_text, role_folder_hint, model, settings)

    def transcribe_audio(self, audio_path: str | Path, model: str | None = None, prompt: str | None = None) -> str:
        path_obj = Path(audio_path)
        model_name = model or self.settings.openai_audio_model
        return self.backend.transcribe_audio(path_obj, model_name, prompt)

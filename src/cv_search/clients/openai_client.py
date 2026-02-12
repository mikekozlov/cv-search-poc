from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Protocol, Type

from openai import AzureOpenAI, OpenAI

from cv_search.config.settings import Settings
from cv_search.lexicon.loader import (
    load_domain_lexicon,
    load_expertise_lexicon,
    load_role_lexicon,
)
from cv_search.llm.schemas import (
    CandidateJustification,
    CandidateRankingResponse,
    CompactRankingResponse,
    LLMCriteria,
    LLMStructuredBrief,
)
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


def _prioritize_full_lexicon(
    lexicon: List[str],
    text: str,
    role_hint: str,
    *,
    max_candidates: int,
) -> List[str]:
    """Return the full lexicon ordered by best matches first."""
    top_matches = _select_candidates(
        lexicon,
        text,
        role_hint,
        max_candidates=max_candidates,
        fallback=max_candidates,
    )
    remaining = [item for item in lexicon if item not in top_matches]
    return top_matches + remaining


def _normalize_brief_tokens(text: str) -> str:
    """Normalize brief text to surface common aliases like .net -> dotnet, c# -> csharp."""
    norm = text.replace(".net", " dotnet ").replace("c#", " csharp ")
    norm = re.sub(r"\s+", " ", norm)
    return norm.strip()


class LLMCV(BaseModel):
    name: str | None = None
    seniority: str
    role_tags: List[str]
    expertise_tags: List[str] = Field(default_factory=list)
    summary: str | None = None
    rationale: str = Field(
        description=(
            "Short, user-facing explanation of how tags and experience entries were derived from "
            "the CV text (key evidence only). This is not hidden chain-of-thought."
        )
    )
    experience: List[Dict[str, Any]]
    tech_tags: List[str]
    source_folder_role_hint: str | None = None


class OpenAIBackendProtocol(Protocol):
    def get_structured_brief(self, text: str, model: str, settings: Settings) -> Dict[str, Any]: ...

    def get_structured_criteria(
        self, text: str, model: str, settings: Settings
    ) -> Dict[str, Any]: ...

    def get_structured_cv(
        self, raw_text: str, role_folder_hint: str, model: str, settings: Settings
    ) -> Dict[str, Any]: ...

    def get_candidate_justification(self, seat_details: str, cv_context: str) -> Dict[str, Any]: ...

    def get_presale_team_plan(
        self, brief: str, criteria: Dict[str, Any], model: str, settings: Settings
    ) -> Dict[str, Any]: ...

    def transcribe_audio(self, audio_path: Path, model: str, prompt: str | None = None) -> str: ...

    def get_candidate_ranking(
        self,
        seat_details: str,
        candidates_context: str,
        pool_size: int,
        top_k: int = 3,
        compact_output: bool = True,
    ) -> Dict[str, Any]: ...


class LiveOpenAIBackend(OpenAIBackendProtocol):
    """Live backend that talks to OpenAI/Azure."""

    def __init__(self, settings: Settings):
        self.settings = settings
        if settings.use_azure_openai:
            if not all(
                [settings.azure_endpoint, settings.azure_api_version, settings.openai_api_key_str]
            ):
                raise ValueError(
                    "Azure settings (endpoint, version, key) are not fully configured."
                )
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
        include_usage: bool = False,
        seed: int | None = None,
    ) -> Dict[str, Any]:
        messages = [
            {
                "role": "system",
                "content": (
                    f"{system_prompt}\n\n"
                    "Rationale rules:\n"
                    "- Include a top-level field `rationale` that briefly explains the key evidence and "
                    "decisions behind the output (1-3 sentences is usually enough).\n"
                    "- This rationale is a user-facing summary; do NOT output hidden chain-of-thought or "
                    "step-by-step internal reasoning.\n\n"
                    "You must respond with JSON matching the following Pydantic schema:\n"
                    f"{self._schema_json(pydantic_model)}"
                ),
            },
            {"role": "user", "content": prompt},
        ]
        start_time = time.perf_counter()
        optional_params: Dict[str, Any] = {}
        if seed is not None:
            optional_params["seed"] = seed
        if self.settings.openai_reasoning_effort:
            optional_params["reasoning_effort"] = self.settings.openai_reasoning_effort
        response = self.client.chat.completions.create(
            model=model,
            response_format={"type": "json_object"},
            messages=messages,
            **optional_params,
        )
        duration_ms = int((time.perf_counter() - start_time) * 1000)
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
            duration_ms=duration_ms,
        )
        parsed = json.loads(content)
        if include_usage:
            parsed["_usage"] = usage
        return parsed

    def get_structured_brief(self, text: str, model: str, settings: Settings) -> Dict[str, Any]:
        role_lex_list = load_role_lexicon(settings.lexicon_dir)
        domain_lex_list = load_domain_lexicon(settings.lexicon_dir)
        expertise_lex_list = load_expertise_lexicon(settings.lexicon_dir)

        role_candidates = _prioritize_full_lexicon(
            role_lex_list,
            _normalize_brief_tokens(text),
            "",
            max_candidates=30,
        )
        domain_candidates = _prioritize_full_lexicon(
            domain_lex_list,
            text,
            "",
            max_candidates=30,
        )
        expertise_candidates = _prioritize_full_lexicon(
            expertise_lex_list,
            text,
            "",
            max_candidates=30,
        )

        system_prompt = f"""
        You are a presale TA lead. Given a client brief, produce canonical search Criteria and presale staffing using ONLY the provided lexicons.

        Translation rule:
        - If the brief is not in English, first translate it to clear English (preserve technical terms). Use ONLY that English translation for all matching and reasoning.
        - Include a top-level field `english_brief` with the English translation of the client brief.

        Role candidates (canonical keys): {json.dumps(role_candidates, indent=2)}
        Domain candidates (canonical keys): {json.dumps(domain_candidates, indent=2)}
        Expertise candidates (canonical keys): {json.dumps(expertise_candidates, indent=2)}

        EXPERTISE vs TECH DISTINCTION (CRITICAL):
        - expertise: Broad specialization patterns from Expertise candidates (e.g., python_backend, react_frontend, devops).
          Describes the KIND of work the role does. Use 1-2 keys per member.
        - tech_tags: Specific concrete technologies mentioned in the brief (e.g., Python, FastAPI, React, PostgreSQL).
          The actual tools/frameworks this role needs. Use the tech names as written in the brief.
        - nice_to_have: Secondary/optional technologies from the brief.

        CRITICAL ROLE MAPPING RULES (follow these EXACTLY):
        - "backend developer/engineer" or "server-side developer" → backend_engineer (regardless of tech stack like C++, Java, Python, etc.)
        - "frontend developer/engineer" or "UI developer" → frontend_engineer
        - "fullstack developer/engineer" → fullstack_engineer
        - "mobile developer/engineer" or "iOS/Android developer" → mobile_engineer
        - "embedded developer/engineer" → embedded_engineer (ONLY when explicitly mentioned as "embedded" or for IoT/firmware/hardware work)
        - "devops engineer" or "platform engineer" → devops_engineer
        - "data engineer" → data_engineer
        - "QA engineer/tester" → qa_engineer
        - The tech stack (C++, Java, Python, etc.) does NOT determine the role. A "C++ backend developer" is still a backend_engineer, not an embedded_engineer.

        Strict rules (apply to BOTH criteria and presale_team):
        - Use ONLY canonical keys from the provided candidate lists (for roles, domains, expertise). Do NOT invent or rephrase keys.
        - Output JSON matching the schema shown below (Criteria block + presale_team). Leave fields empty rather than guessing.

        Criteria rules:
        - Populate team_size.members whenever a role or hiring need is implied. Each member must include:
          - role (canonical key from Role candidates)
          - seniority (normalize mid/mid-level->middle, jr->junior, sr/senior->senior)
          - domains (subset of Domain candidates)
          - expertise (1-2 keys from Expertise candidates describing specialization)
          - tech_tags (must-have technologies from the brief)
          - nice_to_have (optional/secondary technologies from the brief)
        - tech_stack is the deduplicated rollup of explicit technologies mentioned in the brief. List only tech explicitly present; do not invent.
        - expert_roles is the set of canonical roles relevant to the brief. It MUST include every role used anywhere in the response: any roles assigned to team_size.members, plus all roles listed in presale_team.minimum_team and presale_team.extended_team. Deduplicate.
        - If the brief does not mention a domain, return an empty domain list; do NOT guess a domain.

        Presale team rules:
        - Hard limits (non-negotiable):
          - minimum_team MUST contain 1-3 roles total.
          - extended_team MUST contain 0-3 roles total.
        - minimum_team: smallest cross-functional set to run discovery and craft a proposal. Prefer 2-3 roles when possible, but never exceed 3.
        - extended_team: optional specialists/advisors to de-risk integrations, compliance, security, analytics, or delivery. Include only the highest-leverage roles; never exceed 3.
        - If you believe more roles are needed, pick the best 3 for each list by impact/risk-reduction and omit the rest (do not create extra lists and do not combine roles into invented keys).
        - Use ONLY canonical role keys from Role candidates. Deduplicate roles and order by priority.
        - Prefer roles that align with the brief's domain, stack, integrations, and regulatory needs.
        """

        prompt = f"Client brief:\n{text.strip()}"

        return self._get_structured_response(
            prompt=prompt,
            system_prompt=system_prompt,
            model=model,
            pydantic_model=LLMStructuredBrief,
        )

    def get_structured_criteria(self, text: str, model: str, settings: Settings) -> Dict[str, Any]:
        role_lex_list = load_role_lexicon(settings.lexicon_dir)
        domain_lex_list = load_domain_lexicon(settings.lexicon_dir)
        expertise_lex_list = load_expertise_lexicon(settings.lexicon_dir)

        role_candidates = _prioritize_full_lexicon(
            role_lex_list,
            _normalize_brief_tokens(text),
            "",
            max_candidates=30,
        )
        domain_candidates = _prioritize_full_lexicon(
            domain_lex_list,
            text,
            "",
            max_candidates=30,
        )
        expertise_candidates = _prioritize_full_lexicon(
            expertise_lex_list,
            text,
            "",
            max_candidates=30,
        )

        system_prompt = f"""
        You are a TA lead. Given a client brief, produce canonical search Criteria using ONLY the provided lexicons.

        Translation rule:
        - If the brief is not in English, first translate it to clear English (preserve technical terms). Use ONLY that English translation for all matching and reasoning.
        - Include a top-level field `english_brief` with the English translation of the client brief.

        Role candidates (canonical keys): {json.dumps(role_candidates, indent=2)}
        Domain candidates (canonical keys): {json.dumps(domain_candidates, indent=2)}
        Expertise candidates (canonical keys): {json.dumps(expertise_candidates, indent=2)}

        EXPERTISE vs TECH DISTINCTION (CRITICAL):
        - expertise: Broad specialization patterns from Expertise candidates (e.g., python_backend, react_frontend, devops).
          Describes the KIND of work the role does. Use 1-2 keys per member.
        - tech_tags: Specific concrete technologies mentioned in the brief (e.g., Python, FastAPI, React, PostgreSQL).
          The actual tools/frameworks this role needs. Use the tech names as written in the brief.
        - nice_to_have: Secondary/optional technologies from the brief.

        CRITICAL ROLE MAPPING RULES (follow these EXACTLY):
        - "backend developer/engineer" or "server-side developer" → backend_engineer (regardless of tech stack like C++, Java, Python, etc.)
        - "frontend developer/engineer" or "UI developer" → frontend_engineer
        - "fullstack developer/engineer" → fullstack_engineer
        - "mobile developer/engineer" or "iOS/Android developer" → mobile_engineer
        - "embedded developer/engineer" → embedded_engineer (ONLY when explicitly mentioned as "embedded" or for IoT/firmware/hardware work)
        - "devops engineer" or "platform engineer" → devops_engineer
        - "data engineer" → data_engineer
        - "QA engineer/tester" → qa_engineer
        - The tech stack (C++, Java, Python, etc.) does NOT determine the role. A "C++ backend developer" is still a backend_engineer, not an embedded_engineer.

        Strict rules:
        - Use ONLY canonical keys from the provided candidate lists. Do NOT invent or rephrase keys.
        - Output JSON matching the Criteria schema shown below. Leave fields empty rather than guessing.

        Criteria rules:
        - expert_roles: First, identify ALL canonical roles needed to deliver the project described in the brief.
        - team_size.members: Create ONE member entry for EACH role in expert_roles. Each member must include:
          - role (canonical key from Role candidates)
          - seniority (normalize mid/mid-level->middle, jr->junior, sr/senior->senior; default to "senior" if unclear)
          - domains (subset of Domain candidates relevant to this role)
          - expertise (1-2 keys from Expertise candidates describing specialization, e.g., python_backend)
          - tech_tags (must-have technologies from the brief, e.g., Python, FastAPI)
          - nice_to_have (optional/secondary technologies from the brief)
          - rationale (1 sentence explaining why this role is needed for the project)
        - IMPORTANT: The count of team_size.members MUST equal the count of expert_roles. Every role needs a corresponding member.
        - tech_stack is the deduplicated rollup of explicit technologies mentioned in the brief. List only tech explicitly present; do not invent.
        - If the brief does not mention a domain, return an empty domain list; do NOT guess a domain.
        - If the brief is generic hiring intent like "need a developer/engineer" with no role qualifiers, domain, seniority, or technologies, return empty expert_roles and team_size (null/empty) instead of guessing a generic role.
        """

        prompt = f"Client brief:\n{text.strip()}"

        return self._get_structured_response(
            prompt=prompt,
            system_prompt=system_prompt,
            model=model,
            pydantic_model=LLMCriteria,
        )

    def get_presale_team_plan(
        self, brief: str, criteria: Dict[str, Any], model: str, settings: Settings
    ) -> Dict[str, Any]:
        payload = self.get_structured_brief(brief, model, settings)
        presale_payload = payload.get("presale_team", payload)
        if isinstance(presale_payload, dict):
            return presale_payload
        return {}

    def get_candidate_justification(self, seat_details: str, cv_context: str) -> Dict[str, Any]:
        system_prompt = """
        You are an expert Talent Acquisition manager. Your task is to evaluate a candidate's CV
        against a specific role's requirements.

        You will be given:
        1.  [ROLE]: A JSON object describing the role's requirements (role, seniority, must-have tech, nice-to-have tech, domains).
        2.  [CV]: The candidate's CV context (summary, experience, and tags).

        Your task is to provide a structured JSON justification.
        - `match_summary`: Exactly 1 sentence executive summary focused on the smost important fit signals.
        - `strength_analysis`: A list with exactly 1 item; that item must be exactly 1 sentence stating the single most important strength and citing CV evidence.
        - `gap_analysis`: A list with exactly 1 item; that item must be exactly 1 sentence stating the single most important gap (or "No material gaps identified" if none).
        - `overall_match_score`: A float from 0.0 to 1.0.
        """

        prompt = f"[ROLE]\n{seat_details}\n\n[CV]\n{cv_context}"

        return self._get_structured_response(
            prompt=prompt,
            system_prompt=system_prompt,
            model=self.settings.openai_model,
            pydantic_model=CandidateJustification,
        )

    def get_candidate_ranking(
        self,
        seat_details: str,
        candidates_context: str,
        pool_size: int,
        top_k: int = 3,
        compact_output: bool = True,
    ) -> Dict[str, Any]:
        # Base system prompt shared between modes
        base_prompt = """You are an expert Talent Acquisition manager.

You will be given:
1. [POOL_SIZE]: The total number of candidates to rank.
2. [TOP_K]: The number of top candidates that need full verdicts.
3. [ROLE]: A JSON object describing the role requirements.
4. [CANDIDATES]: Candidates with candidate_id, lexical signals, and CV context.

CANDIDATE ATTRIBUTES:
- lexical_score: Pre-computed relevance score (higher = better lexical fit)
- must_hit_count: Number of must_have tags matched
- matched_must_have: Which must_have tags were matched
- nice_hit_count: Number of nice_to_have tags matched
- expertise_hit: 1 if expertise specialization matches, 0 otherwise
- domain_hit: 1 if domain experience matches, 0 otherwise
- last_updated: CV update date (prefer recent)

SCORING RUBRIC (0.0-1.0):
- 0.90-1.00: Exceptional - ALL must-haves with depth, expertise+domain match, all nice-to-haves
- 0.75-0.89: Strong - ALL must-haves, expertise OR domain match, most nice-to-haves
- 0.60-0.74: Moderate - ALL must-haves but variable depth, partial expertise/domain
- 0.40-0.59: Weak - Most must-haves, gaps exist, no expertise match
- 0.00-0.39: Poor - Missing multiple must-haves, wrong tech focus

SCORING RULES:
- Use FULL range to differentiate candidates
- Gaps identified → score MUST be < 0.90
- Missing expertise → cap at 0.85
- Domain mismatch → cap at 0.85
- Spread between highest/lowest >= 0.15"""

        if compact_output:
            # Tiered output: scores for all, full verdicts for top_k only
            output_rules = """
OUTPUT (TIERED - scores for all, verdicts for top_k only):
- all_scores: List ALL candidates ranked best-to-worst with {candidate_id, overall_match_score}. Length MUST equal POOL_SIZE.
- top_k_verdicts: Full verdicts for the TOP_K candidates ONLY. Each verdict has:
  - candidate_id, match_summary (1 sentence), strength_analysis (1 item), gap_analysis (1 item), overall_match_score
- rationale: Brief explanation of ranking factors.
- Do NOT generate narratives for candidates ranked below TOP_K."""
            schema_model = CompactRankingResponse
        else:
            # Legacy full output: full verdicts for all candidates
            output_rules = """
OUTPUT (FULL - verdicts for all candidates):
- ranked_candidates: List ALL candidates ranked best-to-worst. Length MUST equal POOL_SIZE. Each has:
  - candidate_id, match_summary (1 sentence), strength_analysis (1 item), gap_analysis (1 item), overall_match_score
- rationale: Brief explanation of ranking factors."""
            schema_model = CandidateRankingResponse

        system_prompt = (
            base_prompt
            + output_rules
            + """

SCHEMA NOTE: Ignore 'model_config' or 'extra' fields - focus on required output fields."""
        )

        prompt = (
            f"[POOL_SIZE]\n{int(pool_size)}\n\n"
            f"[TOP_K]\n{int(top_k)}\n\n"
            f"[ROLE]\n{seat_details}\n\n"
            f"[CANDIDATES]\n{candidates_context}"
        )

        # Use a fixed seed for reproducibility (best effort, not guaranteed by Azure)
        return self._get_structured_response(
            prompt=prompt,
            system_prompt=system_prompt,
            model=self.settings.openai_model,
            pydantic_model=schema_model,
            include_usage=True,
            seed=42,
        )

    def get_structured_cv(
        self,
        raw_text: str,
        role_folder_hint: str,
        model: str,
        settings: Settings,
    ) -> Dict[str, Any]:
        role_lex_list = load_role_lexicon(settings.lexicon_dir)
        domain_lex_list = load_domain_lexicon(settings.lexicon_dir)
        expertise_lex_list = load_expertise_lexicon(settings.lexicon_dir)

        role_candidates = _prioritize_full_lexicon(
            role_lex_list,
            raw_text,
            role_folder_hint,
            max_candidates=25,
        )
        domain_candidates = _prioritize_full_lexicon(
            domain_lex_list,
            raw_text,
            role_folder_hint,
            max_candidates=30,
        )
        expertise_candidates = _prioritize_full_lexicon(
            expertise_lex_list,
            raw_text,
            role_folder_hint,
            max_candidates=30,
        )

        system_prompt = f"""
        You are an expert CV parser. Your task is to parse raw text from a CV slide deck
        into a structured JSON object.

        You are given a HINT: the normalized parent folder for this CV is '{role_folder_hint}'.

        Role candidates (canonical keys): {json.dumps(role_candidates, indent=2)}
        Domain candidates (canonical keys): {json.dumps(domain_candidates, indent=2)}
        Expertise candidates (canonical keys): {json.dumps(expertise_candidates, indent=2)}

        Strictly follow these rules:
        1.  `name`:
            * Extract the candidate's full name if present; otherwise set this field to `null`.
            * Do NOT repeat the name in `summary`, `experience`, or `responsibilities`.

        2.  `seniority`:
            * Return one of: "junior", "middle", "senior", "lead", "manager".
            * Normalize mid/mid-level -> middle; jr/junior -> junior; sr/senior -> senior; lead/staff/tech lead -> lead; manager/principal/director/head -> manager.
            * If the CV does not provide a clear signal, return "senior".

        3.  `source_folder_role_hint`:
            * Analyze the HINT: `{role_folder_hint}`.
            * Determine if this hint represents a valid professional role.
            * If it **is** a valid role, find the **best matching canonical key** from the Role candidates.
            * If the HINT is **not** a valid role, you **MUST** set this field to `null`.

        4.  `role_tags`: Extract roles from the CV text and map them ONLY to the Role candidates.
        5.  `tech_tags`: Extract technologies from the CV text as raw strings; do NOT use domain or expertise keys. Include the explicit tools/stack named in the CV (e.g., '.NET Core 6', '.NET Core 8', 'Kafka', 'MassTransit', 'PostgreSQL', 'Redis', 'Docker', 'Kubernetes', 'AKS', 'Azure Functions', 'Blob Storage', 'OpenTelemetry', 'GitHub Actions'). Split multi-version/alias combos into separate items (e.g., '.NET Core 6/8' -> ['.net core 6', '.net core 8'], 'Kubernetes/AKS' -> ['kubernetes', 'aks']). Preserve versions when given. Deduplicate case-insensitively.
        6.  `domain_tags`: Use ONLY the Domain candidates. Map medical/clinical/healthcare cues (e.g., patient, clinic, hospital, EMR, pharma) to `healthtech`. Map banking/fintech/payments cues (e.g., banking, loans, savings, cards, BNPL, payments, trading, KYC/AML, PSPs) to `banking` or `fintech` as appropriate (payments/BNPL/cards/KYC/AML -> `fintech`; banking/loans/savings/digital banking -> `banking`). Do not leave this empty when domain cues exist; pick the best-fit domain per experience entry 
        7.  `experience`: If the text mentions any projects, responsibilities, or work history, you MUST return at least one experience entry. Each entry must include:
            * `project_description`: 1-3 sentences summarizing the project/product.
            * `responsibilities`: list of bullet strings preserving the candidate's described duties.
            * `domain_tags`: map ONLY to the provided Domain candidates. `tech_tags`: use the explicit technologies from the CV (same rules as #5, including splitting version/alias combos); do not return an empty experience list when work cues are present.
            * Include every distinct project/responsibility block mentioned in the CV; do NOT drop, merge, or summarize away entries. Preserve the ordering as presented in the CV.
        8.  `expertise_tags`: Infer expertise areas and map them ONLY to the Expertise candidates; return only the 2 most relevant items (<=2); leave empty if not clearly present.

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

    def _ensure_rationale(self, payload: Dict[str, Any], rationale: str) -> Dict[str, Any]:
        if not payload.get("rationale"):
            payload["rationale"] = rationale
        return payload

    def _ensure_nested_rationale(
        self, payload: Dict[str, Any], key: str, rationale: str
    ) -> Dict[str, Any]:
        nested = payload.get(key)
        if isinstance(nested, dict) and not nested.get("rationale"):
            nested["rationale"] = rationale
        return payload

    def _pick_cv_fixture(self, raw_text: str, role_folder_hint: str) -> str:
        text = f"{raw_text} {role_folder_hint}".lower()
        if "front" in text and self._fixture_path("structured_cv_frontend.json").exists():
            return "structured_cv_frontend.json"
        if "back" in text and self._fixture_path("structured_cv_backend.json").exists():
            return "structured_cv_backend.json"
        return "structured_cv.json"

    def get_structured_brief(self, text: str, model: str, settings: Settings) -> Dict[str, Any]:
        try:
            payload = self._load_fixture("structured_brief.json")
        except FileNotFoundError:
            criteria = self._load_fixture("structured_criteria.json")
            presale = self._load_fixture("presale_plan.json")
            payload = {"criteria": criteria, "presale_team": presale}

        payload = self._ensure_rationale(
            payload, "Stubbed rationale: deterministic brief parsing output."
        )
        payload = self._ensure_nested_rationale(
            payload, "criteria", "Stubbed rationale: deterministic criteria extraction output."
        )
        return payload

    def get_structured_criteria(self, text: str, model: str, settings: Settings) -> Dict[str, Any]:
        try:
            payload = self._load_fixture("structured_criteria.json")
        except FileNotFoundError:
            payload = self.get_structured_brief(text, model, settings)
            criteria_payload = payload.get("criteria", payload)
            if isinstance(criteria_payload, dict):
                return self._ensure_rationale(
                    criteria_payload, "Stubbed rationale: deterministic criteria extraction output."
                )
            return criteria_payload
        return self._ensure_rationale(
            payload, "Stubbed rationale: deterministic criteria extraction output."
        )

    def get_presale_team_plan(
        self, brief: str, criteria: Dict[str, Any], model: str, settings: Settings
    ) -> Dict[str, Any]:
        payload = self.get_structured_brief(brief, model, settings)
        presale = payload.get("presale_team", payload)
        return presale if isinstance(presale, dict) else {}

    def get_structured_cv(
        self, raw_text: str, role_folder_hint: str, model: str, settings: Settings
    ) -> Dict[str, Any]:
        fixture_name = self._pick_cv_fixture(raw_text, role_folder_hint)
        payload = self._load_fixture(fixture_name)
        return self._ensure_rationale(
            payload, "Stubbed rationale: deterministic CV parsing output."
        )

    def get_candidate_justification(self, seat_details: str, cv_context: str) -> Dict[str, Any]:
        payload = self._load_fixture("candidate_justification.json")
        return self._ensure_rationale(
            payload, "Stubbed rationale: deterministic candidate justification output."
        )

    def get_candidate_ranking(
        self,
        seat_details: str,
        candidates_context: str,
        pool_size: int,
        top_k: int = 3,
        compact_output: bool = True,
    ) -> Dict[str, Any]:
        # Deterministic stub: extract candidate ids from the XML-like prompt and rank ALL
        ids = re.findall(r'<candidate id="([^"]+)"', candidates_context)

        # Build scores for all candidates
        all_scores = []
        for idx, cid in enumerate(ids, start=1):
            score = max(0.0, 1.0 - 0.05 * (idx - 1))  # Gradual score decrease
            all_scores.append({"candidate_id": cid, "overall_match_score": score})

        # Build full verdicts for top_k candidates
        top_k_verdicts = []
        for idx, cid in enumerate(ids[:top_k], start=1):
            score = max(0.0, 1.0 - 0.05 * (idx - 1))
            top_k_verdicts.append(
                {
                    "candidate_id": cid,
                    "match_summary": f"Stub verdict for {cid}.",
                    "strength_analysis": ["Stub strength based on provided context."],
                    "gap_analysis": ["No material gaps identified."],
                    "overall_match_score": score,
                }
            )

        # Stub usage: estimate based on context length
        prompt_tokens = len(candidates_context.split()) + len(seat_details.split())
        # Compact mode: fewer completion tokens (scores for all + verdicts for top_k)
        completion_tokens = len(ids) * 10 + top_k * 40 if compact_output else len(ids) * 50

        if compact_output:
            return {
                "all_scores": all_scores,
                "top_k_verdicts": top_k_verdicts,
                "notes": "stub",
                "rationale": "Stubbed rationale: candidates ranked by deterministic fixture ordering.",
                "_usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                },
            }
        else:
            # Legacy format: full verdicts for all candidates
            ranked = []
            for idx, cid in enumerate(ids, start=1):
                score = max(0.0, 1.0 - 0.05 * (idx - 1))
                ranked.append(
                    {
                        "candidate_id": cid,
                        "match_summary": f"Stub verdict for {cid}.",
                        "strength_analysis": ["Stub strength based on provided context."],
                        "gap_analysis": ["No material gaps identified."],
                        "overall_match_score": score,
                    }
                )
            return {
                "ranked_candidates": ranked,
                "notes": "stub",
                "rationale": "Stubbed rationale: candidates ranked by deterministic fixture ordering.",
                "_usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                },
            }

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

    def get_structured_brief(self, text: str, model: str, settings: Settings) -> Dict[str, Any]:
        return self.backend.get_structured_brief(text, model, settings)

    def get_structured_criteria(self, text: str, model: str, settings: Settings) -> Dict[str, Any]:
        return self.backend.get_structured_criteria(text, model, settings)

    def get_presale_team_plan(
        self, brief: str, criteria: Dict[str, Any], model: str, settings: Settings
    ) -> Dict[str, Any]:
        return self.backend.get_presale_team_plan(brief, criteria, model, settings)

    def get_candidate_justification(self, seat_details: str, cv_context: str) -> Dict[str, Any]:
        return self.backend.get_candidate_justification(seat_details, cv_context)

    def get_candidate_ranking(
        self,
        seat_details: str,
        candidates_context: str,
        pool_size: int,
        top_k: int = 3,
        compact_output: bool = True,
    ) -> Dict[str, Any]:
        return self.backend.get_candidate_ranking(
            seat_details, candidates_context, pool_size, top_k, compact_output
        )

    def get_structured_cv(
        self,
        raw_text: str,
        role_folder_hint: str,
        model: str,
        settings: Settings,
    ) -> Dict[str, Any]:
        return self.backend.get_structured_cv(raw_text, role_folder_hint, model, settings)

    def transcribe_audio(
        self, audio_path: str | Path, model: str | None = None, prompt: str | None = None
    ) -> str:
        path_obj = Path(audio_path)
        model_name = model or self.settings.openai_audio_model
        return self.backend.transcribe_audio(path_obj, model_name, prompt)

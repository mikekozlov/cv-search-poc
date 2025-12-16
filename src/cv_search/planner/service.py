# src/cvsearch/planner.py
# Stateless business logic for deriving project/presale teams.
# Presale planning uses a provided LLM client; no DB or orchestration here.

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Any, Dict, List, Optional

from cv_search.clients.openai_client import OpenAIClient
from cv_search.config.settings import Settings
from cv_search.core.criteria import Criteria, SeniorityEnum, TeamMember, TeamSize
from cv_search.lexicon.loader import load_role_lexicon


class Planner:
    """
    Contains stateless business logic for deriving team compositions
    from a user request.
    """

    def __init__(self):
        # --- (Internal constant helpers) ---
        self._AI_TEXT_TOKENS = {
            "openai",
            "chatgpt",
            "gpt",
            "llm",
            "ai chatbot",
            "ai assistant",
            "assistant",
        }
        self._AI_TECH_TOKENS = {
            "machine_learning",
            "deep_learning",
            "pytorch",
            "tensorflow",
            "huggingface",
            "vertex_ai",
            "azure_ml",
        }
        self._MOBILE_TECH_TOKENS = {
            "flutter",
            "react_native",
            "android",
            "ios",
            "kotlin",
            "swift",
            "xamarin",
            "dart",
        }
        self._WEB_TECH_TOKENS = {"react", "angular", "vue", "svelte", "nextjs", "nuxt", "sveltekit"}
        self._BACKEND_TECH_HINTS = {
            "dotnet",
            "nodejs",
            "java",
            "python",
            "go",
            "rust",
            "php",
            "ruby",
            "scala",
        }
        self._BACKEND_NICE_DEFAULTS = ["rest", "openapi", "oauth2", "postgresql"]

    # ---------- private helpers (signal detection) ----------

    def _text_has_any(self, text: Optional[str], needles: set[str]) -> bool:
        if not text:
            return False
        t = text.lower()
        return any(n in t for n in needles)

    def _has_any(self, tokens: List[str], needles: set[str]) -> bool:
        s = set((tokens or []))
        return any(x in s for x in needles)

    def _first_present(self, tokens: List[str], ordered: List[str]) -> Optional[str]:
        st = set(tokens or [])
        for k in ordered:
            if k in st:
                return k
        return None

    def _normalize_roles(
        self, roles: List[str] | None, *, allowed: set[str] | None = None
    ) -> List[str]:
        """Lowercase/deduplicate role names and optionally filter to an allowed set."""
        normalized: List[str] = []
        seen = set()
        for role in roles or []:
            key = (role or "").strip().lower().replace(" ", "_").replace("-", "_")
            if not key or key in seen:
                continue
            if allowed is not None and key not in allowed:
                continue
            seen.add(key)
            normalized.append(key)
        return normalized

    # ---------- public: presale team derivation ----------

    def derive_presale_team(
        self,
        crit: Criteria,
        *,
        client: OpenAIClient,
        settings: Settings,
        raw_text: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Criteria:
        """
        Enriches Criteria with presale team arrays using an LLM, with deterministic fallback.
        """
        criteria_dict = self._criteria_dict(crit)
        role_lexicon = set(load_role_lexicon(settings.lexicon_dir))

        minimum = self._normalize_roles(
            criteria_dict.get("minimum_team") or crit.minimum_team, allowed=role_lexicon
        )
        extended = self._normalize_roles(
            criteria_dict.get("extended_team") or crit.extended_team, allowed=role_lexicon
        )

        if not minimum:
            presale_payload = criteria_dict.get("presale_team") or {}
            minimum = self._normalize_roles(
                presale_payload.get("minimum_team"), allowed=role_lexicon
            )
            extended = self._normalize_roles(
                presale_payload.get("extended_team"), allowed=role_lexicon
            )

        if not minimum:
            plan = client.get_presale_team_plan(
                brief=raw_text or "",
                criteria=criteria_dict,
                model=model or settings.openai_model,
                settings=settings,
            )

            minimum = self._normalize_roles(plan.get("minimum_team"), allowed=role_lexicon)
            extended = self._normalize_roles(plan.get("extended_team"), allowed=role_lexicon)

        if not minimum:
            raise ValueError("Presale LLM returned no minimum_team roles; cannot proceed.")

        crit.minimum_team = minimum
        crit.extended_team = extended
        crit.expert_roles = self._normalize_roles(
            (crit.expert_roles or []) + minimum + extended, allowed=role_lexicon
        )

        return crit

    # ---------- public: project seats derivation ----------

    def derive_project_seats(self, crit: Criteria, raw_text: Optional[str] = None) -> Criteria:
        """
        Deterministically build seat definitions (if not already provided) from normalized tech/features.
        May return zero seats when no canonical roles are implied.
        """
        if crit.team_size and (crit.team_size.members or 0):
            return crit

        techs = crit.tech_stack or []
        domains = crit.domain or []
        roles: List[TeamMember] = []

        ai = self._has_any(techs, self._AI_TECH_TOKENS) or self._text_has_any(
            raw_text, self._AI_TEXT_TOKENS
        )
        mobile = self._has_any(techs, self._MOBILE_TECH_TOKENS) or self._text_has_any(
            raw_text, {"ios", "android", "mobile"}
        )
        web = self._has_any(techs, self._WEB_TECH_TOKENS) or self._text_has_any(
            raw_text, {"web", "react", "frontend", "ui"}
        )
        needs_backend = self._has_any(techs, self._BACKEND_TECH_HINTS) or self._text_has_any(
            raw_text,
            {
                "donate",
                "payment",
                "stripe",
                "paypal",
                "consequence",
                "partner",
                "auth",
                "api",
                "backend",
            },
        )

        if mobile:
            must = (
                self._first_present(techs, ["flutter", "react_native", "android", "ios"])
                or "flutter"
            )
            roles.append(
                TeamMember(
                    role="mobile_engineer",
                    seniority=SeniorityEnum.senior,
                    domains=list(domains),
                    tech_tags=[must],
                    nice_to_have=[],
                    rationale=f"Mobile app presence implied; must-have {must}.",
                )
            )
        if web:
            fe_must = (
                self._first_present(techs, ["react", "nextjs", "vue", "angular", "svelte"])
                or "react"
            )
            roles.append(
                TeamMember(
                    role="frontend_engineer",
                    seniority=SeniorityEnum.senior,
                    domains=list(domains),
                    tech_tags=[fe_must if fe_must != "nextjs" else "react"],
                    nice_to_have=(["nextjs"] if fe_must == "react" or fe_must == "nextjs" else []),
                    rationale=f"Web client implied; must-have {fe_must}.",
                )
            )
        if needs_backend:
            musts = [t for t in techs if t in self._BACKEND_TECH_HINTS]
            roles.append(
                TeamMember(
                    role="backend_engineer",
                    seniority=SeniorityEnum.senior,
                    domains=list(domains),
                    tech_tags=musts,
                    nice_to_have=list(self._BACKEND_NICE_DEFAULTS),
                    rationale="APIs/auth/payments implied by flows; backend required.",
                )
            )
        if ai:
            roles.append(
                TeamMember(
                    role="ml_engineer",
                    seniority=SeniorityEnum.senior,
                    domains=list(domains),
                    tech_tags=[],
                    nice_to_have=["python", "mlops", "pytorch", "tensorflow"],
                    rationale="AI/assistant/chatbot mentioned; add ML engineering for integration & evals.",
                )
            )

        team = TeamSize(total=len(roles), members=roles)
        expert_roles = list({m.role for m in roles})

        return Criteria(
            domain=crit.domain or [],
            tech_stack=crit.tech_stack or [],
            expert_roles=expert_roles,
            project_type=crit.project_type or "greenfield",
            team_size=team,
            minimum_team=crit.minimum_team,
            extended_team=crit.extended_team,
        )

    # ---------- Helpers for project search (used by SearchProcessor) ----------

    def _criteria_dict(self, obj: Any) -> Dict[str, Any]:
        """Converts Criteria/dataclass/dict to a plain dict."""
        if isinstance(obj, dict):
            return obj
        if is_dataclass(obj):
            return asdict(obj)
        if isinstance(obj, Criteria):
            return json.loads(obj.to_json())
        return json.loads(json.dumps(obj))

    def _pack_single_seat_criteria(
        self, base_criteria: Dict[str, Any], seat: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Creates a new Criteria dict for a single seat."""
        expert = list(dict.fromkeys((base_criteria.get("expert_roles") or []) + [seat["role"]]))
        return {
            "domain": base_criteria.get("domain", []),
            "tech_stack": base_criteria.get("tech_stack", []),
            "expert_roles": expert,
            "project_type": base_criteria.get("project_type", "greenfield"),
            "team_size": {"total": 1, "members": [seat]},
        }

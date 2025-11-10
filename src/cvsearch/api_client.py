from __future__ import annotations
import os
import json
from typing import Any, Dict, List

import openai
from openai import OpenAI, AzureOpenAI

from src.cvsearch.settings import Settings
from src.cvsearch.justification import CandidateJustification

# Helper for Pydantic models
try:
    from pydantic.v1 import BaseModel, Field
except ImportError:
    from pydantic import BaseModel, Field

# --- Schemas for LLM responses ---
# These models define the expected JSON structure from the LLM.

class LLMCriteria(BaseModel):
    """
    Pydantic model for parsing a free-text project brief.
    """
    domain: List[str] = Field(..., description="List of canonical domain tags (e.g., 'fintech', 'healthtech').")
    tech_stack: List[str] = Field(..., description="List of canonical tech stack tags (e.g., 'python', 'react', 'dotnet').")
    expert_roles: List[str] = Field(..., description="List of canonical expert role tags (e.g., 'backend_engineer', 'frontend_engineer').")
    project_type: str | None = Field(None, description="The project type (e.g., 'greenfield', 'migration').")
    team_size: Dict[str, Any] | None = Field(None, description="Team size object, if specified.")

class LLMCV(BaseModel):
    """
    Pydantic model for parsing a raw CV text.
    """
    name: str | None = Field(None, description="Candidate's full name.")
    location: str | None = Field(None, description="Candidate's location (e.g., 'USA', 'Poland').")
    seniority: str = Field(..., description="Canonical seniority (e.g., 'junior', 'middle', 'senior', 'lead').")
    role_tags: List[str] = Field(..., description="List of canonical role tags (e.g., 'backend_engineer', 'data_analyst').")
    summary: str | None = Field(None, description="A brief professional summary.")
    experience: List[Dict[str, Any]] = Field(..., description="List of professional experiences.")
    tech_tags: List[str] = Field(..., description="A comprehensive list of all canonical tech tags mentioned.")
    unmapped_tags: str | None = Field(None, description="A comma-separated string of tags found in the CV but not in the lexicons.")
    source_folder_role_hint: str | None = Field(None, description="The role key derived from the CV's parent folder. If the folder name (e.g., 'John Doe') is not a role, this field must be null.")


class OpenAIClient:
    """
    A client for handling all interactions with the OpenAI or Azure OpenAI API.
    """
    def __init__(self, settings: Settings):
        self.settings = settings
        if settings.use_azure_openai:
            if not all([settings.azure_endpoint, settings.azure_api_version, settings.openai_api_key_str]):
                raise ValueError("Azure settings (endpoint, version, key) are not fully configured.")
            self.client = AzureOpenAI(
                api_key=settings.openai_api_key_str,
                api_version=settings.azure_api_version,
                azure_endpoint=settings.azure_endpoint
            )
        else:
            if not settings.openai_api_key_str:
                raise ValueError("OPENAI_API_KEY is not set.")
            self.client = OpenAI(api_key=settings.openai_api_key_str)

    def _get_structured_response(self, prompt: str, system_prompt: str, model: str, pydantic_model: BaseModel) -> Dict[str, Any]:
        """Helper to get structured JSON output from the LLM."""
        try:
            response = self.client.chat.completions.create(
                model=model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": f"{system_prompt}\n\nYou must respond with JSON matching the following Pydantic schema:\n{pydantic_model.schema_json(indent=2)}"},
                    {"role": "user", "content": prompt}
                ]
            )
            content = response.choices[0].message.content
            return json.loads(content)
        except Exception as e:
            print(f"Error in _get_structured_response: {e}")
            print(f"Model: {model}")
            # Fallback or re-raise
            raise

    def get_structured_criteria(self, text: str, model: str, settings: Settings) -> Dict[str, Any]:
        """Calls LLM to parse free-text request into structured Criteria."""

        # These imports are deferred to method-level to avoid
        # potential circular dependencies if lexicons ever needed this client.
        from src.cvsearch.lexicons import load_role_lexicon, load_tech_synonyms, load_domain_lexicon

        # Load the new list-based lexicons
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
            pydantic_model=LLMCriteria
        )

    def get_candidate_justification(self, seat_details: str, cv_context: str) -> Dict[str, Any]:
        """Calls LLM to justify a candidate match."""

        system_prompt = f"""
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
            model=self.settings.openai_model, # Use the default model for justification
            pydantic_model=CandidateJustification
        )

    def get_structured_cv(self, raw_text: str, role_folder_hint: str, model: str, settings: Settings) -> Dict[str, Any]:
        """Calls LLM to parse raw CV text into structured JSON."""

        from src.cvsearch.lexicons import load_role_lexicon, load_tech_synonyms, load_domain_lexicon

        # Load the new list-based lexicons
        role_lex_list = load_role_lexicon(settings.lexicon_dir)
        tech_lex_list = load_tech_synonyms(settings.lexicon_dir)
        domain_lex_list = load_domain_lexicon(settings.lexicon_dir)

        # Create a simple lookup map from the role list for the hint rule
        # e.g., "data_analyst": "bi_analyst" (from role_lexicon.json)
        # This is no longer possible with a flat list, so we trust the LLM
        # to find the "best matching canonical key" from the list.
        # The old role_synonym_map logic is removed.

        system_prompt = f"""
        You are an expert CV parser. Your task is to parse raw text from a CV slide deck
        into a structured JSON object.

        You are given a HINT: the normalized parent folder for this CV is '{role_folder_hint}'.
        
        Available Role Lexicon (Canonical Keys): {json.dumps(role_lex_list, indent=2)}
        Available Tech Lexicon (Canonical Keys): {json.dumps(tech_lex_list, indent=2)}
        Available Domain Lexicon (Canonical Keys): {json.dumps(domain_lex_list, indent=2)}

        Strictly follow these rules:
        1.  `source_folder_role_hint`:
            * Analyze the HINT: `{role_folder_hint}`.
            * Determine if this hint represents a valid professional role.
            * If it **is** a valid role, find the **best matching canonical key** from the Role Lexicon. For example, a hint of 'data_analyst' or 'bi developer' should be mapped to the canonical key 'bi_analyst'. A hint of 'etl_developer' should map to 'data_engineer'. Set this field to that canonical key.
            * If the HINT is **not** a valid role (e.g., it's a person's name like 'yaroslav_siomka' or a technology like 'ruby' or 'golang'), you **MUST** set this field to `null`.

        2.  `role_tags`: Extract all relevant roles from the CV *text itself*, mapping them to the Role Lexicon keys.
        3.  `tech_tags`: Extract all technologies from the CV *text*, mapping them to the Tech Lexicon keys.
        4.  `unmapped_tags`: List any tech/tools found but *not* in the lexicons as a comma-separated string.
        5.  `experience.domain_tags` / `experience.tech_tags`: Map these to the lexicons as well.
        """

        return self._get_structured_response(
            prompt=raw_text,
            system_prompt=system_prompt,
            model=model,
            pydantic_model=LLMCV
        )
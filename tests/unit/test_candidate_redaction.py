from __future__ import annotations

from cv_search.ingestion.redaction import (
    anonymized_candidate_name,
    redact_name_in_text,
    sanitize_cv_payload,
)


def test_anonymized_candidate_name_stable() -> None:
    name_first = anonymized_candidate_name("pptx-123", None, "Candidate")
    name_second = anonymized_candidate_name("pptx-123", None, "Candidate")
    salted = anonymized_candidate_name("pptx-123", "salt", "Candidate")

    assert name_first == name_second
    assert name_first.startswith("Candidate ")
    assert salted != name_first


def test_redact_name_in_text_removes_name_tokens() -> None:
    text = "John Doe led the project.\nDoe improved the API."
    redacted = redact_name_in_text(text, "John Doe", None)

    assert "John" not in redacted
    assert "Doe" not in redacted
    assert "led the project" in redacted


def test_sanitize_cv_payload_redacts_experience_and_preserves_name() -> None:
    cv = {
        "candidate_id": "pptx-456",
        "name": "Jane Roe",
        "summary": "Jane Roe is a backend engineer.",
        "experience": [
            {
                "project_description": "Jane built APIs.",
                "responsibilities": ["Roe owned the API.", "Jane tested deployments."],
            }
        ],
    }

    sanitized = sanitize_cv_payload(
        cv,
        candidate_id="pptx-456",
        name_hint="Jane Roe",
        filename_hint=None,
        salt=None,
        prefix="Candidate",
    )

    assert sanitized["name"] == "Jane Roe"
    assert "Jane" not in sanitized["summary"]
    assert "Roe" not in sanitized["summary"]

    exp = sanitized["experience"][0]
    assert "Jane" not in exp["project_description"]
    assert all("Roe" not in item for item in exp["responsibilities"])
    assert "highlights" not in exp

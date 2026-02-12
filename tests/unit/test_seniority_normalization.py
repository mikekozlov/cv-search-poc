from __future__ import annotations

import pytest

from cv_search.ingestion.seniority import normalize_seniority


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Senior (14+ years)", "senior"),
        ("Lead", "lead"),
        ("Senior/Lead", "lead"),
        ("Senior / Tech Lead", "lead"),
        ("Mid-level (4 years)", "middle"),
        ("mid-level", "middle"),
        ("Middle", "middle"),
        ("Junior", "junior"),
        ("Sr. Backend Engineer", "senior"),
        ("Jr Developer", "junior"),
        ("Staff Engineer", "lead"),
        ("Principal Engineer", "manager"),
        ("Not specified", "senior"),
        ("Software Engineer", "senior"),
        ("senior", "senior"),
        ("", "senior"),
        (None, "senior"),
    ],
)
def test_normalize_seniority(raw: str | None, expected: str) -> None:
    assert normalize_seniority(raw) == expected

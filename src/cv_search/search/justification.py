"""Compatibility wrapper for search-layer justification.

The canonical implementation of `JustificationService` lives in
`cv_search.llm.justification`, where it supports an optional `run_dir` for
prompt/response logging. The search package re-exports the same class to keep
call sites stable.
"""

from __future__ import annotations

from cv_search.llm.justification import JustificationService as _JustificationService

JustificationService = _JustificationService

__all__ = ["JustificationService"]

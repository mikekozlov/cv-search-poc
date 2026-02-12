"""Build markdown representation of a candidate CV.

Extracted from streamlit_page_utils so the API layer can use it
without depending on Streamlit.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _split_lines(value: str | None) -> list[str]:
    if not value:
        return []
    return [line.strip() for line in value.splitlines() if line.strip()]


def _format_timestamp(value: object, empty_label: str = "") -> str:
    if value is None:
        return empty_label
    if isinstance(value, datetime.datetime):
        return value.isoformat(timespec="seconds")
    text = str(value).strip()
    if not text:
        return empty_label
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.datetime.fromisoformat(normalized)
        return parsed.isoformat(timespec="seconds")
    except ValueError:
        return text


def build_cv_markdown(
    candidate_id: str,
    profile: Dict[str, Any] | None,
    context: Dict[str, Any] | None,
    experiences: List[Dict[str, Any]],
    qualifications: Dict[str, List[str]],
    tags: Dict[str, List[str]],
    raw_text: Optional[str] = None,
) -> str:
    """Build markdown representation of a CV."""
    lines: list[str] = ["# Candidate CV", ""]

    def _append_meta(label: str, value: object | None) -> None:
        if value is None or value == "":
            return
        lines.append(f"- {label}: {value}")

    _append_meta("Candidate ID", candidate_id)
    if profile:
        _append_meta("Name", profile.get("name"))
        _append_meta("Location", profile.get("location"))
        _append_meta("Seniority", profile.get("seniority"))
        last_updated = _format_timestamp(profile.get("last_updated"))
        _append_meta("Last Updated", last_updated)
        _append_meta("Source Filename", profile.get("source_filename"))
        _append_meta("Source Path", profile.get("source_gdrive_path"))
        _append_meta("Source Folder Role Hint", profile.get("source_folder_role_hint"))

    lines.append("")
    lines.append("## Summary")
    summary = (context or {}).get("summary_text") or "N/A"
    lines.append(summary)
    lines.append("")

    lines.append("## Experience")
    if experiences:
        for exp in experiences:
            title = exp.get("title") or "Experience"
            company = exp.get("company") or ""
            header = f"{title} @ {company}" if company else title
            lines.append(f"### {header}")

            start = exp.get("start") or ""
            end = exp.get("end") or ""
            if start or end:
                lines.append(f"- Dates: {start or 'unknown'} to {end or 'present'}")

            domains = _split_csv(exp.get("domain_tags_csv"))
            if domains:
                lines.append(f"- Domains: {', '.join(domains)}")

            techs = _split_csv(exp.get("tech_tags_csv"))
            if techs:
                lines.append(f"- Tech: {', '.join(techs)}")

            project = (exp.get("project_description") or "").strip()
            if project:
                lines.append(f"- Project: {project}")

            responsibilities = _split_lines(exp.get("responsibilities_text"))
            if responsibilities:
                lines.append("- Responsibilities:")
                lines.extend([f"  - {item}" for item in responsibilities])

            highlights = _split_lines(exp.get("highlights"))
            if highlights:
                lines.append("- Highlights:")
                lines.extend([f"  - {item}" for item in highlights])

            lines.append("")
    else:
        experience_text = (context or {}).get("experience_text") or "N/A"
        lines.append(experience_text)
        lines.append("")

    if qualifications:
        lines.append("## Qualifications")
        for category in sorted(qualifications.keys()):
            items = [item for item in qualifications.get(category, []) if item]
            if not items:
                continue
            if category:
                lines.append(f"### {category}")
            lines.extend([f"- {item}" for item in items])
            lines.append("")

    lines.append("## Tags")
    tag_labels = {
        "role": "Roles",
        "expertise": "Expertise",
        "tech": "Tech",
        "domain": "Domains",
        "seniority": "Seniority",
    }
    added_tag = False
    for tag_key, label in tag_labels.items():
        items = tags.get(tag_key, [])
        if items:
            lines.append(f"- {label}: {', '.join(items)}")
            added_tag = True
    if not added_tag:
        tags_text = (context or {}).get("tags_text")
        lines.append(tags_text or "N/A")
    lines.append("")

    if raw_text:
        lines.append("## Original Text")
        lines.append("")
        for line in raw_text.splitlines():
            lines.append(f"    {line}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"

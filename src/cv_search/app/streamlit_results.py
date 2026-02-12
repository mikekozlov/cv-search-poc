from __future__ import annotations

import datetime
import html

import streamlit as st

ScoreLine = tuple[str, str | None]


def inject_candidate_result_styles() -> None:
    st.markdown(
        """
<style>
:root {
  --cv-ink: var(--tt-text);
  --cv-muted: var(--tt-muted);
  --cv-card: var(--tt-card-bg);
  --cv-card-border: var(--tt-card-border);
  --cv-accent: var(--tt-accent);
  --cv-accent-warm: #f1a64f;
  --cv-chip-bg: var(--tt-chip-bg);
  --cv-chip-ink: var(--tt-text);
  --cv-shadow: rgba(36, 54, 90, 0.08);
  --cv-summary-bg: #f8faff;
  --cv-justify-bg: #f7f9ff;
  --cv-justify-border: #dfe6f4;
  --cv-success: #2f7d5d;
  --cv-success-soft: #e7f6ef;
  --cv-danger: #c0392b;
  --cv-danger-soft: #fdecea;
}

.cv-summary-card {
  background: var(--cv-summary-bg);
  border: 1px solid var(--cv-card-border);
  border-radius: 16px;
  padding: 14px 16px;
  box-shadow: 0 10px 22px var(--cv-shadow);
  margin-bottom: 12px;
}

.cv-exp-card {
  background: var(--cv-card);
  border: 1px solid var(--cv-card-border);
  border-radius: 18px;
  padding: 16px;
  box-shadow: 0 12px 26px var(--cv-shadow);
  margin-bottom: 14px;
}

.cv-exp-title {
  font-size: 1.05rem;
  font-weight: 600;
  color: var(--cv-ink);
  margin-bottom: 6px;
}

.cv-exp-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}

.cv-chip {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 0.78rem;
  font-weight: 500;
  background: var(--cv-chip-bg);
  color: var(--cv-chip-ink);
  border: 1px solid var(--tt-chip-border);
}

.cv-chip--warm {
  background: #fff1e3;
  color: var(--cv-accent-warm);
  border-color: rgba(241, 166, 79, 0.3);
}

.cv-exp-project {
  font-size: 0.92rem;
  color: var(--cv-muted);
  margin-bottom: 10px;
}

.cv-exp-list {
  margin: 0;
  padding-left: 18px;
  color: var(--cv-ink);
}

.cv-exp-list li {
  margin-bottom: 6px;
}

.cv-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 6px;
}

.tt-justify-card {
  background: var(--tt-card-bg);
  border: 1px solid var(--cv-justify-border);
  border-radius: 18px;
  padding: 16px 18px;
  box-shadow: 0 12px 24px var(--cv-shadow);
  margin: 12px 0 16px;
  max-width: 720px;
  width: 100%;
  margin-left: 0;
  margin-right: auto;
}

.tt-justify-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.tt-justify-title {
  font-size: 1rem;
  font-weight: 600;
  color: var(--cv-ink);
}

.tt-justify-subtitle {
  font-size: 0.78rem;
  color: var(--cv-muted);
  margin-top: 2px;
}

.tt-justify-score {
  text-align: right;
  border-radius: 12px;
  padding: 6px 12px;
  border: 1px solid transparent;
  min-width: 110px;
}

.tt-justify-score--good {
  background: var(--cv-success-soft);
  border-color: rgba(47, 125, 93, 0.35);
  color: var(--cv-success);
}

.tt-justify-score--bad {
  background: var(--cv-danger-soft);
  border-color: rgba(192, 57, 43, 0.35);
  color: var(--cv-danger);
}

.tt-justify-score--neutral {
  background: var(--cv-justify-bg);
  border-color: var(--cv-justify-border);
  color: var(--cv-muted);
}

.tt-justify-score-label {
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.tt-justify-score-value {
  font-size: 1.15rem;
  font-weight: 600;
}

.tt-justify-summary {
  margin-top: 12px;
  padding: 10px 12px;
  border-radius: 12px;
  background: var(--tt-accent-soft);
  border: 1px solid #d6e3ff;
  font-weight: 600;
  color: var(--cv-ink);
}

.tt-justify-columns {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 12px;
}

.tt-justify-section {
  background: var(--cv-justify-bg);
  border: 1px solid var(--cv-justify-border);
  border-radius: 12px;
  padding: 10px 12px;
}

.tt-justify-section-title {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--cv-ink);
  margin-bottom: 6px;
}

.tt-justify-list {
  margin: 0;
  padding-left: 18px;
  color: var(--cv-ink);
  font-size: 0.9rem;
}

.tt-justify-list li {
  margin-bottom: 6px;
}

.tt-justify-empty {
  font-size: 0.85rem;
  color: var(--cv-muted);
}

@media (max-width: 700px) {
  .tt-justify-card {
    max-width: 100%;
  }

  .tt-justify-columns {
    grid-template-columns: 1fr;
  }
}

div[data-testid="stMetric"] {
  padding: 10px 12px;
  border-radius: 12px;
  box-shadow: 0 8px 18px var(--cv-shadow);
}

div[data-testid="stMetric"] label {
  font-size: 0.78rem;
}

div[data-testid="stMetric"] [data-testid="stMetricValue"] {
  font-size: 1.2rem;
  line-height: 1.2;
}

button[aria-label^="Like"],
button[title^="Like"],
button[data-testid="baseButton-secondary"][aria-label^="Like"] {
  background: #2f7d5d !important;
  color: #ffffff !important;
  border: 1px solid #2f7d5d !important;
  border-radius: 999px !important;
  padding: 8px 18px !important;
  font-weight: 600 !important;
  line-height: 1 !important;
  box-shadow: 0 8px 18px rgba(47, 125, 93, 0.25) !important;
}

button[aria-label^="Like"]:hover,
button[title^="Like"]:hover,
button[data-testid="baseButton-secondary"][aria-label^="Like"]:hover {
  background: #276a4f !important;
  border-color: #276a4f !important;
}

button[aria-label^="Dislike"],
button[title^="Dislike"],
button[data-testid="baseButton-secondary"][aria-label^="Dislike"] {
  background: #c0392b !important;
  color: #ffffff !important;
  border: 1px solid #c0392b !important;
  border-radius: 999px !important;
  padding: 8px 18px !important;
  font-weight: 600 !important;
  line-height: 1 !important;
  box-shadow: 0 8px 18px rgba(192, 57, 43, 0.25) !important;
}

button[aria-label^="Dislike"]:hover,
button[title^="Dislike"]:hover,
button[data-testid="baseButton-secondary"][aria-label^="Dislike"]:hover {
  background: #a93226 !important;
  border-color: #a93226 !important;
}
</style>
        """,
        unsafe_allow_html=True,
    )


def parse_experience_text(experience_text: str) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    if not experience_text:
        return entries

    blocks = [block for block in experience_text.split(" \n") if block.strip()]
    if len(blocks) == 1:
        blocks = _split_domain_blocks(blocks[0])
    for block in blocks:
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue

        entry = {
            "title": "",
            "domains": [],
            "tech": [],
            "project": "",
            "responsibilities": [],
            "extra": [],
        }

        def is_labeled_line(line: str) -> bool:
            lower = line.lower()
            return lower.startswith(("domains:", "tech:", "project:", "responsibilities:"))

        def handle_segment(segment: str) -> None:
            lower = segment.lower()
            if lower.startswith("domains:"):
                raw = segment.split(":", 1)[-1]
                entry["domains"] = _split_csv(raw)
            elif lower.startswith("tech:"):
                raw = segment.split(":", 1)[-1]
                entry["tech"] = _split_csv(raw)
            elif lower.startswith("project:"):
                entry["project"] = segment.split(":", 1)[-1].strip()
            elif lower.startswith("responsibilities:"):
                raw = segment.split(":", 1)[-1]
                entry["responsibilities"] = _split_semicolon(raw)
            else:
                entry["extra"].append(segment.strip())

        for line in lines:
            if not entry["title"] and not is_labeled_line(line):
                entry["title"] = line.strip()
                continue
            segments = [seg.strip() for seg in line.split(" | ") if seg.strip()]
            for segment in segments:
                handle_segment(segment)

        if not entry["title"]:
            entry["title"] = "Experience"
        entries.append(entry)

    return entries


def render_summary_card(summary_text: str) -> None:
    summary = (summary_text or "").strip()
    if not summary:
        st.caption("No summary available.")
        return
    safe_summary = html.escape(summary)
    st.markdown(
        f'<div class="cv-summary-card">{safe_summary}</div>',
        unsafe_allow_html=True,
    )


def render_experience_cards(experience_text: str) -> None:
    entries = parse_experience_text(experience_text or "")
    if not entries:
        st.caption("No experience entries available.")
        return

    for entry in entries:
        title = html.escape(str(entry.get("title") or "Experience"))
        domains = entry.get("domains") or []
        tech = entry.get("tech") or []
        project = html.escape(str(entry.get("project") or ""))
        responsibilities = entry.get("responsibilities") or []
        extra = entry.get("extra") or []

        chips = []
        for domain in domains:
            chips.append(f'<span class="cv-chip">{html.escape(domain)}</span>')
        for tag in tech:
            chips.append(f'<span class="cv-chip cv-chip--warm">{html.escape(tag)}</span>')
        chips_html = " ".join(chips)

        bullet_items = responsibilities or extra
        bullet_html = ""
        if bullet_items:
            items = "".join(f"<li>{html.escape(str(item))}</li>" for item in bullet_items)
            bullet_html = f'<ul class="cv-exp-list">{items}</ul>'
        else:
            bullet_html = '<div class="cv-exp-project">No responsibilities listed.</div>'

        project_html = f'<div class="cv-exp-project">{project}</div>' if project else ""

        st.markdown(
            f"""
<div class="cv-exp-card">
  <div class="cv-exp-title">{title}</div>
  <div class="cv-exp-meta">{chips_html}</div>
  {project_html}
  {bullet_html}
</div>
            """,
            unsafe_allow_html=True,
        )


def render_tag_chips(tags_text: str, max_items: int = 28) -> None:
    tags = [t.strip() for t in (tags_text or "").split() if t.strip()]
    if not tags:
        st.caption("No tags available.")
        return

    visible = tags[:max_items]
    hidden = tags[max_items:]
    chips = "".join(f'<span class="cv-chip">{html.escape(tag)}</span>' for tag in visible)
    more_html = ""
    if hidden:
        more_html = f'<span class="cv-chip">+{len(hidden)} more</span>'
    st.markdown(
        f'<div class="cv-tags">{chips}{more_html}</div>',
        unsafe_allow_html=True,
    )


def render_justification_block(justification: dict[str, object]) -> None:
    if not isinstance(justification, dict):
        st.caption("No justification available.")
        return

    summary_text = _safe_str(justification.get("match_summary")) or "No summary provided."
    strengths = _coerce_str_list(justification.get("strength_analysis"))
    gaps = _coerce_str_list(justification.get("gap_analysis"))

    score_value = _safe_float(justification.get("overall_match_score"))
    score_label = "n/a"
    score_state = "neutral"
    if score_value is not None:
        score_pct = score_value * 100
        score_label = f"{score_pct:.0f}%"
        score_state = "good" if score_pct >= 60 else "bad"

    summary_html = html.escape(summary_text)
    strengths_html = _render_justification_list_html(strengths, "No strengths highlighted.")
    gaps_html = _render_justification_list_html(gaps, "No gaps highlighted.")

    st.markdown(
        f"""
<div class="tt-justify-card">
  <div class="tt-justify-header">
    <div>
      <div class="tt-justify-title">Justification</div>
      <div class="tt-justify-subtitle">LLM fit summary and key signals</div>
    </div>
    <div class="tt-justify-score tt-justify-score--{score_state}">
      <div class="tt-justify-score-label">LLM match</div>
      <div class="tt-justify-score-value">{score_label}</div>
    </div>
  </div>
  <div class="tt-justify-summary">{summary_html}</div>
  <div class="tt-justify-columns">
    <div class="tt-justify-section">
      <div class="tt-justify-section-title">Strengths</div>
      {strengths_html}
    </div>
    <div class="tt-justify-section">
      <div class="tt-justify-section-title">Gaps</div>
      {gaps_html}
    </div>
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )


def render_score_breakdown(result: dict[str, object]) -> None:
    score = _safe_float(_get_nested(result, "score", "value"))
    order = _safe_int(_get_nested(result, "score", "order"))
    lexical = _get_nested(result, "score_components", "lexical") or {}
    semantic = _get_nested(result, "score_components", "semantic") or {}
    hybrid = _get_nested(result, "score_components", "hybrid") or {}
    mode = _safe_str(_get_nested(result, "score_components", "mode")) or "hybrid"
    weights = _get_nested(result, "score_components", "weights") or {}
    semantic_evidence = result.get("semantic_evidence") or {}
    recency = result.get("recency") or {}

    lex_raw = _safe_float(_get_nested(lexical, "raw"))
    lex_must_idf = _safe_float(_get_nested(lexical, "must_idf_sum"))
    lex_nice_idf = _safe_float(_get_nested(lexical, "nice_idf_sum"))
    lex_must_total = _safe_float(_get_nested(lexical, "must_idf_total"))
    lex_nice_total = _safe_float(_get_nested(lexical, "nice_idf_total"))
    lex_must_cov = _safe_float(_get_nested(lexical, "must_idf_cov"))
    lex_nice_cov = _safe_float(_get_nested(lexical, "nice_idf_cov"))
    lex_coverage = _safe_float(_get_nested(lexical, "coverage"))
    lex_coverage_den = _safe_float(_get_nested(lexical, "coverage_denominator"))
    lex_must_hits = _safe_int(_get_nested(lexical, "must_hit_count"))
    lex_nice_hits = _safe_int(_get_nested(lexical, "nice_hit_count"))
    lex_must_count = _safe_int(_get_nested(lexical, "must_count"))
    lex_nice_count = _safe_int(_get_nested(lexical, "nice_count"))
    lex_domain_hit = bool(_get_nested(lexical, "domain_hit")) if lexical else False
    lex_domain_bonus = _safe_float(_get_nested(lexical, "domain_bonus"))
    lex_fts_rank = _safe_float(_get_nested(lexical, "fts_rank"))
    sem_score = _safe_float(_get_nested(semantic, "score"))
    w_lex = _safe_float(_get_nested(weights, "w_lex"))
    w_sem = _safe_float(_get_nested(weights, "w_sem"))
    last_updated = recency.get("last_updated") if isinstance(recency, dict) else None

    must_map = _coerce_bool_map(result.get("must_have"))
    nice_map = _coerce_bool_map(result.get("nice_to_have"))

    st.markdown("##### Score breakdown")
    metric_cols = st.columns(4)
    metric_cols[0].metric("Final score", _format_metric(score, 3))
    metric_cols[1].metric("Lexical raw", _format_metric(lex_raw, 2))
    metric_cols[2].metric("Semantic score", _format_metric(sem_score, 2))
    metric_cols[3].metric("Last updated", _format_last_updated(last_updated))

    with st.expander("Score calculations"):
        score_meta_lines = _score_meta_lines(
            score=score,
            lex_raw=lex_raw,
            sem_score=sem_score,
            last_updated=last_updated,
            order=order,
            mode=mode,
            w_lex=w_lex,
            w_sem=w_sem,
        )
        _render_explained_lines(score_meta_lines, "No score metadata available.")

        calc_cols = st.columns(3)
        with calc_cols[0]:
            st.markdown("**Final score**")
            final_lines = _hybrid_breakdown_lines(
                mode=mode,
                hybrid=hybrid,
                final_score=score,
                lex_raw=lex_raw,
                sem_score=sem_score,
                w_lex=w_lex,
                w_sem=w_sem,
            )
            _render_explained_lines(final_lines, "No final score details available.")

        with calc_cols[1]:
            st.markdown("**Lexical raw**")
            lex_lines = _lexical_breakdown_lines(lexical)
            _render_explained_lines(lex_lines, "No lexical score details available.")

        with calc_cols[2]:
            st.markdown("**Semantic score**")
            sem_lines = _semantic_breakdown_lines(semantic, sem_score)
            _render_explained_lines(sem_lines, "No semantic score details available.")

    with st.expander("Match evidence"):
        evidence_cols = st.columns(2)
        with evidence_cols[0]:
            _render_match_summary("Must-have skills", must_map)
        with evidence_cols[1]:
            _render_match_summary("Nice-to-have skills", nice_map)

        signal_cols = st.columns(2)
        with signal_cols[0]:
            st.markdown("**Lexical signals**")
            lex_lines = _lexical_detail_lines(
                lex_coverage,
                lex_coverage_den,
                lex_must_hits,
                lex_nice_hits,
                lex_must_count,
                lex_nice_count,
                lex_must_idf,
                lex_must_total,
                lex_must_cov,
                lex_nice_idf,
                lex_nice_total,
                lex_nice_cov,
                lex_domain_hit,
                lex_domain_bonus,
                lex_fts_rank,
            )
            _render_explained_lines(lex_lines, "No lexical signal details available.")
        with signal_cols[1]:
            st.markdown("**Semantic evidence**")
            reason_label = _semantic_reason_label(semantic_evidence)
            file_id = _safe_str(_get_nested(semantic_evidence, "file_id"))
            if reason_label:
                st.markdown(f"- Signal: {reason_label}")
            if file_id:
                st.markdown(f"- File id: {file_id}")
            if not reason_label and not file_id:
                st.caption("No semantic evidence available.")


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _split_semicolon(value: str) -> list[str]:
    return [item.strip() for item in value.split(" ; ") if item.strip()]


def _split_domain_blocks(text: str) -> list[str]:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return []

    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        lower = line.strip().lower()
        starts_new = lower.startswith("domains:") or lower.startswith("tech:")
        if starts_new and current:
            blocks.append(current)
            current = []
        current.append(line)

    if current:
        blocks.append(current)

    return ["\n".join(block) for block in blocks if block]


def _coerce_str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            items.append(text)
    return items


def _render_justification_list_html(items: list[str], empty_label: str) -> str:
    if not items:
        return f'<div class="tt-justify-empty">{html.escape(empty_label)}</div>'
    list_items = "".join(f"<li>{html.escape(item)}</li>" for item in items)
    return f'<ul class="tt-justify-list">{list_items}</ul>'


def _get_nested(data: object, *keys: str) -> object | None:
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _safe_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _format_metric(value: float | None, precision: int) -> str:
    if value is None:
        return "n/a"
    return f"{value:.{precision}f}"


def format_timestamp(value: object, empty_label: str = "n/a", utc: bool = False) -> str:
    if value is None:
        return empty_label
    if isinstance(value, datetime.datetime):
        parsed = value
        if utc and parsed.tzinfo is not None:
            parsed = parsed.astimezone(datetime.timezone.utc)
        return parsed.isoformat(timespec="seconds")
    text = str(value).strip()
    if not text:
        return empty_label
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.datetime.fromisoformat(normalized)
    except ValueError:
        trimmed = text.split(".", 1)[0]
        return trimmed or text
    if utc and parsed.tzinfo is not None:
        parsed = parsed.astimezone(datetime.timezone.utc)
    return parsed.isoformat(timespec="seconds")


def _format_last_updated(value: object) -> str:
    return format_timestamp(value, empty_label="n/a")


def _coerce_bool_map(value: object) -> dict[str, bool]:
    if not isinstance(value, dict):
        return {}
    return {str(k): bool(v) for k, v in value.items()}


def _match_stats(match_map: dict[str, bool]) -> tuple[int, int, float | None]:
    total = len(match_map)
    hits = sum(1 for v in match_map.values() if v)
    ratio = hits / total if total else None
    return hits, total, ratio


def _render_match_summary(title: str, match_map: dict[str, bool]) -> None:
    st.markdown(f"**{title}**")
    if not match_map:
        st.caption("No tags specified.")
        return
    matched = [k for k in sorted(match_map.keys()) if match_map.get(k)]
    missing = [k for k in sorted(match_map.keys()) if not match_map.get(k)]
    matched_label = ", ".join(matched) if matched else "none"
    missing_label = ", ".join(missing) if missing else "none"
    st.markdown(f"- Matched: {matched_label}")
    st.markdown(f"- Missing: {missing_label}")


def _render_explained_lines(lines: list[ScoreLine], empty_label: str) -> None:
    if not lines:
        st.caption(empty_label)
        return
    for line, detail in lines:
        st.markdown(f"- {line}")
        if detail:
            st.caption(detail)


def _score_meta_lines(
    *,
    score: float | None,
    lex_raw: float | None,
    sem_score: float | None,
    last_updated: object,
    order: int | None,
    mode: str | None,
    w_lex: float | None,
    w_sem: float | None,
) -> list[ScoreLine]:
    lines: list[ScoreLine] = []
    if score is not None:
        lines.append(
            (
                f"Final score: {score:.3f}",
                "Weighted sum of normalized lexical and semantic scores "
                "(in lexical or semantic modes the final score equals that signal).",
            )
        )
    if lex_raw is not None:
        lines.append(
            (
                f"Lexical raw: {lex_raw:.2f}",
                "Sum of weighted lexical terms (coverage, IDF coverage, domain hit, and FTS rank) "
                "before any hybrid normalization.",
            )
        )
    if sem_score is not None:
        lines.append(
            (
                f"Semantic score: {sem_score:.3f}",
                "Vector similarity score from pgvector, clamped to the 0 to 1 range.",
            )
        )
    formatted_last = _format_last_updated(last_updated)
    if formatted_last != "n/a":
        lines.append(
            (
                f"Last updated: {formatted_last}",
                "Timestamp stored on the candidate profile during ingestion; used as a tie-breaker.",
            )
        )
    if order is not None:
        lines.append(
            (
                f"Rank order: {order}",
                "Position after sorting by final score; ties break by last updated then candidate id.",
            )
        )
    if w_lex is not None or w_sem is not None:
        parts = []
        if w_lex is not None:
            parts.append(f"lexical {w_lex:g}")
        if w_sem is not None:
            parts.append(f"semantic {w_sem:g}")
        lines.append(
            (
                f"Hybrid weights: {', '.join(parts)}",
                "Weights from settings (search_w_lex, search_w_sem) that scale lexical and semantic contributions.",
            )
        )
    if mode:
        lines.append(
            (
                f"Scoring mode: {mode}",
                "Mode selects which signals contribute to the final score (hybrid, lexical, or semantic).",
            )
        )
    return lines


def _lexical_detail_lines(
    coverage: float | None,
    coverage_denominator: float | None,
    must_hit_count: int | None,
    nice_hit_count: int | None,
    must_count: int | None,
    nice_count: int | None,
    must_idf_sum: float | None,
    must_idf_total: float | None,
    must_idf_cov: float | None,
    nice_idf_sum: float | None,
    nice_idf_total: float | None,
    nice_idf_cov: float | None,
    domain_hit: bool,
    domain_bonus: float | None,
    fts_rank: float | None,
) -> list[ScoreLine]:
    lines: list[ScoreLine] = []
    if must_hit_count is not None and must_count is not None:
        denom = coverage_denominator or float(max(1, must_count))
        if coverage is not None:
            lines.append(
                (
                    f"Must-have coverage: {must_hit_count}/{int(denom)} = {coverage:.2f}",
                    f"{must_hit_count} must-have tags matched out of {int(denom)} required; "
                    f"{coverage:.2f} is the coverage ratio.",
                )
            )
        else:
            lines.append(
                (
                    f"Must-have hits: {must_hit_count}/{int(denom)}",
                    f"{must_hit_count} must-have tags matched out of {int(denom)} required.",
                )
            )
    if nice_hit_count is not None and nice_count is not None:
        lines.append(
            (
                f"Nice-to-have hits: {nice_hit_count}/{nice_count}",
                f"{nice_hit_count} nice-to-have tags matched out of {nice_count} specified.",
            )
        )
    if must_idf_sum is not None:
        if must_idf_total is not None and must_idf_total > 0 and must_idf_cov is not None:
            lines.append(
                (
                    f"Must-have IDF: {must_idf_sum:.2f}/{must_idf_total:.2f} = {must_idf_cov:.2f}",
                    "IDF is inverse document frequency. The numerator is the sum of IDF weights for matched "
                    "must-have tags; the denominator is the sum for all must-have tags.",
                )
            )
        else:
            lines.append(
                (
                    f"Must-have IDF sum: {must_idf_sum:.2f}",
                    "Sum of IDF weights for matched must-have tags.",
                )
            )
    if nice_idf_sum is not None:
        if nice_idf_total is not None and nice_idf_total > 0 and nice_idf_cov is not None:
            lines.append(
                (
                    f"Nice-to-have IDF: {nice_idf_sum:.2f}/{nice_idf_total:.2f} = {nice_idf_cov:.2f}",
                    "IDF coverage for nice-to-have tags (matched IDF sum divided by total possible IDF sum).",
                )
            )
        else:
            lines.append(
                (
                    f"Nice-to-have IDF sum: {nice_idf_sum:.2f}",
                    "Sum of IDF weights for matched nice-to-have tags.",
                )
            )
    if domain_bonus is not None:
        if domain_bonus > 0:
            lines.append(
                (
                    f"Domain bonus applied (+{domain_bonus:.2f})",
                    "Fixed bonus added when any candidate domain tag matches the seat domains.",
                )
            )
        else:
            lines.append(
                (
                    f"Domain bonus: {domain_bonus:.2f}",
                    "Domain bonus is 0.00 when no seat domain tags match the candidate.",
                )
            )
    if fts_rank is not None:
        lines.append(
            (
                f"FTS rank: {fts_rank:.2f}",
                "Full-text search rank from Postgres (ts_rank_cd) using the seat text query.",
            )
        )
    return lines


def _lexical_breakdown_lines(lexical: dict[str, object]) -> list[ScoreLine]:
    if not isinstance(lexical, dict):
        return []
    lines: list[ScoreLine] = []
    coverage = _safe_float(lexical.get("coverage"))
    coverage_denominator = _safe_float(lexical.get("coverage_denominator"))
    must_hit_count = _safe_int(lexical.get("must_hit_count"))
    must_count = _safe_int(lexical.get("must_count"))
    nice_hit_count = _safe_int(lexical.get("nice_hit_count"))
    nice_count = _safe_int(lexical.get("nice_count"))
    must_idf_sum = _safe_float(lexical.get("must_idf_sum"))
    must_idf_total = _safe_float(lexical.get("must_idf_total"))
    must_idf_cov = _safe_float(lexical.get("must_idf_cov"))
    nice_idf_sum = _safe_float(lexical.get("nice_idf_sum"))
    nice_idf_total = _safe_float(lexical.get("nice_idf_total"))
    nice_idf_cov = _safe_float(lexical.get("nice_idf_cov"))
    domain_hit = bool(lexical.get("domain_hit"))
    domain_bonus = _safe_float(lexical.get("domain_bonus"))
    fts_rank = _safe_float(lexical.get("fts_rank"))
    lex_raw = _safe_float(lexical.get("raw"))

    weights = lexical.get("weights") if isinstance(lexical.get("weights"), dict) else {}
    terms = lexical.get("terms") if isinstance(lexical.get("terms"), dict) else {}
    w_cov = _safe_float(weights.get("coverage")) if weights else None
    w_must = _safe_float(weights.get("must_idf")) if weights else None
    w_nice = _safe_float(weights.get("nice_idf")) if weights else None
    w_dom = _safe_float(weights.get("domain_bonus")) if weights else None
    w_fts = _safe_float(weights.get("fts_rank")) if weights else None
    t_cov = _safe_float(terms.get("coverage")) if terms else None
    t_must = _safe_float(terms.get("must_idf")) if terms else None
    t_nice = _safe_float(terms.get("nice_idf")) if terms else None
    t_dom = _safe_float(terms.get("domain_bonus")) if terms else None
    t_fts = _safe_float(terms.get("fts_rank")) if terms else None

    if must_hit_count is not None and must_count is not None:
        denom = coverage_denominator or float(max(1, must_count))
        if coverage is not None:
            line = f"Coverage: {must_hit_count}/{int(denom)} = {coverage:.2f}"
            if w_cov is not None and t_cov is not None:
                line += f" (x {w_cov:g} = {t_cov:.2f})"
            if w_cov is not None:
                explain = (
                    f"{must_hit_count} must-have tags matched out of {int(denom)} required; "
                    f"{coverage:.2f} is the ratio, and {w_cov:g} is the coverage weight."
                )
            else:
                explain = (
                    f"{must_hit_count} must-have tags matched out of {int(denom)} required; "
                    f"{coverage:.2f} is the ratio."
                )
            lines.append((line, explain))

    if must_idf_sum is not None and must_idf_total is not None and must_idf_total > 0:
        cov_val = must_idf_cov if must_idf_cov is not None else must_idf_sum / must_idf_total
        line = f"Must IDF coverage: {must_idf_sum:.2f}/{must_idf_total:.2f} = {cov_val:.2f}"
        if w_must is not None and t_must is not None:
            line += f" (x {w_must:g} = {t_must:.2f})"
        lines.append(
            (
                line,
                "IDF is inverse document frequency. The numerator is the sum of IDF weights for matched "
                "must-have tags; the denominator is the total IDF sum for all must-have tags.",
            )
        )

    if nice_idf_sum is not None and nice_idf_total is not None and nice_idf_total > 0:
        cov_val = nice_idf_cov if nice_idf_cov is not None else nice_idf_sum / nice_idf_total
        line = f"Nice IDF coverage: {nice_idf_sum:.2f}/{nice_idf_total:.2f} = {cov_val:.2f}"
        if w_nice is not None and t_nice is not None:
            line += f" (x {w_nice:g} = {t_nice:.2f})"
        lines.append(
            (
                line,
                "IDF coverage for nice-to-have tags (matched IDF sum divided by total possible IDF sum).",
            )
        )

    if domain_bonus is not None:
        domain_indicator = 1.0 if domain_hit else 0.0
        if w_dom is not None and t_dom is not None:
            line = (
                f"Domain hit: {'yes' if domain_hit else 'no'} -> "
                f"{domain_indicator:.0f} x {w_dom:g} = {t_dom:.2f}"
            )
            explain = (
                "Domain indicator is 1 when any seat domain tag matches the candidate; "
                "the fixed domain weight contributes this amount."
            )
        else:
            line = f"Domain bonus: {domain_bonus:+.2f}"
            explain = "Fixed bonus added when any seat domain tag matches the candidate."
        lines.append((line, explain))

    if fts_rank is not None:
        line = f"FTS rank: {fts_rank:.2f}"
        if w_fts is not None and t_fts is not None:
            line += f" (x {w_fts:g} = {t_fts:.2f})"
        lines.append(
            (
                line,
                "Full-text search rank from Postgres (ts_rank_cd) using the seat text query; "
                "the weight scales the contribution.",
            )
        )

    if lex_raw is not None and all(
        term is not None for term in (t_cov, t_must, t_nice, t_dom, t_fts)
    ):
        line = (
            f"Lexical raw = {t_cov:.2f} + {t_must:.2f} + {t_nice:.2f} + "
            f"{t_dom:.2f} + {t_fts:.2f} = {lex_raw:.2f}"
        )
        lines.append((line, "Sum of weighted lexical contributions."))
    elif lex_raw is not None:
        lines.append(
            (
                f"Lexical raw = {lex_raw:.2f}",
                "Sum of weighted lexical contributions (coverage, IDF, domain, and FTS terms).",
            )
        )

    if nice_hit_count is not None and nice_count is not None and nice_count > 0:
        lines.append(
            (
                f"Nice-to-have hits: {nice_hit_count}/{nice_count}",
                f"{nice_hit_count} nice-to-have tags matched out of {nice_count} specified.",
            )
        )

    return lines


def _hybrid_breakdown_lines(
    mode: str | None,
    hybrid: dict[str, object],
    final_score: float | None,
    lex_raw: float | None,
    sem_score: float | None,
    w_lex: float | None,
    w_sem: float | None,
) -> list[ScoreLine]:
    if not isinstance(hybrid, dict):
        hybrid = {}
    lines: list[ScoreLine] = []
    mode_label = mode or _safe_str(hybrid.get("mode"))
    if mode_label:
        lines.append(
            (
                f"Mode: {mode_label}",
                "Hybrid combines normalized lexical and semantic scores; lexical or semantic mode uses one signal.",
            )
        )

    if mode_label == "lexical":
        if lex_raw is not None:
            lines.append(
                (
                    f"Final = lexical raw = {lex_raw:.3f}",
                    "In lexical mode, the final score equals the lexical raw score.",
                )
            )
        elif final_score is not None:
            lines.append(
                (
                    f"Final = {final_score:.3f}",
                    "In lexical mode, the final score is the lexical signal.",
                )
            )
        return lines

    if mode_label == "semantic":
        if sem_score is not None:
            lines.append(
                (
                    f"Final = semantic score = {sem_score:.3f}",
                    "In semantic mode, the final score equals the semantic similarity score.",
                )
            )
        elif final_score is not None:
            lines.append(
                (
                    f"Final = {final_score:.3f}",
                    "In semantic mode, the final score is the semantic signal.",
                )
            )
        return lines

    lex_norm = _safe_float(hybrid.get("lex_norm"))
    lex_min = _safe_float(hybrid.get("lex_min"))
    lex_max = _safe_float(hybrid.get("lex_max"))
    weighted_lex = _safe_float(hybrid.get("weighted_lex"))
    weighted_sem = _safe_float(hybrid.get("weighted_sem"))
    pool_size = _safe_int(hybrid.get("pool_size"))

    if lex_norm is not None and lex_min is not None and lex_max is not None and lex_raw is not None:
        if lex_max > lex_min:
            lines.append(
                (
                    f"Lex norm = ({lex_raw:.3f} - {lex_min:.3f}) / "
                    f"({lex_max:.3f} - {lex_min:.3f}) = {lex_norm:.3f}",
                    f"{lex_raw:.3f} is this candidate's lexical raw; {lex_min:.3f} and {lex_max:.3f} "
                    "are the min and max lexical raw values in the normalization pool.",
                )
            )
        else:
            lines.append(
                (
                    f"Lex norm = 0.000 (min=max={lex_min:.3f})",
                    "All candidates share the same lexical raw score, so normalization outputs 0.000.",
                )
            )
    elif lex_norm is not None:
        lines.append(
            (
                f"Lex norm = {lex_norm:.3f}",
                "Normalized lexical score in the 0 to 1 range.",
            )
        )

    if w_lex is not None and lex_norm is not None:
        if weighted_lex is None:
            weighted_lex = w_lex * lex_norm
        lines.append(
            (
                f"Weighted lex = {w_lex:g} x {lex_norm:.3f} = {weighted_lex:.3f}",
                f"{w_lex:g} is the lexical weight; {lex_norm:.3f} is the normalized lexical score.",
            )
        )

    if w_sem is not None and sem_score is not None:
        if weighted_sem is None:
            weighted_sem = w_sem * sem_score
        lines.append(
            (
                f"Weighted sem = {w_sem:g} x {sem_score:.3f} = {weighted_sem:.3f}",
                f"{w_sem:g} is the semantic weight; {sem_score:.3f} is the semantic score.",
            )
        )

    if weighted_lex is not None and weighted_sem is not None:
        combined = weighted_lex + weighted_sem
        final_val = final_score if final_score is not None else combined
        lines.append(
            (
                f"Final = {weighted_lex:.3f} + {weighted_sem:.3f} = {final_val:.3f}",
                "Final score is the sum of the weighted lexical and semantic contributions.",
            )
        )
    elif final_score is not None:
        lines.append(
            (
                f"Final = {final_score:.3f}",
                "Final score after combining lexical and semantic contributions.",
            )
        )

    if pool_size is not None:
        lines.append(
            (
                f"Normalization pool size: {pool_size}",
                "Count of candidates used to compute lexical min/max (top lexical results plus semantic fan-in).",
            )
        )

    return lines


def _semantic_breakdown_lines(
    semantic: dict[str, object], sem_score: float | None
) -> list[ScoreLine]:
    if not isinstance(semantic, dict):
        return []
    lines: list[ScoreLine] = []
    raw_score = _safe_float(semantic.get("raw_score"))
    distance = _safe_float(semantic.get("distance"))
    clamped = _safe_float(semantic.get("clamped_score"))
    score_source = _safe_str(semantic.get("score_source"))
    source_label = _semantic_score_source_label(score_source)
    if source_label:
        lines.append(
            (
                f"Source: {source_label}",
                "Semantic scores come from pgvector similarity or are derived from distance.",
            )
        )

    if raw_score is not None:
        lines.append(
            (
                f"Raw score: {raw_score:.3f}",
                "Raw similarity score returned from pgvector (or derived from distance).",
            )
        )
    if distance is not None:
        if raw_score is None:
            derived = 1.0 - distance
            lines.append(
                (
                    f"Derived score: 1 - {distance:.3f} = {derived:.3f}",
                    "When a raw score is missing, similarity is computed as 1 - distance.",
                )
            )
        lines.append(
            (
                f"Distance: {distance:.3f}",
                "pgvector <=> distance between the query embedding and the candidate embedding.",
            )
        )
    if clamped is not None:
        lines.append(
            (
                f"Clamped score: {clamped:.3f}",
                "Raw score clamped to the 0 to 1 range before weighting.",
            )
        )
    elif sem_score is not None:
        lines.append(
            (
                f"Score: {sem_score:.3f}",
                "Semantic similarity score used in ranking.",
            )
        )
    return lines


def _semantic_reason_label(evidence: object) -> str | None:
    if not isinstance(evidence, dict):
        return None
    reason = _safe_str(evidence.get("reason"))
    if not reason:
        return None
    friendly = {
        "pgvector_similarity": "Vector similarity (pgvector)",
    }
    return friendly.get(reason, reason.replace("_", " "))


def _semantic_score_source_label(source: str | None) -> str | None:
    if not source:
        return None
    friendly = {
        "pgvector_score": "pgvector score",
        "distance": "derived from distance",
    }
    return friendly.get(source, source.replace("_", " "))


def _clamp_ratio(value: float) -> float:
    return max(0.0, min(1.0, value))

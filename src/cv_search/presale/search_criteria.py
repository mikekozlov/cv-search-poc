from __future__ import annotations

from typing import Iterable

from cv_search.core.criteria import Criteria, SeniorityEnum, TeamMember, TeamSize


def _dedupe_ordered(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        role = (value or "").strip()
        if not role or role in seen:
            continue
        seen.add(role)
        out.append(role)
    return out


def _normalize_role_key(role: str | None) -> str:
    return (role or "").strip().lower().replace(" ", "_").replace("-", "_")


def _normalize_seniority(value: SeniorityEnum | str | None) -> SeniorityEnum | None:
    if value is None:
        return None
    if isinstance(value, SeniorityEnum):
        return value
    try:
        return SeniorityEnum(str(value).strip().lower())
    except ValueError:
        return None


_TECH_BUCKETS: dict[str, set[str]] = {
    "mobile": {
        "flutter",
        "react_native",
        "android",
        "ios",
        "kotlin",
        "swift",
        "xamarin",
        "dart",
    },
    "web": {
        "react",
        "angular",
        "vue",
        "svelte",
        "nextjs",
        "nuxt",
        "sveltekit",
        "javascript",
        "typescript",
        "html",
        "css",
    },
    "backend": {
        "python",
        "dotnet",
        "nodejs",
        "java",
        "go",
        "rust",
        "php",
        "ruby",
        "scala",
        "django",
        "flask",
        "fastapi",
        "spring",
        "express",
    },
    "data": {
        "postgresql",
        "mysql",
        "mssql",
        "sqlserver",
        "mongodb",
        "redis",
        "elasticsearch",
        "bigquery",
        "snowflake",
        "redshift",
        "dbt",
        "airflow",
        "spark",
        "hadoop",
        "kafka",
        "databricks",
    },
    "payments": {"stripe", "paypal", "adyen", "braintree", "square", "wise"},
    "compliance": {
        "gdpr",
        "hipaa",
        "pci",
        "sox",
        "soc2",
        "iso27001",
        "data_privacy",
        "compliance",
        "privacy",
        "security",
    },
    "devops": {
        "docker",
        "kubernetes",
        "terraform",
        "ansible",
        "jenkins",
        "github_actions",
        "gitlab_ci",
        "aws",
        "azure",
        "gcp",
        "helm",
        "prometheus",
        "grafana",
    },
    "ai": {
        "openai",
        "chatgpt",
        "gpt",
        "llm",
        "pytorch",
        "tensorflow",
        "huggingface",
        "vertex_ai",
        "azure_ml",
        "mlops",
    },
    "notifications": {
        "firebase",
        "twilio",
        "sendgrid",
        "sns",
        "ses",
        "push",
        "email",
        "sms",
        "fcm",
    },
}

_ROLE_BUCKET_MAP: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "mobile_engineer": (("mobile",), ("web", "notifications")),
    "frontend_engineer": (("web",), ("mobile", "notifications")),
    "backend_engineer": (
        ("backend",),
        ("data", "payments", "compliance", "devops", "ai", "notifications"),
    ),
    "fullstack_engineer": (
        ("web", "backend"),
        ("data", "payments", "devops", "ai", "notifications"),
    ),
    "data_engineer": (("data",), ("backend", "devops", "ai")),
    "data_scientist": (("ai", "data"), ("backend",)),
    "ml_engineer": (("ai",), ("data", "backend", "devops")),
    "devops_engineer": (("devops",), ("backend", "data")),
    "cloud_engineer": (("devops",), ("backend", "data")),
    "qa_engineer": (("web", "backend"), ("devops",)),
    "data_privacy_expert": (("compliance",), ()),
    "security_engineer": (("compliance", "devops"), ()),
    "solution_architect": (
        ("backend",),
        ("web", "mobile", "data", "devops", "payments", "ai", "compliance"),
    ),
    "project_manager": (
        (),
        ("web", "backend", "mobile", "data", "devops", "ai", "payments", "compliance"),
    ),
    "product_manager": (
        (),
        ("web", "backend", "mobile", "data", "devops", "ai", "payments", "compliance"),
    ),
    "designer": (("web", "mobile"), ()),
}


def _bucketize_tech_stack(tech_stack: Iterable[str]) -> dict[str, list[str]]:
    buckets = {name: [] for name in _TECH_BUCKETS}
    buckets["other"] = []
    for raw in _dedupe_ordered(tech_stack):
        tag = (raw or "").strip().lower()
        if not tag:
            continue
        matched = False
        for name, tagset in _TECH_BUCKETS.items():
            if tag in tagset:
                buckets[name].append(tag)
                matched = True
        if not matched:
            buckets["other"].append(tag)
    return buckets


def _derive_role_tags(
    role: str,
    buckets: dict[str, list[str]],
    tech_stack: Iterable[str],
) -> tuple[list[str], list[str]]:
    role_key = _normalize_role_key(role)
    rule = _ROLE_BUCKET_MAP.get(role_key)
    must: list[str] = []
    nice: list[str] = []
    if rule:
        must_buckets, nice_buckets = rule
        for bucket in must_buckets:
            must.extend(buckets.get(bucket, []))
        for bucket in nice_buckets:
            nice.extend(buckets.get(bucket, []))
    else:
        nice = list(_dedupe_ordered(tech_stack))

    must = _dedupe_ordered(must)
    if not must and not nice:
        nice = list(_dedupe_ordered(tech_stack))
    nice = _dedupe_ordered([t for t in nice if t not in set(must)])
    return must, nice


def build_presale_search_criteria(
    criteria: Criteria,
    *,
    include_extended: bool = True,
    seniority: SeniorityEnum | str | None = SeniorityEnum.senior,
) -> Criteria:
    """Convert presale plan role arrays into a multi-seat Criteria for SearchProcessor.search_for_project."""

    roles = _dedupe_ordered(
        (criteria.minimum_team or []) + ((criteria.extended_team or []) if include_extended else [])
    )
    normalized_seniority = _normalize_seniority(seniority)
    domains = list(criteria.domain or [])
    tech_stack = list(criteria.tech_stack or [])
    buckets = _bucketize_tech_stack(tech_stack)
    existing_members = {
        _normalize_role_key(m.role): m
        for m in (criteria.team_size.members if criteria.team_size else [])
    }

    members = [
        TeamMember(
            role=role,
            seniority=normalized_seniority,
            domains=list(domains),
            tech_tags=[],
            nice_to_have=[],
            rationale=None,
        )
        for role in roles
    ]

    for member in members:
        derived_must, derived_nice = _derive_role_tags(member.role, buckets, tech_stack)
        existing = existing_members.get(_normalize_role_key(member.role))
        existing_must = existing.tech_tags if existing else []
        existing_nice = existing.nice_to_have if existing else []
        merged_must = _dedupe_ordered(list(existing_must or []) + derived_must)
        merged_nice = _dedupe_ordered(list(existing_nice or []) + derived_nice)
        if merged_must:
            merged_nice = [t for t in merged_nice if t not in set(merged_must)]
        member.tech_tags = merged_must
        member.nice_to_have = merged_nice

    team_size = TeamSize(total=len(members), members=members)
    expert_roles = _dedupe_ordered((criteria.expert_roles or []) + roles)

    # Normalize empty project_type to None
    project_type = criteria.project_type
    if project_type is not None and not project_type.strip():
        project_type = None

    return Criteria(
        domain=list(criteria.domain or []),
        tech_stack=tech_stack,
        expert_roles=expert_roles,
        project_type=project_type,
        team_size=team_size,
        minimum_team=list(criteria.minimum_team or []),
        extended_team=list(criteria.extended_team or []),
        presale_rationale=criteria.presale_rationale,
    )

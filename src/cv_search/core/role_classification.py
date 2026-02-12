"""Role classification for Core vs SME (Subject Matter Expert) roles.

Core roles are commonly available and searched in the candidate database.
SME roles are specialists that are listed as recommendations but not searched.
"""

from __future__ import annotations

from typing import Set

# Core roles: commonly available, will be searched
CORE_ROLES: Set[str] = {
    # Leadership & Management
    "product_manager",
    "project_manager",
    "scrum_master",
    "tech_lead",
    "team_lead",
    "delivery_manager",
    "engineering_manager",
    "release_manager",
    # Design
    "ui_ux_designer",
    "product_designer",
    # Analysis
    "business_analyst",
    # Engineering - Frontend/Backend/Full
    "frontend_engineer",
    "backend_engineer",
    "fullstack_engineer",
    # Engineering - Mobile
    "mobile_engineer",
    # Engineering - Infrastructure
    "devops_engineer",
    "platform_engineer",
    "site_reliability_engineer",
    "infrastructure_engineer",
    "cloud_architect",
    # Engineering - Quality
    "qa_engineer",
    "qa_automation_engineer",
    # Engineering - Data
    "data_engineer",
    "data_scientist",
    "bi_analyst",
    "analytics_engineer",
    "dba",
    # Engineering - AI/ML
    "ml_engineer",
    "ai_developer",
    "llm_engineer",
    # Engineering - Security
    "security_engineer",
    "devsecops_engineer",
    # Engineering - Specialized
    "embedded_engineer",
    "game_developer",
    # Architecture
    "solution_architect",
    # Support & Integration
    "support_engineer",
    "technical_support_engineer",
    "integration_specialist",
    "technical_writer",
}


def classify_role(role: str) -> str:
    """Classify a role as 'core' or 'sme'.

    Args:
        role: The role name (canonical key)

    Returns:
        'core' if the role is commonly available, 'sme' otherwise
    """
    return "core" if role.lower() in CORE_ROLES else "sme"


def is_core_role(role: str) -> bool:
    """Check if a role is a core role.

    Args:
        role: The role name (canonical key)

    Returns:
        True if core role, False if SME
    """
    return role.lower() in CORE_ROLES

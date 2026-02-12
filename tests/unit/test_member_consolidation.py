"""Unit tests for member consolidation logic."""

from cv_search.core.criteria import (
    TeamMember,
    SeniorityEnum,
    consolidate_members,
    consolidate_seat_dicts,
)


class TestConsolidateMembers:
    """Tests for consolidate_members() function."""

    def test_single_member_unchanged(self):
        """Single member should be returned unchanged."""
        members = [
            TeamMember(
                role="backend_engineer",
                seniority=SeniorityEnum.senior,
                tech_tags=["python"],
            )
        ]
        result = consolidate_members(members)
        assert len(result) == 1
        assert result[0].role == "backend_engineer"
        assert result[0].tech_tags == ["python"]

    def test_duplicate_roles_consolidated(self):
        """Multiple members with same role should be consolidated to one."""
        members = [
            TeamMember(role="backend_engineer", tech_tags=["python"]),
            TeamMember(role="backend_engineer", tech_tags=["java"]),
        ]
        result = consolidate_members(members)
        assert len(result) == 1
        assert result[0].role == "backend_engineer"
        # First occurrence's tech_tags are kept
        assert result[0].tech_tags == ["python"]

    def test_merges_nice_to_have(self):
        """nice_to_have from duplicates should be merged."""
        members = [
            TeamMember(role="backend_engineer", nice_to_have=["fastapi"]),
            TeamMember(role="backend_engineer", nice_to_have=["django", "flask"]),
        ]
        result = consolidate_members(members)
        assert len(result) == 1
        assert set(result[0].nice_to_have) == {"fastapi", "django", "flask"}

    def test_merges_domains(self):
        """domains from duplicates should be merged."""
        members = [
            TeamMember(role="backend_engineer", domains=["fintech"]),
            TeamMember(role="backend_engineer", domains=["healthcare"]),
        ]
        result = consolidate_members(members)
        assert len(result) == 1
        assert set(result[0].domains) == {"fintech", "healthcare"}

    def test_normalizes_role_casing(self):
        """Role names with different casing should be treated as same."""
        members = [
            TeamMember(role="Backend_Engineer"),
            TeamMember(role="backend-engineer"),
            TeamMember(role="backend engineer"),
        ]
        result = consolidate_members(members)
        assert len(result) == 1

    def test_preserves_distinct_roles(self):
        """Different roles should remain separate."""
        members = [
            TeamMember(role="backend_engineer"),
            TeamMember(role="frontend_engineer"),
            TeamMember(role="backend_engineer"),
        ]
        result = consolidate_members(members)
        assert len(result) == 2
        roles = {m.role.lower().replace(" ", "_") for m in result}
        assert roles == {"backend_engineer", "frontend_engineer"}

    def test_keeps_first_occurrence_attributes(self):
        """Should keep seniority/tech_tags from first occurrence."""
        members = [
            TeamMember(
                role="backend_engineer",
                seniority=SeniorityEnum.senior,
                tech_tags=["python"],
            ),
            TeamMember(
                role="backend_engineer",
                seniority=SeniorityEnum.middle,
                tech_tags=["java"],
            ),
        ]
        result = consolidate_members(members)
        assert len(result) == 1
        assert result[0].seniority == SeniorityEnum.senior
        assert result[0].tech_tags == ["python"]


class TestConsolidateSeatDicts:
    """Tests for consolidate_seat_dicts() function."""

    def test_single_seat_unchanged(self):
        """Single seat dict should be returned unchanged."""
        seats = [{"role": "backend_engineer", "tech_tags": ["python"]}]
        result = consolidate_seat_dicts(seats)
        assert len(result) == 1
        assert result[0]["role"] == "backend_engineer"

    def test_duplicate_roles_consolidated(self):
        """Multiple seat dicts with same role should be consolidated."""
        seats = [
            {"role": "backend_engineer", "tech_tags": ["python"]},
            {"role": "backend_engineer", "tech_tags": ["java"]},
        ]
        result = consolidate_seat_dicts(seats)
        assert len(result) == 1

    def test_merges_nice_to_have_dicts(self):
        """nice_to_have from duplicate dicts should be merged."""
        seats = [
            {"role": "backend_engineer", "nice_to_have": ["fastapi"]},
            {"role": "backend_engineer", "nice_to_have": ["django"]},
        ]
        result = consolidate_seat_dicts(seats)
        assert len(result) == 1
        assert set(result[0]["nice_to_have"]) == {"fastapi", "django"}

    def test_merges_domains_dicts(self):
        """domains from duplicate dicts should be merged."""
        seats = [
            {"role": "backend_engineer", "domains": ["fintech"]},
            {"role": "backend_engineer", "domains": ["healthcare"]},
        ]
        result = consolidate_seat_dicts(seats)
        assert len(result) == 1
        assert set(result[0]["domains"]) == {"fintech", "healthcare"}

    def test_preserves_distinct_roles_dicts(self):
        """Different roles should remain separate."""
        seats = [
            {"role": "backend_engineer"},
            {"role": "frontend_engineer"},
            {"role": "backend_engineer"},
        ]
        result = consolidate_seat_dicts(seats)
        assert len(result) == 2

    def test_does_not_mutate_original(self):
        """Original seat dicts should not be mutated."""
        original = {"role": "backend_engineer", "domains": ["fintech"]}
        seats = [original, {"role": "backend_engineer", "domains": ["healthcare"]}]
        result = consolidate_seat_dicts(seats)
        # Original should still have only "fintech"
        assert original["domains"] == ["fintech"]
        # Result should have both
        assert set(result[0]["domains"]) == {"fintech", "healthcare"}

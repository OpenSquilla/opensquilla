"""Compatibility exports for Community skill search operations."""

from __future__ import annotations

from opensquilla.skills.hub.operations import (
    SkillRouterFactory,
    SkillSearchOutcome,
    SkillSearchRequest,
    search_skills,
    skill_search_request,
)

__all__ = [
    "SkillRouterFactory",
    "SkillSearchOutcome",
    "SkillSearchRequest",
    "search_skills",
    "skill_search_request",
]

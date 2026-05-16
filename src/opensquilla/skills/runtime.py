"""Process-wide skill runtime services."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from opensquilla.skills.loader import SkillLoader

_skill_loader: SkillLoader | None = None


def configure_skill_loader(loader: SkillLoader | None) -> None:
    global _skill_loader
    _skill_loader = loader


def reset_skill_runtime() -> None:
    configure_skill_loader(None)


def current_skill_loader() -> SkillLoader | None:
    return _skill_loader


def skill_loader_available() -> bool:
    return _skill_loader is not None


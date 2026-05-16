"""Operation helpers for Community skill management."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from opensquilla.skills.hub.installer import InstallResult, SkillInstaller


@dataclass(frozen=True)
class SkillInstallRequest:
    """Validated ``skills.install`` operation input."""

    identifier: Any
    source_id: Any
    force: Any


@dataclass(frozen=True)
class SkillUpdateRequest:
    """Validated ``skills.update`` operation input."""

    name: Any | None = None


@dataclass(frozen=True)
class SkillUninstallRequest:
    """Validated ``skills.uninstall`` operation input."""

    name: Any


@dataclass(frozen=True)
class SkillUpdateOutcome:
    """Result of updating managed Community skills."""

    results: list[InstallResult]
    unavailable_message: str = ""


def skill_install_request(params: Mapping[str, Any] | None) -> SkillInstallRequest:
    """Build a ``skills.install`` operation request from RPC params."""

    if not isinstance(params, Mapping) or "identifier" not in params:
        raise ValueError("params.identifier is required")

    return SkillInstallRequest(
        identifier=params["identifier"],
        source_id=params.get("source", "clawhub"),
        force=params.get("force", False),
    )


def skills_update_request(params: Mapping[str, Any] | None) -> SkillUpdateRequest:
    """Build a ``skills.update`` operation request from RPC params."""

    if params is None:
        return SkillUpdateRequest()
    return SkillUpdateRequest(name=params.get("name"))


def skill_uninstall_request(params: Mapping[str, Any] | None) -> SkillUninstallRequest:
    """Build a ``skills.uninstall`` operation request from RPC params."""

    if not isinstance(params, Mapping) or "name" not in params:
        raise ValueError("params.name is required")

    return SkillUninstallRequest(name=params["name"])


async def install_skill(
    installer: SkillInstaller,
    request: SkillInstallRequest,
) -> InstallResult:
    """Install a Community skill from a validated operation request."""

    return await installer.install(
        request.identifier,
        request.source_id,
        force=request.force,
    )


async def update_skills(
    installer: SkillInstaller,
    request: SkillUpdateRequest,
) -> SkillUpdateOutcome:
    """Update managed Community skills from a validated operation request."""

    try:
        return SkillUpdateOutcome(results=await installer.update(request.name))
    except OSError as exc:
        return SkillUpdateOutcome(
            results=[],
            unavailable_message=f"Skill update unavailable: {exc}",
        )


async def uninstall_skill(
    installer: SkillInstaller,
    request: SkillUninstallRequest,
) -> InstallResult:
    """Uninstall a managed Community skill from a validated operation request."""

    return await installer.uninstall(request.name)

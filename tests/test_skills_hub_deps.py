from __future__ import annotations

from types import SimpleNamespace

import pytest

from opensquilla.skills.hub import deps
from opensquilla.skills.hub.deps import DepResult, install_skill_dependency
from opensquilla.skills.types import SkillInstallSpec, SkillPlatformMeta


@pytest.mark.asyncio
async def test_install_skill_dependency_selects_spec_and_reports_remaining_gaps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected_spec = SkillInstallSpec(id="brew", kind="brew", os=[])
    ignored_spec = SkillInstallSpec(id="uv", kind="uv", os=[])
    skill = SimpleNamespace(
        metadata=SkillPlatformMeta(install=[ignored_spec, selected_spec])
    )
    installed_specs: list[SkillInstallSpec] = []
    validated: list[tuple[SkillInstallSpec, str]] = []

    async def fake_install_deps(specs: list[SkillInstallSpec]) -> list[DepResult]:
        installed_specs.extend(specs)
        return [DepResult(kind="brew", identifier="brew", success=True, message="installed")]

    monkeypatch.setattr(deps, "install_deps", fake_install_deps)
    monkeypatch.setattr(
        deps,
        "validate_skill_install_supported",
        lambda spec, install_id: validated.append((spec, install_id)),
    )
    monkeypatch.setattr(
        deps,
        "skill_missing_requirements",
        lambda actual_skill: {"bins": ["node"], "env": []},
    )

    outcome = await install_skill_dependency(skill, name="planner", install_id="brew")

    assert installed_specs == [selected_spec]
    assert validated == [(selected_spec, "brew")]
    assert outcome.result.success is True
    assert outcome.result.kind == "brew"
    assert outcome.missing_still == {"bins": ["node"], "env": []}


@pytest.mark.asyncio
async def test_install_skill_dependency_raises_for_unknown_install_id() -> None:
    skill = SimpleNamespace(metadata=SkillPlatformMeta(install=[]))

    with pytest.raises(KeyError, match="Install spec not found: brew"):
        await install_skill_dependency(skill, name="planner", install_id="brew")

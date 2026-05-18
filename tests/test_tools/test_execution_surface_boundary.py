from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from opensquilla.engine.types import ToolCall
from opensquilla.tools.execution_surface import build_tool_execution_surface
from opensquilla.tools.registry import ToolRegistry
from opensquilla.tools.types import CallerKind, InteractionMode, ToolContext, ToolSpec

REPO_ROOT = Path(__file__).resolve().parents[2]
ENGINE_RUNTIME = REPO_ROOT / "src" / "opensquilla" / "engine" / "runtime.py"


async def _handler() -> str:
    return "ok"


class _Skill:
    def __init__(self, name: str, *, disable_model_invocation: bool = False) -> None:
        self.name = name
        self.disable_model_invocation = disable_model_invocation


class _SkillLoader:
    def __init__(self, *skills: _Skill) -> None:
        self._skills = list(skills)

    def load_all(self) -> list[_Skill]:
        return list(self._skills)


def _spec(name: str, *, exposed_by_default: bool = True) -> ToolSpec:
    return ToolSpec(
        name=name,
        description=name,
        parameters={},
        exposed_by_default=exposed_by_default,
    )


def _register(registry: ToolRegistry, *names: str) -> None:
    for name in names:
        registry.register(_spec(name), _handler)


def _top_level_method_body(class_name: str, method_name: str) -> list[ast.stmt]:
    tree = ast.parse(ENGINE_RUNTIME.read_text(encoding="utf-8"), filename=str(ENGINE_RUNTIME))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for child in node.body:
                if isinstance(child, ast.FunctionDef) and child.name == method_name:
                    return list(child.body)
    raise AssertionError(f"{class_name}.{method_name} not found")


def _imported_modules(nodes: list[ast.stmt]) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(ast.Module(body=nodes, type_ignores=[])):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_turn_runner_build_tools_delegates_execution_surface_to_tools_boundary() -> None:
    build_tools_body = _top_level_method_body("TurnRunner", "_build_tools")
    imported = _imported_modules(build_tools_body)

    assert "opensquilla.tools.execution_surface" in imported
    assert "opensquilla.tools.dispatch" not in imported
    assert "opensquilla.tools.policy" not in imported
    assert "opensquilla.tools.registry" not in imported


@pytest.mark.asyncio
async def test_execution_surface_applies_policy_runtime_profile_and_skill_mismatch() -> None:
    registry = ToolRegistry()
    _register(registry, "allowed", "denied", "session_status")
    registry.register(_spec("hidden", exposed_by_default=False), _handler)
    metadata: dict[str, Any] = {}

    surface = build_tool_execution_surface(
        registry,
        ToolContext(
            is_owner=True,
            caller_kind=CallerKind.CLI,
            interaction_mode=InteractionMode.UNATTENDED,
            session_key="agent:main:test",
            agent_id="main",
        ),
        config=SimpleNamespace(
            tools=SimpleNamespace(
                profile="minimal",
                also_allow=["allowed"],
                deny=["denied"],
            )
        ),
        session_manager=object(),
        gateway_config=object(),
        skill_loader=_SkillLoader(
            _Skill("known_skill"),
            _Skill("disabled_skill", disable_model_invocation=True),
        ),
        metadata=metadata,
    )

    assert surface.profile == "owner_full"
    assert metadata["tool_profile"] == "owner_full"
    assert {tool.name for tool in surface.definitions} == {"allowed", "session_status"}

    denied = await surface.handler(
        ToolCall(tool_use_id="tc-denied", tool_name="denied", arguments={})
    )
    assert denied.is_error is True
    assert json.loads(denied.content)["error_class"] == "PolicyDenied"

    skill_call = await surface.handler(
        ToolCall(tool_use_id="tc-skill", tool_name="known_skill", arguments={})
    )
    assert skill_call.is_error is True
    skill_payload = json.loads(skill_call.content)
    assert skill_payload["error_class"] == "UnsupportedSurface"
    assert "skill" in skill_payload["user_message"].lower()


@pytest.mark.asyncio
async def test_execution_surface_denies_runtime_unavailable_session_tools() -> None:
    registry = ToolRegistry()
    _register(registry, "read_file", "sessions_list")

    surface = build_tool_execution_surface(
        registry,
        ToolContext(
            is_owner=True,
            caller_kind=CallerKind.CLI,
            interaction_mode=InteractionMode.UNATTENDED,
            session_key="agent:main:test",
            agent_id="main",
        ),
        config=SimpleNamespace(),
        session_manager=None,
        gateway_config=object(),
    )

    assert {tool.name for tool in surface.definitions} == {"read_file"}

    result = await surface.handler(
        ToolCall(tool_use_id="tc-sessions", tool_name="sessions_list", arguments={})
    )
    assert result.is_error is True
    assert json.loads(result.content)["error_class"] == "PolicyDenied"

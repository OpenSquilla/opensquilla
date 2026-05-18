from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

from opensquilla.tools.policy_config import (
    ToolPolicy,
    expand_selectors,
    policy_from_config,
    profile_allowlist,
    sender_policy,
)

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "src/opensquilla/tools/policy.py"
POLICY_CONFIG = ROOT / "src/opensquilla/tools/policy_config.py"


def _imports_from(path: Path) -> set[tuple[str, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                imports.add((node.module, alias.name))
    return imports


def _top_level_classes(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {node.name for node in tree.body if isinstance(node, ast.ClassDef)}


def _top_level_functions(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _top_level_assignments(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def test_policy_module_delegates_config_and_selector_policy_to_boundary() -> None:
    imports = _imports_from(POLICY)

    assert ("opensquilla.tools", "policy_config") in imports
    assert "ToolPolicy" not in _top_level_classes(POLICY)
    assert {"ToolPolicy"} <= _top_level_assignments(POLICY)
    assert "_TOOL_GROUPS" not in _top_level_assignments(POLICY)
    assert "_TOOL_PROFILES" not in _top_level_assignments(POLICY)
    assert "_expand_selectors" not in _top_level_functions(POLICY)
    assert "_policy_from_config" not in _top_level_functions(POLICY)

    config_classes = _top_level_classes(POLICY_CONFIG)
    config_functions = _top_level_functions(POLICY_CONFIG)
    config_assignments = _top_level_assignments(POLICY_CONFIG)
    assert "ToolPolicy" in config_classes
    assert "_TOOL_GROUPS" in config_assignments
    assert "_TOOL_PROFILES" in config_assignments
    assert "expand_selectors" in config_functions
    assert "policy_from_config" in config_functions


def test_policy_config_expands_groups_patterns_and_profiles() -> None:
    available = frozenset(
        {
            "web_search",
            "web_fetch",
            "http_request",
            "read_file",
            "write_file",
            "session_status",
            "sessions_send",
            "message",
        }
    )

    assert expand_selectors(frozenset({"group:web", "read_*", "missing"}), available) == {
        "web_search",
        "web_fetch",
        "http_request",
        "read_file",
    }
    assert profile_allowlist("minimal", available) == {"session_status"}
    assert profile_allowlist("full", available) is None


def test_policy_config_parses_gateway_and_sender_policy_shapes() -> None:
    config = SimpleNamespace(
        tools=SimpleNamespace(profile="coding", deny=["exec_*"], also_allow=["http_request"]),
        toolsBySender={
            "id:alice": {"allow": ["message"], "deny": ["read_file"]},
            "*": {"alsoAllow": ["sessions_send"]},
        },
    )

    policy = policy_from_config(config)

    assert policy == ToolPolicy(
        profile="coding",
        allow=frozenset(),
        deny=frozenset({"exec_*"}),
        also_allow=frozenset({"http_request"}),
        by_sender={
            "id:alice": ToolPolicy(
                allow=frozenset({"message"}),
                deny=frozenset({"read_file"}),
            ),
            "*": ToolPolicy(also_allow=frozenset({"sessions_send"})),
        },
    )
    assert sender_policy(policy, "alice") == ToolPolicy(
        allow=frozenset({"message"}),
        deny=frozenset({"read_file"}),
    )
    assert sender_policy(policy, "bob") == ToolPolicy(
        also_allow=frozenset({"sessions_send"})
    )

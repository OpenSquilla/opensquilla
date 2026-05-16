from __future__ import annotations

import ast
from pathlib import Path

from opensquilla.skills import runtime as skill_runtime
from opensquilla.tools.builtin import skill_tools

ROOT = Path(__file__).resolve().parents[1]
SKILL_TOOLS = ROOT / "src/opensquilla/tools/builtin/skill_tools.py"
BOOT = ROOT / "src/opensquilla/gateway/boot.py"


class _Loader:
    workspace_dir = None

    def load_all(self) -> list[object]:
        return []

    def get_by_name(self, name: str) -> object | None:
        return None

    def invalidate_cache(self) -> None:
        return None


def _top_level_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
    return names


def _imports_from(path: Path) -> set[tuple[str, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                imports.add((node.module, alias.name))
    return imports


def test_skill_tool_does_not_own_loader_runtime_state() -> None:
    assert "_loader" not in _top_level_names(SKILL_TOOLS)


def test_skill_tool_uses_skills_runtime_boundary() -> None:
    imports = _imports_from(SKILL_TOOLS)

    assert ("opensquilla.skills.runtime", "configure_skill_loader") in imports
    assert ("opensquilla.skills.runtime", "current_skill_loader") in imports


def test_boot_documents_skills_runtime_side_effect() -> None:
    source = BOOT.read_text(encoding="utf-8")

    assert "skills.runtime (configure_skill_loader via create_skill_tools)" in source


def test_create_skill_tools_sets_shared_skill_runtime() -> None:
    loader = _Loader()
    skill_runtime.reset_skill_runtime()

    skill_tools.create_skill_tools(loader)  # type: ignore[arg-type]

    assert skill_runtime.current_skill_loader() is loader
    assert skill_runtime.skill_loader_available() is True
    skill_runtime.reset_skill_runtime()


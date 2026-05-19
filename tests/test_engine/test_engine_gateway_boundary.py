"""Architecture guards for engine/gateway decoupling."""

from __future__ import annotations

import ast
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[2] / "src" / "opensquilla" / "engine"


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_engine_does_not_import_gateway() -> None:
    offenders = {
        path.relative_to(ENGINE_ROOT): sorted(
            module
            for module in _imported_modules(path)
            if module == "opensquilla.gateway" or module.startswith("opensquilla.gateway.")
        )
        for path in ENGINE_ROOT.rglob("*.py")
    }
    offenders = {path: modules for path, modules in offenders.items() if modules}

    assert offenders == {}


def test_engine_sources_do_not_reference_gateway_package() -> None:
    offenders = [
        path.relative_to(ENGINE_ROOT)
        for path in ENGINE_ROOT.rglob("*.py")
        if "opensquilla.gateway" in path.read_text(encoding="utf-8")
    ]

    assert offenders == []

"""Focused CLI provider/model workflow boundary tests."""

from __future__ import annotations

import ast
from pathlib import Path


def _function_node(tree: ast.Module, name: str) -> ast.FunctionDef:
    return next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def test_provider_status_query_owns_gateway_request_params() -> None:
    from opensquilla.cli import providers_gateway_queries

    assert providers_gateway_queries.provider_status_request_params(
        None,
        probe_models=False,
    ) == {"probeModels": False}
    assert providers_gateway_queries.provider_status_request_params(
        "openrouter",
        probe_models=True,
    ) == {"probeModels": True, "provider": "openrouter"}

    tree = ast.parse(
        Path(providers_gateway_queries.__file__).read_text(encoding="utf-8")
    )
    load_provider_status = _function_node(tree, "load_provider_status")
    assert {
        node.func.id
        for node in ast.walk(load_provider_status)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    } >= {"provider_status_request_params"}
    assert not any(
        isinstance(node, ast.Dict)
        and any(
            isinstance(key, ast.Constant) and key.value in {"provider", "probeModels"}
            for key in node.keys
        )
        for node in ast.walk(load_provider_status)
    )


def test_models_query_owns_gateway_request_params() -> None:
    from opensquilla.cli import models_gateway_queries

    assert models_gateway_queries.model_list_request_params(
        provider=None,
        capabilities=None,
    ) == {"provider": None, "capabilities": None}
    assert models_gateway_queries.model_list_request_params(
        provider="openrouter",
        capabilities=["chat"],
    ) == {"provider": "openrouter", "capabilities": ["chat"]}

    tree = ast.parse(Path(models_gateway_queries.__file__).read_text(encoding="utf-8"))
    list_models_from_gateway = _function_node(tree, "list_models_from_gateway")
    assert {
        node.func.id
        for node in ast.walk(list_models_from_gateway)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    } >= {"model_list_request_params"}

"""Boundary tests for the TaskRuntime scheduler extraction."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from opensquilla.gateway.task_runtime import TaskRuntime
from opensquilla.gateway.task_runtime_scheduler import TaskRuntimeScheduler

_ROOT = Path(__file__).resolve().parents[2]
_TASK_RUNTIME_PATH = _ROOT / "src" / "opensquilla" / "gateway" / "task_runtime.py"


def _task_runtime_class() -> ast.ClassDef:
    tree = ast.parse(_TASK_RUNTIME_PATH.read_text())
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "TaskRuntime":
            return node
    raise AssertionError("TaskRuntime class not found")


def _method(class_node: ast.ClassDef, name: str) -> ast.AsyncFunctionDef | ast.FunctionDef:
    for item in class_node.body:
        if isinstance(item, ast.AsyncFunctionDef | ast.FunctionDef) and item.name == name:
            return item
    raise AssertionError(f"TaskRuntime.{name} not found")


def _without_docstring(
    body: list[ast.stmt],
) -> list[ast.stmt]:
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        return body[1:]
    return body


def _assert_thin_scheduler_delegator(
    class_node: ast.ClassDef,
    task_runtime_method: str,
    scheduler_method: str,
) -> None:
    method = _method(class_node, task_runtime_method)
    body = _without_docstring(method.body)
    assert len(body) <= 2, f"{task_runtime_method} should be a short scheduler delegator"
    source = ast.unparse(ast.Module(body=body, type_ignores=[]))
    assert "self._scheduler" in source
    assert f".{scheduler_method}(" in source


def test_scheduler_boundary_exposes_slot_methods() -> None:
    scheduler = TaskRuntimeScheduler(max_concurrency=4, subagent_reserved_slots=1)

    assert callable(scheduler.wait_for_subagent_slot)
    assert callable(scheduler.acquire_fair_slot)
    assert callable(scheduler.release_slot)


def test_task_runtime_slot_methods_are_thin_scheduler_delegators() -> None:
    class_node = _task_runtime_class()

    _assert_thin_scheduler_delegator(
        class_node,
        "_wait_for_subagent_slot",
        "wait_for_subagent_slot",
    )
    _assert_thin_scheduler_delegator(
        class_node,
        "_acquire_fair_slot",
        "acquire_fair_slot",
    )
    _assert_thin_scheduler_delegator(class_node, "_release_slot", "release_slot")


def test_task_runtime_keeps_session_locks_outside_scheduler() -> None:
    class_node = _task_runtime_class()
    init_source = ast.unparse(_method(class_node, "__init__"))
    terminal_source = ast.unparse(_method(class_node, "_mark_terminal"))
    scheduler_init = inspect.getsource(TaskRuntimeScheduler.__init__)

    assert "self._session_locks" in init_source
    assert "_session_locks.pop" not in terminal_source
    assert hasattr(TaskRuntime, "_get_session_lock_for_turn")
    assert "_session_locks" not in scheduler_init

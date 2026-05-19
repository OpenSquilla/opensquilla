"""Presentation helpers for CLI skill install and uninstall mutations."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

import typer

from opensquilla.cli.output import print_json
from opensquilla.cli.ui import console


def skill_result_payload(result: Any) -> dict[str, Any]:
    """Return the JSON payload for a local skill mutation result."""

    payload = dict(result) if isinstance(result, dict) else asdict(result)
    scan = payload.get("scan")
    if scan is None:
        payload.pop("scan", None)
    return payload


def emit_skill_mutation_payload(
    payload: dict[str, Any],
    *,
    json_output: bool,
    success_label: str,
    fallback_name: str,
) -> None:
    """Emit a gateway-style skill mutation payload."""

    success = bool(payload.get("success", False))
    if json_output:
        print_json(payload)
        if not success:
            raise typer.Exit(1)
        return

    name = str(payload.get("name") or fallback_name)
    message = str(payload.get("message") or "")
    if success:
        path = payload.get("path")
        suffix = f" -> {path}" if path else ""
        console.print(f"[green]{success_label}:[/] {name}{suffix}")
        if message:
            console.print(message)
        return

    console.print(f"[red]Failed:[/] {message or name}")
    raise typer.Exit(1)


def emit_failed_skill_mutation(
    message: str,
    *,
    json_output: bool,
    success_label: str,
    fallback_name: str,
) -> None:
    """Emit a failed skill mutation message."""

    emit_skill_mutation_payload(
        {"success": False, "message": message},
        json_output=json_output,
        success_label=success_label,
        fallback_name=fallback_name,
    )


def emit_missing_skill_mutation_result(
    action: str,
    *,
    json_output: bool,
    success_label: str,
    fallback_name: str,
) -> None:
    """Emit the legacy message for a missing local mutation result."""

    emit_failed_skill_mutation(
        f"No skill {action} result returned",
        json_output=json_output,
        success_label=success_label,
        fallback_name=fallback_name,
    )


def emit_local_skill_install_start(
    identifier: str,
    source: str,
    *,
    json_output: bool,
) -> None:
    """Emit the non-JSON local install progress line."""

    if not json_output:
        console.print(f"Installing '{identifier}' from {source}...")


def emit_local_skill_install_result(result: Any, *, json_output: bool) -> None:
    """Emit a local skill install result."""

    if json_output:
        print_json(skill_result_payload(result))
        if not result.success:
            raise typer.Exit(1)
        return

    if result.success:
        console.print(f"[green]Installed:[/] {result.name} → {result.path}")
        if result.scan and result.scan.verdict != "safe":
            scan = result.scan
            console.print(
                f"[yellow]Security: {scan.verdict} ({len(scan.findings)} findings)[/]"
            )
    else:
        console.print(f"[red]Failed:[/] {result.message}")
        raise typer.Exit(1)


def emit_local_skill_uninstall_result(result: Any, *, json_output: bool) -> None:
    """Emit a local skill uninstall result."""

    if json_output:
        print_json(skill_result_payload(result))
        if not result.success:
            raise typer.Exit(1)
        return

    if result.success:
        console.print(f"[green]Uninstalled:[/] {result.name}")
    else:
        console.print(f"[red]Failed:[/] {result.message}")
        raise typer.Exit(1)

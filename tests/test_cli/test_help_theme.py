"""CLI help presentation tests."""

from __future__ import annotations

import re
from pathlib import Path

import click
from typer import rich_utils
from typer.testing import CliRunner

from opensquilla.cli.main import app
from opensquilla.ui import ACCENT, questionary_style

runner = CliRunner()


def test_rich_help_uses_opensquilla_accent() -> None:
    assert rich_utils.STYLE_OPTIONS_PANEL_BORDER == ACCENT
    assert rich_utils.STYLE_COMMANDS_PANEL_BORDER == ACCENT
    assert rich_utils.STYLE_OPTION == f"bold {ACCENT}"
    assert rich_utils.STYLE_COMMANDS_TABLE_FIRST_COLUMN == f"bold {ACCENT}"


def test_questionary_checkbox_selection_avoids_reverse_row_highlight() -> None:
    style = questionary_style()
    assert style is not None
    rules = dict(style.style_rules)

    for token in ("pointer", "highlighted", "selected"):
        assert "noreverse" in rules[token]
        assert "bg:" not in rules[token]


def test_onboard_help_keeps_router_option_readable() -> None:
    result = runner.invoke(app, ["onboard", "--help"], terminal_width=100)

    assert result.exit_code == 0, result.output
    output = click.unstyle(result.output)
    assert "--router" in output
    assert "--router MODE" in output
    assert "Router profile: recommended," in output
    assert "openrouter-mix, or" in output
    assert "disabled." in output
    assert "TEXT  recommended | openrouter-mix" not in output


def test_onboard_help_uses_compact_option_columns() -> None:
    result = runner.invoke(app, ["onboard", "--help"], terminal_width=100)

    assert result.exit_code == 0, result.output
    output = click.unstyle(result.output)
    assert "--provider TEXT" in output
    assert "--router MODE" in output
    assert not re.search(r"--provider\s{12,}TEXT", output)


def test_help_theme_supports_click_make_metavar_without_context(monkeypatch) -> None:
    def legacy_make_metavar(self: click.Option) -> str:
        if self.is_bool_flag:
            return "BOOLEAN"
        return self.metavar or self.type.name.upper()

    monkeypatch.setattr(click.Option, "make_metavar", legacy_make_metavar)

    result = runner.invoke(app, ["onboard", "--help"], terminal_width=100)

    assert result.exit_code == 0, result.output
    output = click.unstyle(result.output)
    assert "--provider TEXT" in output
    assert "--router MODE" in output


def test_cli_brand_surfaces_do_not_use_cyan() -> None:
    cli_files = [*Path("src/opensquilla/cli").rglob("*.py"), Path("src/opensquilla/ui.py")]
    forbidden = (
        "bold cyan",
        "[cyan]",
        "[/cyan]",
        "typer.colors.CYAN",
        'style="cyan"',
    )

    offenders: list[str] = []
    for path in cli_files:
        text = path.read_text(encoding="utf-8")
        for needle in forbidden:
            if needle in text:
                offenders.append(f"{path}:{needle}")

    assert offenders == []

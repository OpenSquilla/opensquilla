"""CLI workflows for skill search commands."""

from __future__ import annotations

from opensquilla.cli.skills_catalog_presenters import emit_skill_search_results
from opensquilla.cli.skills_search_rows import search_skill_rows


async def search_skills_for_cli(
    query: str,
    *,
    json_output: bool,
) -> None:
    """Search skills and emit the CLI result."""

    results = await search_skill_rows(query)
    emit_skill_search_results(query, results, json_output=json_output)

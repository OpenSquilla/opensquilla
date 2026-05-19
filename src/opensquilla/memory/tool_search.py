"""Memory search tool behavior that belongs to the memory boundary."""

from __future__ import annotations

import re
from typing import Any, Final

from opensquilla.memory.types import MemorySearchOpts, MemorySearchResult, SearchIntent

MEMORY_SEARCH_DEFAULT_RESULTS: Final[int] = 10
MEMORY_SEARCH_MAX_RESULTS: Final[int] = 20
_MEMORY_SEARCH_EVIDENCE_CHARS: Final[int] = 900
_MEMORY_SEARCH_STOP_WORDS: Final[frozenset[str]] = frozenset(
    {
        "about",
        "after",
        "and",
        "are",
        "did",
        "for",
        "from",
        "has",
        "have",
        "her",
        "him",
        "his",
        "how",
        "the",
        "their",
        "them",
        "was",
        "were",
        "what",
        "when",
        "where",
        "who",
        "why",
        "with",
    }
)
_YAML_FRONTMATTER_RE = re.compile(r"\A---\s*\n.*?\n---\s*(?:\n|$)", re.S)


def memory_search_limit(value: object) -> int:
    parsed = MEMORY_SEARCH_DEFAULT_RESULTS
    if isinstance(value, (int, float, str)):
        try:
            parsed = int(value)
        except (OverflowError, ValueError):
            parsed = MEMORY_SEARCH_DEFAULT_RESULTS
    return max(1, min(MEMORY_SEARCH_MAX_RESULTS, parsed))


def clean_memory_search_evidence(text: str) -> str:
    raw = text.strip()
    if not raw:
        return ""

    cleaned = _YAML_FRONTMATTER_RE.sub("", raw, count=1).lstrip()
    lines = cleaned.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    while (
        lines
        and lines[0].lstrip().startswith("#")
        and any(line.strip() and not line.lstrip().startswith("#") for line in lines[1:])
    ):
        lines.pop(0)
        while lines and not lines[0].strip():
            lines.pop(0)

    cleaned = "\n".join(lines).strip()
    return cleaned or raw


def _memory_search_query_terms(query: str) -> tuple[str, ...]:
    terms: list[str] = []
    seen: set[str] = set()
    for term in re.findall(r"[A-Za-z0-9]+", query.lower()):
        if len(term) < 3 or term in _MEMORY_SEARCH_STOP_WORDS or term in seen:
            continue
        terms.append(term)
        seen.add(term)
    return tuple(terms)


def _query_line_score(line: str, terms: tuple[str, ...]) -> int:
    lowered = line.lower()
    return sum(1 for term in terms if term in lowered)


def _truncate_line_around_query(line: str, terms: tuple[str, ...], budget: int) -> str:
    if len(line) <= budget:
        return line
    lowered = line.lower()
    positions = [lowered.find(term) for term in terms if term in lowered]
    center = min(positions) if positions else 0
    start = max(0, center - budget // 3)
    end = min(len(line), start + budget)
    start = max(0, end - budget)
    excerpt = line[start:end].strip()
    if start > 0:
        excerpt = "... " + excerpt
    if end < len(line):
        excerpt = excerpt.rstrip() + " ..."
    return excerpt


def _query_centered_evidence(cleaned: str, query: str, budget: int) -> str | None:
    terms = _memory_search_query_terms(query)
    if not terms:
        return None
    lines = cleaned.splitlines()
    scored = [(_query_line_score(line, terms), index) for index, line in enumerate(lines)]
    best_score, best_index = max(scored, default=(0, 0))
    if best_score <= 0:
        return None
    if len(lines[best_index]) >= budget:
        return _truncate_line_around_query(lines[best_index], terms, budget)

    start = best_index
    end = best_index + 1
    while True:
        current = "\n".join(lines[start:end])
        added = False
        if start > 0:
            candidate = "\n".join(lines[start - 1 : end])
            if len(candidate) <= budget:
                start -= 1
                added = True
        if end < len(lines):
            candidate = "\n".join(lines[start : end + 1])
            if len(candidate) <= budget:
                end += 1
                added = True
        if not added or "\n".join(lines[start:end]) == current:
            break

    block = "\n".join(lines[start:end]).strip()
    if start > 0:
        block = "... (earlier lines omitted)\n" + block
    if end < len(lines):
        block = block + "\n... (later lines omitted)"
    if len(block) <= budget:
        return block
    return "\n".join(lines[start:end]).strip()


def bounded_memory_search_evidence(text: str, *, query: str = "") -> str:
    cleaned = clean_memory_search_evidence(text)
    if len(cleaned) <= _MEMORY_SEARCH_EVIDENCE_CHARS:
        return cleaned
    centered = _query_centered_evidence(cleaned, query, _MEMORY_SEARCH_EVIDENCE_CHARS)
    if centered:
        return centered
    return cleaned[:_MEMORY_SEARCH_EVIDENCE_CHARS].rstrip() + "\n... (truncated)"


def _score_parts(result: MemorySearchResult) -> list[str]:
    parts = [f"score: {result.score:.3f}"]
    if result.text_score is not None:
        parts.append(f"text_score: {result.text_score:.3f}")
    return parts


def format_memory_search_results(results: list[MemorySearchResult], *, query: str) -> str:
    if not results:
        return "No results found."

    lines = []
    for i, result in enumerate(results, 1):
        citation = result.citation or f"{result.path}#L{result.start_line}-L{result.end_line}"
        evidence = bounded_memory_search_evidence(result.text or result.snippet, query=query)
        lines.append(
            f"[{i}] {result.path} "
            f"(lines {result.start_line}-{result.end_line}; "
            f"citation: {citation}; {', '.join(_score_parts(result))})\n"
            f"{evidence}"
        )
    return "\n\n".join(lines)


async def search_memory_tool(retriever: Any, query: str, max_results: int) -> str:
    opts = MemorySearchOpts(max_results=memory_search_limit(max_results))
    results = await retriever.search(query, opts, intent=SearchIntent.TOOL)
    return format_memory_search_results(results, query=query)

#!/usr/bin/env python3
"""Hook: user_prompt_submit - Auto-recall relevant memories.

Searches .serena/memories/ for content matching the user's prompt,
ranks by confidence score, and injects top results via stderr.
Exit code 0 = no guidance. Exit code 2 = stderr contains model context.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..search import SearchResult

# Stop words filtered from queries to improve search precision.
_STOP_WORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "by", "do", "for",
    "from", "has", "have", "he", "i", "in", "is", "it", "its", "me",
    "my", "no", "not", "of", "on", "or", "so", "that", "the", "they",
    "this", "to", "up", "us", "was", "we", "what", "when", "which",
    "who", "will", "with", "you", "your",
})

_MAX_RECALL_RESULTS = 3
_MIN_QUERY_TERMS = 1


def main() -> int:
    """Entry point for the user_prompt_submit hook."""
    user_input = _read_user_input()
    if not user_input:
        return 0

    query = _extract_query(user_input)
    if not query:
        return 0

    repo_root = _find_repo_root()
    if repo_root is None:
        return 0

    memories_dir = repo_root / ".serena" / "memories"
    if not memories_dir.is_dir():
        return 0

    results = _search_and_format(query, memories_dir, repo_root)
    if results:
        print(results, file=sys.stderr)
        return 2

    return 0


def _read_user_input() -> str:
    """Read the user prompt from stdin (passed by Claude Code)."""
    try:
        raw = sys.stdin.read()
    except (OSError, UnicodeDecodeError):
        return ""

    try:
        data = json.loads(raw)
        return str(data.get("query", data.get("prompt", "")))
    except (json.JSONDecodeError, TypeError, AttributeError):
        return raw.strip()


def _extract_query(user_input: str) -> str:
    """Extract search terms by filtering stop words and short tokens.

    Args:
        user_input: Raw user prompt text.

    Returns:
        Space-joined query terms, or empty string if insufficient terms.
    """
    words = user_input.lower().split()
    terms = [_strip_punctuation(w) for w in words]
    terms = [w for w in terms if w and w not in _STOP_WORDS and len(w) > 2]
    top_terms = terms[:5]

    if len(top_terms) < _MIN_QUERY_TERMS:
        return ""

    return " ".join(top_terms)


def _strip_punctuation(word: str) -> str:
    """Strip leading/trailing punctuation from a word."""
    return word.strip("?!.,;:\"'()[]{}*#@&^%$~`<>|\\/")


def _find_repo_root(start: Path | None = None) -> Path | None:
    """Walk up from start to find repo root. Delegates to shared utility."""
    from . import find_repo_root

    return find_repo_root(start)


def _search_and_format(
    query: str, memories_dir: Path, repo_root: Path
) -> str:
    """Search memories and format results for stderr injection.

    Args:
        query: Filtered search terms.
        memories_dir: Path to .serena/memories/.
        repo_root: Repository root for verification.

    Returns:
        Formatted memory context string, or empty string.
    """
    # Import here to avoid circular imports at module level
    from ..search import search_memories

    results = search_memories(
        query=query,
        memories_dir=memories_dir,
        max_results=_MAX_RECALL_RESULTS,
        repo_root=repo_root,
    )

    if not results:
        return ""

    return _format_memory_context(results)


def _format_memory_context(results: list[SearchResult]) -> str:
    """Format search results as the memory context injection block.

    Args:
        results: List of SearchResult objects.

    Returns:
        Formatted string for stderr output.
    """
    lines = [
        "<memory-context>",
        "## Relevant Memories (auto-recalled)",
        "",
    ]

    for result in results:
        lines.append(
            f"### {result.title} "
            f"(confidence: {result.confidence:.0%}, {result.citation_status})"
        )
        lines.append(result.snippet)
        relative_path = result.file_path
        try:
            from . import find_repo_root
            repo_root = find_repo_root(result.file_path)
            if repo_root is not None:
                relative_path = result.file_path.relative_to(repo_root)
        except (ValueError, ImportError):
            pass
        lines.append(f"Source: {relative_path}")
        lines.append("")

    lines.append("</memory-context>")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())

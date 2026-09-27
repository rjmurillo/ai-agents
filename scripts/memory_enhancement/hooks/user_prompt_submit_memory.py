#!/usr/bin/env python3
"""Hook: user_prompt_submit - Auto-recall relevant memories.

Searches .serena/memories/ for content matching the user's prompt,
ranks by confidence score, and injects top results into model context.

The two hosts need different events and output shapes (issue #4727):

- Claude Code, ``UserPromptSubmit``: :func:`main` prints the plain
  ``<memory-context>`` block. Claude Code adds that stdout to the model's
  context.
- GitHub Copilot CLI, ``userPromptTransformed``: :func:`main_transformed`
  prints one ``{"modifiedTransformedPrompt": ...}`` object that appends the
  block to the model-facing prompt. Copilot drops all output from
  config-file ``userPromptSubmitted`` hooks, so the Claude path is inert
  there. The event itself selects the host. The only environment check
  skips recall inside the Copilot cloud agent, which runs unattended.

Exit Codes:
    0 = always. Recall is fail-open and needs no non-zero code. Exit code 2
        on UserPromptSubmit blocks prompt processing and erases the user's
        prompt, so this hook must never return it (issue #4011).
"""

from __future__ import annotations

import json
import os
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
# The GitHub hook reference documents these as set only inside the Copilot
# cloud agent sandbox. That agent runs unattended with pre-approved tools and
# reads .serena/memories from a checked-out branch, so recall stays off there
# (ADR-068 amendment for issue #4727).
_CLOUD_AGENT_ENV_VARS = ("COPILOT_AGENT_PROMPT", "GITHUB_COPILOT_API_TOKEN")
_MIN_QUERY_TERMS = 1


def main() -> int:
    """Entry point for the Claude Code UserPromptSubmit hook."""
    results = _recall(_read_user_input())
    if results:
        print(results)

    return 0


def main_transformed() -> int:
    """Entry point for the Copilot CLI userPromptTransformed hook.

    Appends the memory block to ``transformedPrompt`` and prints one
    ``modifiedTransformedPrompt`` object. Prints nothing when recall finds
    no match, the payload lacks a usable ``prompt`` or ``transformedPrompt``,
    or the hook runs inside the Copilot cloud agent. Printing nothing leaves
    the model-facing content unchanged.
    """
    if _in_cloud_agent():
        return 0

    payload = _parse_payload(_read_stdin())
    transformed = payload.get("transformedPrompt")
    prompt = payload.get("prompt")
    if not isinstance(transformed, str) or not transformed.strip():
        return 0
    if not isinstance(prompt, str):
        return 0

    results = _recall(prompt)
    if results:
        envelope = {"modifiedTransformedPrompt": f"{transformed}\n\n{results}"}
        print(json.dumps(envelope))

    return 0


def _in_cloud_agent() -> bool:
    """Return True inside the Copilot cloud agent sandbox."""
    return any(os.environ.get(name) for name in _CLOUD_AGENT_ENV_VARS)


def _recall(user_input: str) -> str:
    """Return the memory context block for a prompt, or empty string."""
    if not user_input:
        return ""

    query = _extract_query(user_input)
    if not query:
        return ""

    repo_root = _find_repo_root()
    if repo_root is None:
        return ""

    memories_dir = repo_root / ".serena" / "memories"
    if not memories_dir.is_dir():
        return ""

    return _search_and_format(query, memories_dir, repo_root)


def _read_stdin() -> str:
    """Read the raw hook payload from stdin."""
    try:
        return sys.stdin.read()
    except (OSError, UnicodeDecodeError):
        return ""


def _parse_payload(raw: str) -> dict:
    """Parse a JSON object payload, or return an empty dict."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _read_user_input() -> str:
    """Read the user prompt from stdin (passed by Claude Code)."""
    raw = _read_stdin()
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
    """Search memories and format results as the memory context block.

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
        The ``<memory-context>`` block, written to stdout by the caller.
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

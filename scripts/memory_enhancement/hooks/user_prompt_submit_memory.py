#!/usr/bin/env python3
"""Hook: user_prompt_submit - Auto-recall relevant memories.

Searches .serena/memories/ for content matching the user's prompt,
ranks by confidence score, and injects top results via stdout.

The stdout shape depends on the host, because the two harnesses read this
event differently (issue #4727):

- Claude Code adds plain ``UserPromptSubmit`` stdout to the model context, so
  the memory block is printed bare.
- GitHub Copilot CLI discards plain stdout on this event and consumes a
  top-level ``{"additionalContext": "..."}`` envelope instead, so the block is
  wrapped when ``COPILOT_CLI`` is set and no Claude signal is. ``COPILOT_CLI``
  is an unconfirmed heuristic, not a vendor-documented signal; see
  ``_render_for_host`` for the correction and what is actually verified.

``_render_for_host`` carries the citation for the one signal that is
confirmed, the correction for the one that is not, and the reason the Claude
signal takes precedence either way.

Hook Type: UserPromptSubmit
Exit Codes:
    0 = always. Both hosts read this hook's context from stdout, so recall
        needs no non-zero code. Exit code 2 on this event blocks prompt
        processing and erases the user's prompt, so this hook must never
        return it (issue #4011).
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
        print(_render_for_host(results))

    return 0


def _render_for_host(memory_context: str) -> str:
    """Return the memory block in the stdout shape the running host reads.

    Issue #4727 probed GitHub Copilot CLI 1.0.79-6 on the production
    registration surface (``.claude/settings.json``) with a matched pair that
    differed only in output form: plain stdout was discarded, and a top-level
    ``{"additionalContext": "<sentinel>"}`` document reached the model. Claude
    Code reads plain stdout on this event, so it keeps the bare block.

    Only one of the two signals is vendor-confirmed:

    - ``CLAUDE_CODE_ENTRYPOINT`` is set by Claude Code and never by Copilot CLI.
      Measured on Copilot CLI 1.0.80: the literal string appears 0 times in the
      shipped ``app.js`` and ``copilot`` binary, in a search where
      ``COPILOT_CLI`` (12), ``additionalContext`` (24), and ``GITHUB_TOKEN``
      (27) are the positive controls.
    - ``COPILOT_CLI`` is NOT vendor-confirmed. An earlier revision of this
      docstring quoted a changelog entry ("Git hooks can detect Copilot CLI
      subprocesses via the COPILOT_CLI=1 environment variable...", citing
      ``changelog.json`` version ``0.0.421`` and
      ``github/copilot-agent-runtime#4049``). That citation was checked against
      the actual installed ``@github/copilot`` package (all published versions,
      including current) and does not exist: no such entry, no such string, no
      such PR reference, anywhere in ``changelog.json``. A byte search of the
      shipped 1.0.80 ``app.js`` finds exactly one bare ``COPILOT_CLI`` literal,
      and it is an unrelated feature-flighting enum key
      (``COPILOT_CLI="copilot_cli"``), not an environment variable read or
      write. Official GitHub docs and the community environment-variable
      reference for Copilot CLI do not list it either. The 12 "positive
      control" hits referenced above are all ``COPILOT_CLI_*``-prefixed names
      (``COPILOT_CLI_VERSION`` and similar), not the bare variable. Treat the
      ``COPILOT_CLI`` branch below as an unconfirmed heuristic, not a vendor
      contract: it costs nothing when wrong (Claude sessions never reach it,
      per the precedence order), but there is currently no verified
      environment signal that positively identifies a Copilot-CLI-spawned
      hook subprocess. See probe-evidence.md section 8b for the full
      correction and the open follow-up to get a live-session probe.

    Because the positive Copilot signal is unconfirmed, the Claude signal is
    checked first and is the only branch this code can vouch for. Claude reads
    a nested ``hookSpecificOutput`` envelope and never a top-level
    ``additionalContext`` key, so an envelope sent to Claude parses as
    structured output with no recognized field and the memory block is dropped
    with no error. That is the silent inertness of issues #4011 and #4727,
    reproduced on the other harness. Checking the Claude signal first fails
    safe: the bare block is what Claude reads, and Copilot discards it exactly
    as it did before this hook changed. Whether the ``COPILOT_CLI`` branch ever
    fires under real Copilot CLI is unverified; if it never fires, recall
    remains silently inert under Copilot exactly as issue #4727 first found.

    ``CLAUDE_PROJECT_DIR`` is not a usable discriminator in either direction.
    Copilot does not set it (same 1.0.80 search, 0 hits), so it is unset under
    Copilot rather than shared, but it is also unset in some Claude Code
    surfaces, so its absence identifies nothing.

    Args:
        memory_context: The rendered ``<memory-context>`` block.

    Returns:
        The block itself under Claude Code, or a one-line JSON envelope
        carrying it under Copilot CLI.
    """
    if os.environ.get("CLAUDE_CODE_ENTRYPOINT", "").strip():
        return memory_context
    if os.environ.get("COPILOT_CLI", "").strip():
        return json.dumps({"additionalContext": memory_context})
    return memory_context


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
    """Search memories and format results for stdout injection.

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
        Formatted string for stdout output. ``_render_for_host`` decides
        whether it is printed bare or inside an ``additionalContext``
        envelope.
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

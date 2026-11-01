"""Known shipped-YAML offenses that check_plugin_root_interpreter.py allows.

Each entry is keyed by (path relative to its plugin root, YAML key path, rule,
script tail), so one entry covers the three mirrors and survives line moves,
but a new command under another key is still reported. Rules: "form",
"dependency", "bare-path". For an entry that no longer matches anything, the
checker prints it to stderr and exits 1, so a stale entry cannot hide a later
offense. Delete the entry once the offense is fixed (issue #6506).
"""

from __future__ import annotations

import re

_PR_REVIEW_CONFIG = "skills/pr-review/pr-review-config.yaml"
_CLAUDE_CODE_MAP = (
    "scripts.claude_code predates plugin-self-containment MUST 2; the copilot map "
    "already uses the plugin-root form. Migrating it is an owner decision (Refs #6195)."
)
_GUARDED_MARKDOWN_IT = (
    "check_review_thread_resolution_shas.py imports markdown-it-py inside "
    "try/except ImportError and scans the raw body without it. Whether a guarded "
    "import meets MUST 4 is an owner decision (Refs #6195)."
)
_PR = "skills/github/scripts/pr/"
_CRITERION = "completion_criteria.command"

# scripts.claude_code entry -> the script it runs on a bare path.
_CLAUDE_CODE_ENTRIES = {
    "get_pr_context": f"{_PR}get_pr_context.py",
    "test_pr_merged": f"{_PR}test_pr_merged.py",
    "get_review_threads": f"{_PR}get_pr_review_threads.py",
    "get_unresolved_threads": f"{_PR}get_unresolved_review_threads.py",
    "cluster_threads": "skills/pr-comment-responder/scripts/cluster_threads.py",
    "wait_for_settled_zero": f"{_PR}wait_for_unresolved_zero.py",
    "get_unaddressed_comments": f"{_PR}get_unaddressed_comments.py",
    "get_pr_checks": f"{_PR}get_pr_checks.py",
    "add_thread_reply": f"{_PR}add_pr_review_thread_reply.py",
    "add_thread_reply_resolve": f"{_PR}add_pr_review_thread_reply.py",
    "resolve_thread": f"{_PR}resolve_pr_review_thread.py",
}
YAML_ALLOWANCES: dict[tuple[str, str, str, str], str] = {
    **{
        (_PR_REVIEW_CONFIG, f"scripts.claude_code.{entry}", "bare-path", script): _CLAUDE_CODE_MAP
        for entry, script in _CLAUDE_CODE_ENTRIES.items()
    },
    (
        _PR_REVIEW_CONFIG,
        _CRITERION,
        "dependency",
        f"{_PR}check_review_thread_resolution_shas.py",
    ): _GUARDED_MARKDOWN_IT,
}

_KEY_RE = re.compile(r"([A-Za-z0-9_.-]+):(?:\s|$)")
# A block scalar header closes a key line (or a `- ` item): `|`, `>`, with an
# optional chomping or indentation indicator and an optional trailing comment.
_BLOCK_HEADER_RE = re.compile(r"[|>](?:[+-]?\d?|\d[+-])[ \t]*(?:#.*)?$")


def _opens_block_scalar(content: str) -> bool:
    """Return whether ``content`` (dash already stripped) ends in a block scalar header."""
    match = _KEY_RE.match(content)
    value = content[match.end() :].strip() if match else content.strip()
    return bool(_BLOCK_HEADER_RE.fullmatch(value))


def yaml_key_paths(text: str) -> list[str]:
    """Return the dotted block-mapping key path that owns each line of ``text``.

    Stdlib only, for the block-style YAML this repository ships: a key's
    parents are the keys at smaller indentation above it, and a ``- `` list
    item adds no path segment. A comment or blank line inherits the open path.
    The body of a block scalar (``|`` or ``>``) is text, not keys: its lines
    inherit the owning key's path even when one reads like ``key:`` (issue #6506).
    """
    stack: list[tuple[int, str]] = []
    paths: list[str] = []
    block_floor: int | None = None  # body lines must be indented deeper than this
    for raw in text.splitlines():
        stripped = raw.lstrip(" ")
        if block_floor is not None:
            if not stripped or len(raw) - len(stripped) > block_floor:
                paths.append(".".join(key for _, key in stack))
                continue
            block_floor = None
        content = stripped
        floor = len(raw) - len(stripped)
        if content.startswith("- "):
            content = content[2:].lstrip(" ")
        if content and not content.startswith("#"):
            indent = len(raw) - len(content)
            while stack and stack[-1][0] >= indent:
                stack.pop()
            match = _KEY_RE.match(content)
            if match:
                stack.append((indent, match.group(1)))
                floor = indent
            if _opens_block_scalar(content):
                block_floor = floor
        paths.append(".".join(key for _, key in stack))
    return paths

#!/usr/bin/env python3
"""Allowlist of intentional generated-agent divergences.

``build/generate_agents.py --validate`` regenerates every agent file and fails
when a committed file differs. Before issue #5636 the only escape was a
``[skip-drift-check]`` commit marker that skipped the whole job on the word of
whoever wrote the commit message. This module replaces that marker with a
committed file, ``.agents/governance/drift-allowlist.json``, that names each
divergent file and states why. A reviewer sees the entry in the diff, and the
validator refuses an entry it cannot account for.

File shape (schema version 1)::

    {
      "schema_version": "1",
      "entries": [
        {"path": "src/copilot-cli/agents/example.agent.md", "reason": "why"}
      ]
    }

Rules the loader enforces. Any violation raises ``AllowlistError`` naming every
bad entry, and the caller exits 2 (configuration error, ADR-035):

- ``path`` is required, a string, repo-relative, POSIX-separated, and exact.
  Absolute paths, ``..`` segments, backslashes, and glob characters are refused
  so one entry can never cover more than one file.
- ``reason`` is required and must hold non-whitespace text with no control
  character. A newline in ``reason`` would let a crafted entry start a line
  that GitHub Actions parses as a workflow command when the validator echoes
  the reason.
- No duplicate ``path``, and no keys beyond ``path`` and ``reason``.

A missing file is an empty allowlist (no divergence is permitted). An
unreadable or malformed file is an error, never an empty allowlist: a parse
failure that fell back to "nothing allowed" would hide the fault, and one that
fell back to "everything allowed" would be a bypass.

Canonical source and reuse decision (``.claude/rules/canonical-source-mirror.md``):
the sidecar-JSON-under-``.agents/governance/`` shape mirrors
``build/model_pin_manifest.py``'s ``load_pin_manifest`` reading of
``.agents/governance/model-pin-evidence.json``, which also carries a
``schema_version`` and a fixed set of required per-entry fields.

Stricter/looser/different than canonical: ``load_pin_manifest`` degrades an
invalid manifest to "no entries" so generation still runs. This loader does
the opposite and raises, because an allowlist that degrades silently is a
bypass path, which is the defect this module exists to close.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

ALLOWLIST_RELATIVE_PATH = Path(".agents") / "governance" / "drift-allowlist.json"
SCHEMA_VERSION = "1"
_ENTRY_KEYS = frozenset({"path", "reason"})
_GLOB_CHARS = frozenset("*?[]{}")


class AllowlistError(Exception):
    """The allowlist file is unreadable or holds an invalid entry."""


@dataclass(frozen=True)
class AllowedDivergence:
    """One accepted divergence: a repo-relative file and the reason it differs."""

    path: str
    reason: str


def _has_control_char(value: str) -> bool:
    """True when ``value`` holds an ASCII control character, including newline and DEL."""
    return any(ord(char) < 32 or ord(char) == 127 for char in value)


def _path_problem(value: object) -> str | None:
    """Return why ``value`` is not an acceptable exact repo-relative path."""
    if not isinstance(value, str) or not value.strip():
        return "'path' must be a non-empty string"
    if value != value.strip() or "\\" in value:
        return "'path' must use forward slashes and no surrounding whitespace"
    if _has_control_char(value):
        return "'path' must not contain a control character"
    if any(char in _GLOB_CHARS for char in value):
        return "'path' must name one exact file, not a glob"
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts or value.endswith("/"):
        return "'path' must be a repo-relative file path with no '..' segment"
    return None


def _entry_problems(entry: object, seen: set[str]) -> list[str]:
    """Return every problem with one raw entry, and record its path in ``seen``."""
    if not isinstance(entry, dict):
        return ["entry must be an object with 'path' and 'reason'"]
    problems: list[str] = []
    extra = sorted(set(entry) - _ENTRY_KEYS)
    if extra:
        problems.append(f"unknown key(s) {extra}")
    path_problem = _path_problem(entry.get("path"))
    if path_problem:
        problems.append(path_problem)
    elif entry["path"] in seen:
        problems.append(f"duplicate path {entry['path']!r}")
    else:
        seen.add(entry["path"])
    reason = entry.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        problems.append("'reason' must be a non-empty string")
    elif _has_control_char(reason):
        problems.append("'reason' must not contain a control character")
    return problems


def parse_allowlist(document: object) -> list[AllowedDivergence]:
    """Validate a decoded allowlist document and return its entries."""
    if not isinstance(document, dict):
        raise AllowlistError("allowlist must be a JSON object")
    if document.get("schema_version") != SCHEMA_VERSION:
        raise AllowlistError(f"'schema_version' must be {SCHEMA_VERSION!r}")
    raw_entries = document.get("entries")
    if not isinstance(raw_entries, list):
        raise AllowlistError("'entries' must be a list")
    seen: set[str] = set()
    problems: list[str] = []
    for index, entry in enumerate(raw_entries):
        problems.extend(f"entries[{index}]: {p}" for p in _entry_problems(entry, seen))
    if problems:
        raise AllowlistError("; ".join(problems))
    return [AllowedDivergence(e["path"], e["reason"].strip()) for e in raw_entries]


def load_allowlist(repo_root: Path) -> list[AllowedDivergence]:
    """Read and validate the allowlist under ``repo_root``.

    Returns an empty list when the file does not exist. Raises
    ``AllowlistError`` for an unreadable, non-JSON, or invalid file.
    """
    path = repo_root / ALLOWLIST_RELATIVE_PATH
    if not path.exists():
        return []
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AllowlistError(f"cannot read {ALLOWLIST_RELATIVE_PATH.as_posix()}: {exc}") from exc
    return parse_allowlist(document)


def _relative_posix(diff: str, repo_root: Path) -> str | None:
    """Return ``diff`` as a repo-relative POSIX path, or None when outside the root."""
    try:
        return Path(diff).resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return None


def split_differences(
    differences: list[str],
    allowlist: list[AllowedDivergence],
    repo_root: Path,
) -> tuple[list[str], list[tuple[str, str]], list[str]]:
    """Partition drift into ``(blocking, allowed, unused_entries)``.

    ``allowed`` holds ``(difference, reason)`` pairs. ``unused_entries`` lists
    allowlist paths that matched no difference, so a stale entry is visible.
    """
    reasons = {entry.path: entry.reason for entry in allowlist}
    blocking: list[str] = []
    allowed: list[tuple[str, str]] = []
    matched: set[str] = set()
    for diff in differences:
        relative = _relative_posix(diff, repo_root)
        if relative is not None and relative in reasons:
            allowed.append((diff, reasons[relative]))
            matched.add(relative)
        else:
            blocking.append(diff)
    unused = sorted(set(reasons) - matched)
    return blocking, allowed, unused

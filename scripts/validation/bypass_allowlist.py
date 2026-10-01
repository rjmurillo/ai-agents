#!/usr/bin/env python3
"""Allowlist of authorized bypass toggles and advisory workflow exceptions.

Issue #5636, owner decision D17 (built on D8). Two kinds of path let a check
report success without proving its contract, and neither had an owner on
record:

- an environment toggle whose name carries ``SKIP_`` (``SKIP_AUTOFIX``,
  ``SKIP_YAMLLINT``, and the rest), set by whoever runs the command; and
- a workflow job or step with ``continue-on-error``, whose failure the job
  never reads.

``scripts/validation/check_bypass_allowlist.py`` finds every use and refuses one
this file does not list. Each entry carries a reason, an owner, and an expiry
date, so an exception is a decision someone made and must renew, not a
leftover.

File shape (schema version 1)::

    {
      "schema_version": "1",
      "entries": [
        {"kind": "toggle", "toggle": "SKIP_EXAMPLE",
         "reason": "why", "owner": "handle", "expires": "2026-12-31"},
        {"kind": "continue-on-error", "path": ".github/workflows/x.yml",
         "job": "job-id", "step": "Step name",
         "reason": "why", "owner": "handle", "expires": "2026-12-31"}
      ]
    }

``step`` is the step ``name`` (or ``id`` when the step has no name). An empty
``step`` names a job-level ``continue-on-error``.

Rules the loader enforces. Any violation raises ``AllowlistError`` naming every
bad entry, and the caller exits 2 (configuration error, ADR-035):

- ``kind`` is one of the two kinds above, and only that kind's keys appear.
- ``toggle`` matches the toggle-name pattern. ``path`` is exact, repo-relative,
  and POSIX-separated: no absolute path, ``..`` segment, backslash, or glob.
- ``reason`` and ``owner`` are non-blank and hold no control character. A
  newline in ``reason`` would let a crafted entry start a line that GitHub
  Actions parses as a workflow command when the validator echoes it.
- ``expires`` is a real ``YYYY-MM-DD`` date. The checker fails closed on an
  entry whose date has passed.
- No two entries share a key.

A missing file is an empty allowlist (nothing is authorized). An unreadable or
malformed file is an error, never an empty allowlist: a parse failure that fell
back to "nothing allowed" would hide the fault, and one that fell back to
"everything allowed" would be a bypass.

Canonical source (``.claude/rules/canonical-source-mirror.md``):
``build/drift_allowlist.py`` is the D8 loader this module follows: a sidecar JSON
under ``.agents/governance/`` with ``schema_version`` and ``entries``, a missing
file read as an empty allowlist, and an unreadable or malformed file raising
``AllowlistError``. Its docstring states those three rules. This is a summary of
them, not a quotation.

Stricter/looser/different than canonical: this loader adds ``kind``, ``owner``,
and ``expires`` (the drift loader has only ``path`` and ``reason``), and two
entry shapes. It does not import ``build.drift_allowlist``: ``build/`` is a
generator package and this gate belongs to ``scripts/validation``. The path and
control-character checks are re-implemented with the same rules.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path, PurePosixPath

ALLOWLIST_RELATIVE_PATH = Path(".agents") / "governance" / "bypass-allowlist.json"
SCHEMA_VERSION = "1"
KIND_TOGGLE = "toggle"
KIND_CONTINUE_ON_ERROR = "continue-on-error"

#: An environment toggle name: optional uppercase prefix segments, then ``SKIP_``.
#: ``AI_AGENTS_SKIP_TESTS`` and ``EVAL_SKIP_MODEL_PREFLIGHT`` match, so a prefix
#: cannot hide a toggle from the scan.
TOGGLE_NAME = r"(?:[A-Z][A-Z0-9]*_)*SKIP_[A-Z][A-Z0-9_]*"

_COMMON_KEYS = frozenset({"kind", "reason", "owner", "expires"})
_KIND_KEYS = {
    KIND_TOGGLE: _COMMON_KEYS | {"toggle"},
    KIND_CONTINUE_ON_ERROR: _COMMON_KEYS | {"path", "job", "step"},
}
_TOGGLE_RE = re.compile(f"^{TOGGLE_NAME}$")
_OWNER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_GLOB_CHARS = frozenset("*?[]{}")


class AllowlistError(Exception):
    """The allowlist file is unreadable or holds an invalid entry."""


@dataclass(frozen=True)
class AllowedToggle:
    """One authorized environment toggle."""

    toggle: str
    reason: str
    owner: str
    expires: date


@dataclass(frozen=True)
class AllowedAdvisoryStep:
    """One authorized ``continue-on-error`` job or step."""

    path: str
    job: str
    step: str
    reason: str
    owner: str
    expires: date

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.path, self.job, self.step)


@dataclass(frozen=True)
class Allowlist:
    """Every authorized exception, keyed for lookup."""

    toggles: dict[str, AllowedToggle]
    steps: dict[tuple[str, str, str], AllowedAdvisoryStep]


def _has_control_char(value: str) -> bool:
    """True when ``value`` holds an ASCII control character, including newline and DEL."""
    return any(ord(char) < 32 or ord(char) == 127 for char in value)


def _text_problem(entry: dict[str, object], field: str) -> str | None:
    value = entry.get(field)
    if not isinstance(value, str) or not value.strip():
        return f"'{field}' must be a non-empty string"
    if _has_control_char(value):
        return f"'{field}' must not contain a control character"
    return None


def _path_problem(value: object) -> str | None:
    """Return why ``value`` is not an acceptable exact repo-relative path."""
    if not isinstance(value, str) or not value.strip():
        return "'path' must be a non-empty string"
    if value != value.strip() or "\\" in value or _has_control_char(value):
        return "'path' must use forward slashes, no whitespace edge, no control character"
    if any(char in _GLOB_CHARS for char in value):
        return "'path' must name one exact file, not a glob"
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts or value.endswith("/"):
        return "'path' must be a repo-relative file path with no '..' segment"
    return None


def _expiry_problem(value: object) -> str | None:
    if not isinstance(value, str) or not _DATE_RE.match(value):
        return "'expires' must be a YYYY-MM-DD date"
    try:
        date.fromisoformat(value)
    except ValueError:
        return "'expires' must be a real calendar date"
    return None


def _owner_problem(entry: dict[str, object]) -> str | None:
    problem = _text_problem(entry, "owner")
    if problem:
        return problem
    if not _OWNER_RE.match(str(entry["owner"])):
        return "'owner' must be a handle of letters, digits, '.', '_', or '-'"
    return None


def _kind_problems(entry: dict[str, object], kind: str) -> list[str]:
    """Return the problems specific to one entry kind."""
    if kind == KIND_TOGGLE:
        toggle = entry.get("toggle")
        if not isinstance(toggle, str) or not _TOGGLE_RE.match(toggle):
            return ["'toggle' must be an uppercase name containing a SKIP_ segment"]
        return []
    problems = [_path_problem(entry.get("path")), _text_problem(entry, "job")]
    step = entry.get("step")
    if not isinstance(step, str) or _has_control_char(step):
        problems.append("'step' must be a string without control characters ('' for a job)")
    return [p for p in problems if p]


def _entry_key(entry: dict[str, object], kind: str) -> tuple[str, ...]:
    if kind == KIND_TOGGLE:
        return (KIND_TOGGLE, str(entry.get("toggle")))
    return (kind, str(entry.get("path")), str(entry.get("job")), str(entry.get("step")))


def _entry_problems(entry: object, seen: set[tuple[str, ...]]) -> list[str]:
    """Return every problem with one raw entry, and record its key in ``seen``."""
    if not isinstance(entry, dict):
        return ["entry must be an object"]
    kind = entry.get("kind")
    if kind not in _KIND_KEYS:
        return [f"'kind' must be one of {sorted(_KIND_KEYS)}"]
    problems: list[str] = []
    extra = sorted(set(entry) - _KIND_KEYS[kind])
    if extra:
        problems.append(f"unknown key(s) {extra} for kind {kind!r}")
    problems.extend(_kind_problems(entry, kind))
    common = (
        _text_problem(entry, "reason"),
        _owner_problem(entry),
        _expiry_problem(entry.get("expires")),
    )
    problems.extend(p for p in common if p)
    key = _entry_key(entry, kind)
    if key in seen:
        problems.append(f"duplicate entry {key[1:]!r}")
    seen.add(key)
    return problems


def _build(entry: dict[str, str]) -> AllowedToggle | AllowedAdvisoryStep:
    reason = entry["reason"].strip()
    expires = date.fromisoformat(entry["expires"])
    if entry["kind"] == KIND_TOGGLE:
        return AllowedToggle(entry["toggle"], reason, entry["owner"], expires)
    return AllowedAdvisoryStep(
        entry["path"], entry["job"], entry["step"], reason, entry["owner"], expires
    )


def parse_allowlist(document: object) -> Allowlist:
    """Validate a decoded allowlist document and return its entries."""
    if not isinstance(document, dict):
        raise AllowlistError("allowlist must be a JSON object")
    if document.get("schema_version") != SCHEMA_VERSION:
        raise AllowlistError(f"'schema_version' must be {SCHEMA_VERSION!r}")
    raw_entries = document.get("entries")
    if not isinstance(raw_entries, list):
        raise AllowlistError("'entries' must be a list")
    seen: set[tuple[str, ...]] = set()
    problems: list[str] = []
    for index, entry in enumerate(raw_entries):
        problems.extend(f"entries[{index}]: {p}" for p in _entry_problems(entry, seen))
    if problems:
        raise AllowlistError("; ".join(problems))
    built = [_build(entry) for entry in raw_entries]
    return Allowlist(
        toggles={e.toggle: e for e in built if isinstance(e, AllowedToggle)},
        steps={e.key: e for e in built if isinstance(e, AllowedAdvisoryStep)},
    )


def load_allowlist(repo_root: Path) -> Allowlist:
    """Read and validate the allowlist under ``repo_root``.

    Returns an empty allowlist when the file does not exist. Raises
    ``AllowlistError`` for an unreadable, non-JSON, or invalid file.
    """
    path = repo_root / ALLOWLIST_RELATIVE_PATH
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return Allowlist(toggles={}, steps={})
    except (OSError, UnicodeDecodeError) as exc:
        raise AllowlistError(f"cannot read {ALLOWLIST_RELATIVE_PATH.as_posix()}: {exc}") from exc
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AllowlistError(f"cannot parse {ALLOWLIST_RELATIVE_PATH.as_posix()}: {exc}") from exc
    return parse_allowlist(document)

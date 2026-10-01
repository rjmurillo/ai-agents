#!/usr/bin/env python3
"""The applicability table: which validators must have run for a candidate.

ADR-113 decision 3, issue #5636. Quoted from
``.project-toolkit/architecture/ADR-113-promotion-gate-evidence-and-exceptions.md``:

    "A checked-in applicability table maps candidate contents (for example,
    "contains a workflow file") to the validators that must have run. A missing
    applicable result is `UNKNOWN`, never `PASS`. [...] The applicability
    table has the same CODEOWNERS protection as the exceptions file. Gate
    coverage equals table coverage: a required check the table does not list
    is never consulted, so a drift check compares the required-checks ruleset
    with the table."

File shape, ``.agents/governance/promotion-applicability.json``, schema 1::

    {"schema_version": "1", "entries": [{
      "validator": "run_python_tests", "tier": "commit",
      "workflow": ".github/workflows/pytest.yml",
      "job": "Run Python Tests", "when": "always",
      "rationale": "why this validator gates promotion"}]}

``workflow`` is the repository path of the workflow file whose run holds the
job. The provenance check (decision 5) accepts evidence only from a run of that
workflow, so a result uploaded by any other workflow is refused.

``when`` is the string ``"always"``, the string ``"never"`` (not applicable to any
promotion, decision 9), or a non-empty list of glob patterns over
repository-relative paths of the candidate commit. A pattern matches a path
with :func:`fnmatch.fnmatchcase`, where ``*`` also crosses ``/``. That reads a
pattern wider than a shell glob does, which can only add a required validator,
never drop one. ``tier`` is ``"commit"`` or ``"build"`` (decision 4).

The loader raises ``ApplicabilityError`` for any bad entry. A missing file is
an empty table, which the gate reports as ``applicability.absent``, so a deleted
table blocks promotion instead of excusing every validator.

Mirrors ``scripts/validation/promotion_exceptions.py`` (``_read_regular_file``,
``_reject_duplicate_keys``, and ``load_exceptions``, whose contract reads
"Returns an empty tuple when the file does not exist. Raises
``ExceptionsFileError`` for an unreadable, non-JSON, or invalid file."):
the same bounded, no-symlink read, duplicate-key refusal, and per-entry error
list under an ``entries[N]:`` prefix.

Different from that module: an entry with a missing or unknown key reports only
those shape errors, then stops. ``promotion_exceptions.py`` goes on to report
field errors in the same entry. Here a field check would index a key that is not
there. The author fixes the shape, and the next run reports the field errors.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import stat
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

APPLICABILITY_RELATIVE_PATH = Path(".agents") / "governance" / "promotion-applicability.json"
SCHEMA_VERSION = "1"
MAX_FILE_BYTES = 1_048_576
TIER_COMMIT = "commit"
TIER_BUILD = "build"
ALWAYS = "always"
NEVER = "never"

_SHOWN_PATH = APPLICABILITY_RELATIVE_PATH.as_posix()
_KEYS = frozenset({"validator", "tier", "workflow", "job", "when", "rationale"})
_WORKFLOW_RE = re.compile(r"\.github/workflows/[A-Za-z0-9][A-Za-z0-9._-]*\.ya?ml")
_VALIDATOR_RE = re.compile(r"[a-z][a-z0-9_.-]*")
_TIERS = frozenset({TIER_COMMIT, TIER_BUILD})


class ApplicabilityError(Exception):
    """The applicability file is unreadable or holds an invalid entry."""


@dataclass(frozen=True, slots=True)
class Applicability:
    """One validator, the tier it binds on, and when it must have run."""

    validator: str
    tier: str
    workflow: str
    job: str
    when: tuple[str, ...]
    rationale: str

    @property
    def always(self) -> bool:
        """True when the validator applies to every candidate."""
        return self.when == (ALWAYS,)

    @property
    def never(self) -> bool:
        """True when the validator is marked not applicable to any promotion (decision 9)."""
        return self.when == (NEVER,)

    def applies_to(self, paths: Iterable[str]) -> bool:
        """Return True when this validator must have run for a candidate with ``paths``."""
        if self.never:
            return False
        if self.always:
            return True
        names = list(paths)
        return any(fnmatch.fnmatchcase(name, pattern) for pattern in self.when for name in names)


def _has_forbidden_char(value: str) -> bool:
    return any(not char.isprintable() for char in value)


def _text_problem(entry: dict[str, object], field: str) -> str | None:
    value = entry.get(field)
    if not isinstance(value, str) or not value.strip():
        return f"'{field}' must be a non-empty string"
    if _has_forbidden_char(value):
        return f"'{field}' must not contain a control character"
    return None


def _when_problem(value: object) -> str | None:
    if value in (ALWAYS, NEVER):
        return None
    if not isinstance(value, list) or not value:
        return f"'when' must be \"{ALWAYS}\", \"{NEVER}\", or a non-empty list of glob patterns"
    for pattern in value:
        if not isinstance(pattern, str) or not pattern.strip() or _has_forbidden_char(pattern):
            return "'when' patterns must be non-empty printable strings"
        if pattern.startswith(("/", "./")) or ".." in pattern.split("/"):
            return (
                "'when' patterns must be repository-relative with no leading './' or '..' segment"
            )
        if pattern.endswith("/"):
            return (
                "'when' patterns match file paths, so a trailing '/' would never match; use 'dir/*'"
            )
    return None


def _workflow_problem(value: object) -> str | None:
    if isinstance(value, str) and _WORKFLOW_RE.fullmatch(value):
        return None
    return "'workflow' must be a path such as '.github/workflows/pytest.yml'"


def _identity_problems(entry: dict[str, object]) -> list[str]:
    """Problems with the validator, tier, and workflow fields of a well-shaped entry."""
    problems: list[str] = []
    validator = entry["validator"]
    if not isinstance(validator, str) or not _VALIDATOR_RE.fullmatch(validator):
        problems.append("'validator' must be a lowercase slug such as 'run_python_tests'")
    tier = entry["tier"]
    if not isinstance(tier, str) or tier not in _TIERS:
        problems.append(f"'tier' must be one of {', '.join(sorted(_TIERS))}")
    workflow_problem = _workflow_problem(entry["workflow"])
    if workflow_problem:
        problems.append(workflow_problem)
    return problems


def _entry_problems(entry: object) -> list[str]:
    if not isinstance(entry, dict):
        return ["entry must be a JSON object"]
    problems: list[str] = []
    missing = sorted(_KEYS - set(entry))
    extra = sorted(set(entry) - _KEYS)
    if missing:
        problems.append(f"missing {', '.join(missing)}")
    if extra:
        problems.append(f"unknown key(s) {', '.join(extra)}")
    if problems:
        return problems
    problems.extend(_identity_problems(entry))
    for field in ("job", "rationale"):
        problem = _text_problem(entry, field)
        if problem:
            problems.append(problem)
    when_problem = _when_problem(entry["when"])
    if when_problem:
        problems.append(when_problem)
    return problems


def _build(entry: dict[str, object]) -> Applicability:
    when = entry["when"]
    return Applicability(
        validator=str(entry["validator"]),
        tier=str(entry["tier"]),
        workflow=str(entry["workflow"]),
        job=str(entry["job"]),
        when=(str(when),)
        if when in (ALWAYS, NEVER)
        else tuple(str(item) for item in cast("list[object]", when)),
        rationale=str(entry["rationale"]),
    )


def parse_applicability(document: object) -> tuple[Applicability, ...]:
    """Validate a decoded table and return its entries."""
    if not isinstance(document, dict):
        raise ApplicabilityError("applicability file must be a JSON object")
    if document.get("schema_version") != SCHEMA_VERSION:
        raise ApplicabilityError(f"'schema_version' must be {SCHEMA_VERSION!r}")
    raw = document.get("entries")
    if not isinstance(raw, list):
        raise ApplicabilityError("'entries' must be a list")
    problems: list[str] = []
    for index, entry in enumerate(raw):
        problems.extend(f"entries[{index}]: {p}" for p in _entry_problems(entry))
    if problems:
        raise ApplicabilityError("; ".join(problems))
    entries = tuple(_build(entry) for entry in raw)
    names = [entry.validator for entry in entries]
    if len(set(names)) != len(names):
        raise ApplicabilityError("two entries name the same validator; keep one")
    return entries


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    seen: set[str] = set()
    repeated: set[str] = set()
    for key, _ in pairs:
        (repeated if key in seen else seen).add(key)
    if repeated:
        raise ValueError(f"duplicate key(s) {', '.join(sorted(repeated))}")
    return dict(pairs)


def _read_regular_file(path: Path) -> str:
    if path.is_symlink():
        raise OSError("a symlink is not accepted")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    descriptor = os.open(path, flags)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise OSError("not a regular file")
        data = os.read(descriptor, MAX_FILE_BYTES + 1)
    finally:
        os.close(descriptor)
    if len(data) > MAX_FILE_BYTES:
        raise ApplicabilityError(f"{_SHOWN_PATH} is larger than {MAX_FILE_BYTES} bytes")
    return data.decode("utf-8")


def load_applicability(repo_root: Path) -> tuple[Applicability, ...]:
    """Read and validate the table under ``repo_root``.

    ``repo_root`` must be a checkout of the default branch (decision 5). Returns
    an empty tuple when the file does not exist. Raises ``ApplicabilityError``
    for an unreadable, non-JSON, or invalid file.
    """
    path = repo_root / APPLICABILITY_RELATIVE_PATH
    try:
        text = _read_regular_file(path)
    except FileNotFoundError:
        return ()
    except (OSError, UnicodeDecodeError) as exc:
        raise ApplicabilityError(f"cannot read {_SHOWN_PATH}: {exc}") from exc
    try:
        document = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except (ValueError, RecursionError) as exc:
        raise ApplicabilityError(f"cannot parse {_SHOWN_PATH}: {exc}") from exc
    return parse_applicability(document)


def required_validators(entries: Iterable[Applicability], paths: Iterable[str]) -> tuple[str, ...]:
    """Return the validators that must have run for a candidate with ``paths``."""
    names = list(paths)
    return tuple(sorted(entry.validator for entry in entries if entry.applies_to(names)))


def build_tier_validators(entries: Iterable[Applicability]) -> frozenset[str]:
    """Return the validators that bind on the tarball digest as well as the SHA."""
    return frozenset(entry.validator for entry in entries if entry.tier == TIER_BUILD)

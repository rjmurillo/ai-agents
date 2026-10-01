#!/usr/bin/env python3
"""Persisted validator evidence and its binding to a promotion candidate.

ADR-113 decisions 2 and 4, issue #5636. Quoted from
``.project-toolkit/architecture/ADR-113-promotion-gate-evidence-and-exceptions.md``:

    "Each job that runs a validator uploads its `CheckOutcome.to_dict()`
    output as a JSON evidence artifact." (decision 2)

    "The candidate is a commit SHA plus the SHA-256 digest of the npm
    tarball. Results computed before the build (tests, validators, analysis)
    bind to the SHA: the result's `revision` must equal the candidate SHA.
    Results about the build itself (pack size, package metadata, install
    smoke) bind to the SHA and the digest. [...] A result bound to another
    SHA or digest is rejected and counted as missing." (decision 4)

Evidence file shape: the ``CheckOutcome.to_dict()`` keys from
``scripts/validation/evidence.py`` (``validator``, ``state``, ``revision``,
``scope``, ``reason``, ``detail``, ``examined``, ``findings``,
``duration_seconds``) plus two optional keys this module adds, ``digest`` (the
tarball SHA-256 a build-tier result is about) and ``items`` (what failed, for
the finding fingerprint). Any other key is refused.

Different than canonical: ``CheckOutcome`` has no ``digest`` or ``items``
field, and ADR-113 allows either extending it or a sibling type. This module
takes the sibling, :class:`EvidenceRecord`, so ``evidence.py`` (1002 lines)
does not grow and no existing validator changes.

This module checks that a record names the candidate. It does not prove the
record was written by a trusted job. That is the provenance check in decision
5, which reads the workflow-run API and is separate work.
"""

from __future__ import annotations

import json
import math
import os
import re
import stat
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from scripts.validation.evidence import CheckOutcome, EvidenceState

REASON_MALFORMED = "evidence.malformed"
REASON_UNREADABLE = "evidence.unreadable"
REASON_REVISION_MISMATCH = "binding.revision_mismatch"
REASON_DIGEST_MISMATCH = "binding.digest_mismatch"
REASON_DIGEST_MISSING = "binding.digest_missing"
REASON_CANDIDATE_DIGEST_ABSENT = "binding.candidate_digest_absent"

MAX_EVIDENCE_BYTES = 1_048_576
_SHOWN_LIMIT = 200
_SHA_RE = re.compile(r"[0-9a-f]{40}")
_DIGEST_RE = re.compile(r"[0-9a-f]{64}")
_OUTCOME_KEYS = frozenset(
    {
        "validator",
        "state",
        "revision",
        "scope",
        "reason",
        "detail",
        "examined",
        "findings",
        "duration_seconds",
    }
)
_RECORD_KEYS = _OUTCOME_KEYS | {"digest", "items"}


class EvidenceError(ValueError):
    """A document is not a well-formed evidence record."""


class BindingTier(str, Enum):
    """What a result must name to describe the candidate."""

    COMMIT = "commit"
    BUILD = "build"


@dataclass(frozen=True, slots=True)
class Candidate:
    """The thing being promoted: a commit and, once built, its tarball digest."""

    sha: str
    digest: str = ""

    def __post_init__(self) -> None:
        """Refuse an abbreviated SHA or a malformed digest."""
        if not _SHA_RE.fullmatch(self.sha):
            raise ValueError("candidate sha must be a 40-character lowercase hex commit SHA")
        if self.digest and not _DIGEST_RE.fullmatch(self.digest):
            raise ValueError("candidate digest must be 64 lowercase hex characters or empty")


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    """One persisted result: the typed outcome plus its digest and failed items."""

    outcome: CheckOutcome
    digest: str = ""
    items: tuple[str, ...] = ()
    source: str = ""


@dataclass(frozen=True, slots=True)
class RejectedEvidence:
    """A record that cannot count, kept so the report can say why it is missing."""

    source: str
    validator: str
    reason: str
    detail: str = ""

    def to_dict(self) -> dict[str, str]:
        """Return the JSON form written into the promotion manifest."""
        return {
            "source": self.source,
            "validator": self.validator,
            "reason": self.reason,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class BoundEvidence:
    """Records that name the candidate, and records that do not."""

    bound: tuple[EvidenceRecord, ...]
    rejected: tuple[RejectedEvidence, ...]


def _optional_int(document: dict[str, Any], key: str) -> int | None:
    value = document.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise EvidenceError(f"'{key}' must be an integer or null")
    return value


def _string(document: dict[str, Any], key: str, default: str = "") -> str:
    value = document.get(key, default)
    if not isinstance(value, str):
        raise EvidenceError(f"'{key}' must be a string")
    return value


def _items(document: dict[str, Any]) -> tuple[str, ...]:
    value = document.get("items", [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise EvidenceError("'items' must be a list of strings")
    return tuple(value)


def _duration(document: dict[str, Any]) -> float:
    value = document.get("duration_seconds", 0.0)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise EvidenceError("'duration_seconds' must be a finite number")
    return float(value)


def _state(document: dict[str, Any]) -> EvidenceState:
    try:
        return EvidenceState(_string(document, "state"))
    except ValueError as exc:
        raise EvidenceError("'state' must be one of PASS, FAIL, SKIP, BLOCKED, UNKNOWN") from exc


def parse_evidence(document: object, source: str = "") -> EvidenceRecord:
    """Validate one decoded evidence document and return its record."""
    if not isinstance(document, dict):
        raise EvidenceError("evidence must be a JSON object")
    extra = sorted(set(document) - _RECORD_KEYS)
    if extra:
        raise EvidenceError(f"unknown key(s) {_shown(', '.join(extra))}")
    digest = _string(document, "digest")
    if digest and not _DIGEST_RE.fullmatch(digest):
        raise EvidenceError("'digest' must be 64 lowercase hex characters")
    try:
        outcome = CheckOutcome(
            validator=_string(document, "validator"),
            state=_state(document),
            revision=_string(document, "revision"),
            scope=_string(document, "scope"),
            reason=_string(document, "reason"),
            detail=_string(document, "detail"),
            examined=_optional_int(document, "examined"),
            findings=_optional_int(document, "findings"),
            duration_seconds=_duration(document),
        )
    except (ValueError, TypeError) as exc:
        raise EvidenceError(str(exc)) from exc
    items = _items(document)
    if items and outcome.state is EvidenceState.PASS:
        raise EvidenceError("a PASS must not list failed items")
    return EvidenceRecord(outcome=outcome, digest=digest, items=items, source=source)


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    seen: set[str] = set()
    repeated: set[str] = set()
    for key, _ in pairs:
        (repeated if key in seen else seen).add(key)
    if repeated:
        raise ValueError(f"duplicate key(s) {_shown(', '.join(sorted(repeated)))}")
    return dict(pairs)


def _reject_constant(name: str) -> object:
    raise ValueError(f"non-finite number {name} is not valid evidence")


def _clean(value: str) -> str:
    """Return ``value`` control-free and short enough to log safely.

    Evidence is attacker-writable text. A key name or file name can hold a
    newline that starts a workflow command line, so every value this module
    echoes goes through here first.
    """
    cleaned = "".join(char if char.isprintable() else "?" for char in value)
    if len(cleaned) > _SHOWN_LIMIT:
        cleaned = cleaned[:_SHOWN_LIMIT] + "..."
    return cleaned


def _shown(value: str) -> str:
    """Return the cleaned ``value`` in quotes, for use inside an error message."""
    return repr(_clean(value))


def _read_regular_file(path: Path) -> str:
    """Return the text of a regular file no larger than the cap, or raise OSError.

    Refuses a symlink up front, then opens with ``O_NOFOLLOW`` where the
    platform has it (Windows does not, so the up-front check is the portable
    guard there) and checks the opened descriptor, so a path swapped for a
    symlink after listing is refused rather than followed. Reads at most one
    byte past the cap so a file that grew is still caught.
    """
    if path.is_symlink():
        raise OSError("a symlink is not accepted")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    descriptor = os.open(path, flags)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise OSError("not a regular file")
        data = os.read(descriptor, MAX_EVIDENCE_BYTES + 1)
    finally:
        os.close(descriptor)
    if len(data) > MAX_EVIDENCE_BYTES:
        raise OSError(f"larger than {MAX_EVIDENCE_BYTES} bytes")
    return data.decode("utf-8")


def _load_one(path: Path) -> EvidenceRecord | RejectedEvidence:
    source = _clean(path.name)
    try:
        text = _read_regular_file(path)
    except (OSError, UnicodeDecodeError) as exc:
        return RejectedEvidence(source, "", REASON_UNREADABLE, str(exc))
    try:
        document = json.loads(
            text, object_pairs_hook=_reject_duplicate_keys, parse_constant=_reject_constant
        )
        return parse_evidence(document, source)
    except (ValueError, RecursionError) as exc:
        validator = _validator_hint(text)
        return RejectedEvidence(source, validator, REASON_MALFORMED, str(exc))


def _validator_hint(text: str) -> str:
    """Return the validator name from malformed evidence when one can be read."""
    try:
        document = json.loads(text)
    except (ValueError, RecursionError):
        return ""
    name = document.get("validator") if isinstance(document, dict) else ""
    return _clean(name) if isinstance(name, str) else ""


def load_evidence_dir(
    directory: Path,
) -> tuple[tuple[EvidenceRecord, ...], tuple[RejectedEvidence, ...]]:
    """Load every ``*.json`` file in ``directory``, keeping what fails to load.

    The extension match is case-sensitive on every platform, so a directory
    holding ``x.JSON`` loads the same on Windows and Linux (it loads neither).

    A file that cannot be read or parsed becomes a rejection, never a skip: a
    dropped file is a validator that silently did not report. A directory that
    cannot be listed raises ``OSError`` for the caller to turn into a block.
    """
    if not directory.is_dir():
        raise NotADirectoryError(f"evidence directory {directory.name!r} is not a directory")
    records: list[EvidenceRecord] = []
    rejected: list[RejectedEvidence] = []
    for path in sorted(directory.iterdir()):
        if not path.name.endswith(".json"):
            continue
        loaded = _load_one(path)
        if isinstance(loaded, EvidenceRecord):
            records.append(loaded)
        else:
            rejected.append(loaded)
    return tuple(records), tuple(rejected)


def binding_problem(record: EvidenceRecord, candidate: Candidate, tier: BindingTier) -> str | None:
    """Return the reason a record does not describe the candidate, or None."""
    if record.outcome.revision != candidate.sha:
        return REASON_REVISION_MISMATCH
    if tier is BindingTier.COMMIT:
        return None
    if not candidate.digest:
        return REASON_CANDIDATE_DIGEST_ABSENT
    if not record.digest:
        return REASON_DIGEST_MISSING
    if record.digest != candidate.digest:
        return REASON_DIGEST_MISMATCH
    return None


def bind_records(
    records: tuple[EvidenceRecord, ...],
    candidate: Candidate,
    build_validators: frozenset[str],
) -> BoundEvidence:
    """Split records into those bound to ``candidate`` and those rejected.

    A validator named in ``build_validators`` is about the build and binds on
    SHA and digest. Every other validator binds on SHA alone. ``build_validators``
    has no default: an omitted set would bind a build result on SHA alone with
    no signal, so the caller must state it, and the applicability table owns it.

    A rejected record is reported, not dropped, and does not cancel a bound
    record from the same validator. A validator with no bound record is the
    caller's to count as missing. Two bound records for one validator both stay,
    so worst-wins aggregation, not file order, decides the state.
    """
    bound: list[EvidenceRecord] = []
    rejected: list[RejectedEvidence] = []
    for record in records:
        tier = (
            BindingTier.BUILD
            if record.outcome.validator in build_validators
            else BindingTier.COMMIT
        )
        problem = binding_problem(record, candidate, tier)
        if problem is None:
            bound.append(record)
            continue
        rejected.append(
            RejectedEvidence(
                record.source,
                record.outcome.validator,
                problem,
                f"revision {record.outcome.revision!r}, digest {record.digest!r}",
            )
        )
    return BoundEvidence(bound=tuple(bound), rejected=tuple(rejected))

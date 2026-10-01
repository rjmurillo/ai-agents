#!/usr/bin/env python3
"""Governed exception records for the release promotion gate.

ADR-113 decisions 6, 7, and 8, issue #5636. Quoted from
``.project-toolkit/architecture/ADR-113-promotion-gate-evidence-and-exceptions.md``:

    "An exception names one fingerprint, not a whole validator and reason
    pair." (decision 6)

    "Required fields: rationale, owner, approval, expiry date, remediation
    date." (decision 6)

    "Until a second approving identity exists, no exception can be approved,
    so the gate accepts no exceptions and every unfixed finding is
    `unresolved`." (decision 7)

    "Expiry is compared with the current UTC date at aggregator run time. A
    missing or unparseable date fails closed. An exception past its expiry
    licenses nothing, and the finding becomes `expired`. A record with a
    missing field, or a still-open finding past its remediation date, is
    rejected. A malformed exceptions file fails the load, which blocks every
    promotion until it is fixed." (decision 8)

File shape, ``.agents/governance/promotion-exceptions.json``, schema 1::

    {"schema_version": "1", "entries": [{
      "validator": "...", "reason": "dotted.slug", "scope": "...",
      "item": "optional: the one thing that failed",
      "rationale": "...", "owner": "handle",
      "approval": {"pr": 123, "reviewer": "handle"},
      "expires": "YYYY-MM-DD", "remediate_by": "YYYY-MM-DD"}]}

The loader raises ``ExceptionsFileError`` for any bad entry, naming every bad
entry. A missing file is an empty list: no finding is excused. An unreadable
or malformed file is an error, never an empty list, because a parse failure
read as "nothing excused" would hide the fault.

Approval is not read from the file. ``approval`` names the pull request and
the reviewer, and an injected :data:`ApprovalVerifier` proves them against the
GitHub API at promotion time. :func:`deny_all_approvals` is the verifier
decision 7 requires while the repository has one code owner.

Canonical source and divergences. The nearest loader is
``scripts/validation/bypass_allowlist.py`` (decision D17). The fragments this
module follows, quoted verbatim:

    _OWNER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    _DATE_RE = re.compile(r"^\\d{4}-\\d{2}-\\d{2}$")

and its ``load_allowlist`` contract, "Returns an empty allowlist when the file
does not exist. Raises ``AllowlistError`` for an unreadable, non-JSON, or
invalid file."

Same: a ``schema_version`` of ``"1"``, per-entry required fields, a dated
``expires``, a missing file read as empty, and an invalid file that raises.

Stricter than canonical: the patterns use ``fullmatch``, because the canonical
``$`` also matches before a trailing newline, so ``"bob\\n"`` passes there.
Control characters include Unicode ``Cc``, ``Cf``, ``Zl``, and ``Zp`` (bidi
overrides, U+2028), where the canonical check covers ASCII controls and DEL
only. Duplicate JSON keys fail the load, where ``json.loads`` keeps the last.
``remediate_by`` after ``expires`` is refused; the ADR does not state that
rule. ``item`` null is refused rather than read as absent.

Different from the ADR: decision 6 says per-item exceptions wait for a
structured items field. ``scripts/validation/promotion_evidence.py`` supplies
that field on its own record type, so schema 1 accepts ``item`` now. Today's
``CheckOutcome`` carries no items, so an exception with an ``item`` matches
only evidence whose record lists that item. The expiry day itself is valid
(``expires < today`` is expired); the ADR says "past its expiry", which this
reads as strictly after.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import Enum
from pathlib import Path
from typing import cast

EXCEPTIONS_RELATIVE_PATH = Path(".agents") / "governance" / "promotion-exceptions.json"
_FORBIDDEN_CATEGORIES = frozenset({"Cc", "Cf", "Zl", "Zp"})
_SHOWN_PATH = EXCEPTIONS_RELATIVE_PATH.as_posix()
SCHEMA_VERSION = "1"

_ENTRY_KEYS = frozenset(
    {
        "validator",
        "reason",
        "scope",
        "item",
        "rationale",
        "owner",
        "approval",
        "expires",
        "remediate_by",
    }
)
_REQUIRED_KEYS = _ENTRY_KEYS - {"item"}
_APPROVAL_KEYS = frozenset({"pr", "reviewer"})
_REASON_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)*$")
_HANDLE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ExceptionsFileError(Exception):
    """The exceptions file is unreadable or holds an invalid entry."""


class ExceptionStatus(str, Enum):
    """Whether an exception licenses a finding on a given day."""

    ACTIVE = "active"
    EXPIRED = "expired"
    REMEDIATION_OVERDUE = "remediation_overdue"
    UNAPPROVED = "unapproved"


def finding_fingerprint(validator: str, reason: str, scope: str, item: str = "") -> str:
    """Return the SHA-256 identity of one finding.

    The fields are JSON-encoded as one array, so no value can contain a
    separator that lets ``("a", "bc")`` and ``("ab", "c")``, or a finding's
    ``scope="a\x1fb"`` and an exception's ``scope="a", item="b"``, hash alike.
    An empty ``item`` identifies a finding no validator itemised, which is the
    only identity available until results carry a structured items list.
    """
    encoded = json.dumps([validator, reason, scope, item], ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class PromotionException:
    """One approved licence for one finding, with an end date."""

    validator: str
    reason: str
    scope: str
    item: str
    rationale: str
    owner: str
    approval_pr: int
    approver: str
    expires: date
    remediate_by: date

    @property
    def fingerprint(self) -> str:
        """The finding this record covers."""
        return finding_fingerprint(self.validator, self.reason, self.scope, self.item)

    def to_dict(self) -> dict[str, object]:
        """Return the JSON form written into the promotion manifest."""
        return {
            "fingerprint": self.fingerprint,
            "validator": self.validator,
            "reason": self.reason,
            "scope": self.scope,
            "item": self.item,
            "rationale": self.rationale,
            "owner": self.owner,
            "approval": {"pr": self.approval_pr, "reviewer": self.approver},
            "expires": self.expires.isoformat(),
            "remediate_by": self.remediate_by.isoformat(),
        }


#: Proves that ``approver`` left an approving review on ``approval_pr`` as a
#: code owner other than the pull request's author. Returns False on any doubt.
#: A real verifier must also prove that the pull request merged, that its diff
#: added this exact entry, that the approval is on the head commit and not
#: dismissed, and must compare logins case-insensitively. Otherwise an entry
#: could cite any old approved pull request.
ApprovalVerifier = Callable[[PromotionException], bool]


def deny_all_approvals(_record: PromotionException) -> bool:
    """Refuse every approval. ADR-113 decision 7 for a one-owner repository."""
    return False


def _approved(record: PromotionException, verifier: ApprovalVerifier) -> bool:
    """Return True only when the verifier answers exactly ``True``.

    A verifier that raises (an API outage) or returns a truthy non-bool (an
    error object) has not proven an approval, so both read as unapproved.
    """
    try:
        return verifier(record) is True
    except Exception:  # any verifier fault must fail closed
        return False


def utc_today() -> date:
    """Return the current UTC date, the clock decision 8 names for expiry."""
    return datetime.now(UTC).date()


def exception_status(
    record: PromotionException,
    today: date,
    verifier: ApprovalVerifier,
    finding_open: bool = True,
) -> ExceptionStatus:
    """Return what ``record`` licenses on ``today``.

    Order matters. A lapsed record is ``EXPIRED`` whatever else is true of it,
    because the report must say the exception ran out. A still-open finding past
    its remediation date and an approval the verifier cannot prove both license
    nothing, and both leave the finding ``unresolved``.
    """
    if record.expires < today:
        return ExceptionStatus.EXPIRED
    if finding_open and record.remediate_by < today:
        return ExceptionStatus.REMEDIATION_OVERDUE
    if _approved(record, verifier):
        return ExceptionStatus.ACTIVE
    return ExceptionStatus.UNAPPROVED


def _has_control_char(value: str) -> bool:
    """True for a control, format, or line-separator character.

    Covers ASCII controls and DEL, C1 controls, bidirectional overrides
    (U+202A to U+202E), and U+2028 and U+2029, so a rationale cannot start a
    workflow command line or visually reorder what a reviewer reads.
    """
    return any(unicodedata.category(char) in _FORBIDDEN_CATEGORIES for char in value)


def _text_problem(entry: dict[str, object], field: str, required: bool = True) -> str | None:
    if field not in entry and not required:
        return None
    value = entry.get(field)
    if not isinstance(value, str) or (required and not value.strip()):
        return f"'{field}' must be a non-empty string"
    if _has_control_char(value):
        return f"'{field}' must not contain a control character"
    return None


def _date_problem(entry: dict[str, object], field: str) -> str | None:
    value = entry.get(field)
    if not isinstance(value, str) or not _DATE_RE.fullmatch(value):
        return f"'{field}' must be a YYYY-MM-DD date"
    try:
        date.fromisoformat(value)
    except ValueError:
        return f"'{field}' must be a real calendar date"
    return None


def _handle_problem(value: object, label: str) -> str | None:
    if not isinstance(value, str) or not _HANDLE_RE.fullmatch(value) or _has_control_char(value):
        return f"{label} must be a handle of letters, digits, '.', '_', or '-'"
    return None


def _approval_problem(entry: dict[str, object]) -> str | None:
    approval = entry.get("approval")
    if not isinstance(approval, dict) or set(approval) != _APPROVAL_KEYS:
        return "'approval' must be an object with exactly 'pr' and 'reviewer'"
    pr_number = approval["pr"]
    if isinstance(pr_number, bool) or not isinstance(pr_number, int) or pr_number < 1:
        return "'approval.pr' must be a positive integer"
    return _handle_problem(approval["reviewer"], "'approval.reviewer'")


def _shape_problems(entry: dict[str, object]) -> list[str]:
    problems: list[str] = []
    missing = sorted(_REQUIRED_KEYS - set(entry))
    if missing:
        problems.append(f"missing {', '.join(missing)}")
    extra = sorted(set(entry) - _ENTRY_KEYS)
    if extra:
        problems.append(f"unknown key(s) {', '.join(extra)}")
    return problems


def _field_problems(entry: dict[str, object]) -> list[str]:
    checks = [
        *(_text_problem(entry, f) for f in ("validator", "scope", "rationale")),
        _text_problem(entry, "item", required=False),
        _text_problem(entry, "reason"),
        _handle_problem(entry.get("owner"), "'owner'"),
        _approval_problem(entry) if "approval" in entry else None,
        _date_problem(entry, "expires"),
        _date_problem(entry, "remediate_by"),
    ]
    problems = [problem for problem in checks if problem]
    reason = entry.get("reason")
    if isinstance(reason, str) and reason.strip() and not _REASON_RE.fullmatch(reason):
        problems.append("'reason' must be a dotted lowercase slug such as 'diff.failed'")
    return problems


def _entry_problems(entry: object) -> list[str]:
    if not isinstance(entry, dict):
        return ["entry must be a JSON object"]
    problems = _shape_problems(entry)
    problems.extend(_field_problems(entry))
    if problems:
        return list(dict.fromkeys(problems))
    if date.fromisoformat(entry["remediate_by"]) > date.fromisoformat(entry["expires"]):
        return ["'remediate_by' must not be after 'expires'"]
    return []


def _build(entry: dict[str, object]) -> PromotionException:
    approval = cast("dict[str, object]", entry["approval"])
    return PromotionException(
        validator=str(entry["validator"]),
        reason=str(entry["reason"]),
        scope=str(entry["scope"]),
        item=str(entry.get("item", "")),
        rationale=str(entry["rationale"]),
        owner=str(entry["owner"]),
        approval_pr=cast("int", approval["pr"]),
        approver=str(approval["reviewer"]),
        expires=date.fromisoformat(str(entry["expires"])),
        remediate_by=date.fromisoformat(str(entry["remediate_by"])),
    )


def parse_exceptions(document: object) -> tuple[PromotionException, ...]:
    """Validate a decoded exceptions document and return its records."""
    if not isinstance(document, dict):
        raise ExceptionsFileError("exceptions file must be a JSON object")
    if document.get("schema_version") != SCHEMA_VERSION:
        raise ExceptionsFileError(f"'schema_version' must be {SCHEMA_VERSION!r}")
    raw_entries = document.get("entries")
    if not isinstance(raw_entries, list):
        raise ExceptionsFileError("'entries' must be a list")
    problems: list[str] = []
    for index, entry in enumerate(raw_entries):
        problems.extend(f"entries[{index}]: {p}" for p in _entry_problems(entry))
    if problems:
        raise ExceptionsFileError("; ".join(problems))
    records = tuple(_build(entry) for entry in raw_entries)
    fingerprints = [record.fingerprint for record in records]
    if len(set(fingerprints)) != len(fingerprints):
        raise ExceptionsFileError("two entries name the same finding; keep one")
    return records


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Refuse a JSON object that repeats a key, which would let the last win."""
    keys = [key for key, _ in pairs]
    repeated = sorted({key for key in keys if keys.count(key) > 1})
    if repeated:
        raise ValueError(f"duplicate key(s) {', '.join(repeated)}")
    return dict(pairs)


def load_exceptions(repo_root: Path) -> tuple[PromotionException, ...]:
    """Read and validate the exceptions file under ``repo_root``.

    Returns an empty tuple when the file does not exist. Raises
    ``ExceptionsFileError`` for an unreadable, non-JSON, or invalid file.

    ``repo_root`` must be a checkout of the default branch. ADR-113 decision 5
    reads this file from there, so a candidate cannot edit its own exceptions.
    The loader reads whatever root it is given and cannot check that.
    """
    path = repo_root / EXCEPTIONS_RELATIVE_PATH
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ()
    except (OSError, UnicodeDecodeError) as exc:
        raise ExceptionsFileError(
            f"cannot read {EXCEPTIONS_RELATIVE_PATH.as_posix()}: {exc}"
        ) from exc
    try:
        document = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except (json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise ExceptionsFileError(f"cannot parse {_SHOWN_PATH}: {exc}") from exc
    return parse_exceptions(document)

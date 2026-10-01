#!/usr/bin/env python3
"""Findings, their four classes, and the promotion manifest.

ADR-113 decisions 6, 8, and 9, issue #5636. Quoted from
``.project-toolkit/architecture/ADR-113-promotion-gate-evidence-and-exceptions.md``
decision 9:

    | Typed state | Finding? |
    | `PASS` | No |
    | `SKIP` with reason `policy.exempt`, or a validator the applicability
      table marks not applicable | No |
    | `SKIP` with any other reason | Yes |
    | `FAIL`, `BLOCKED`, `UNKNOWN` | Yes |
    | An applicable validator with no result | Yes, as `UNKNOWN` |

    "Each finding is exactly one of: `remediated`: the finding appears in the
    previous promoted manifest and no longer reproduces at the candidate. [...]
    `accepted`: an unexpired, approved exception covers its fingerprint.
    `expired`: an exception covered it and has lapsed. `unresolved`: no fix and
    no exception."

    "Promotion proceeds only when `unresolved` and `expired` are both zero."

Different than canonical: the table's "validator the applicability table marks
not applicable" row is not implemented here. The applicability table is
separate work, so the caller passes the validators that must have run, and a
validator outside that set still produces findings when it reports a non-pass.

An exception whose remediation date has passed, or whose approval the verifier
cannot prove, licenses nothing, so its finding is ``unresolved``. Only a lapsed
exception makes a finding ``expired``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any

from scripts.validation.evidence import (
    REASON_POLICY_EXEMPT,
    AggregateOutcome,
    CheckOutcome,
    EvidenceState,
    GatePolicy,
    aggregate,
)
from scripts.validation.promotion_evidence import (
    REASON_MALFORMED,
    REASON_UNREADABLE,
    Candidate,
    EvidenceRecord,
    RejectedEvidence,
)
from scripts.validation.promotion_exceptions import (
    ApprovalVerifier,
    ExceptionStatus,
    PromotionException,
    exception_status,
    finding_fingerprint,
)

MANIFEST_SCHEMA_VERSION = "1"
REASON_MISSING = "evidence.missing"
MAX_MANIFEST_BYTES = 8_388_608
_SHA_RE = re.compile(r"[0-9a-f]{40}")


class FindingClass(str, Enum):
    """The four report classes. Every finding is exactly one."""

    REMEDIATED = "remediated"
    ACCEPTED = "accepted"
    EXPIRED = "expired"
    UNRESOLVED = "unresolved"


class ManifestError(ValueError):
    """The previous manifest is unreadable or not a promotion manifest."""


@dataclass(frozen=True, slots=True)
class Finding:
    """One non-pass observation, identified by its fingerprint."""

    validator: str
    reason: str
    scope: str
    item: str
    state: EvidenceState
    detail: str = ""

    @property
    def fingerprint(self) -> str:
        """The identity an exception names."""
        return finding_fingerprint(self.validator, self.reason, self.scope, self.item)


@dataclass(frozen=True, slots=True)
class ClassifiedFinding:
    """A finding with its class and, when one applies, the exception behind it."""

    finding: Finding
    finding_class: FindingClass
    exception: PromotionException | None = None
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON form written into the manifest."""
        return {
            "fingerprint": self.finding.fingerprint,
            "class": self.finding_class.value,
            "validator": self.finding.validator,
            "reason": self.finding.reason,
            "scope": self.finding.scope,
            "item": self.finding.item,
            "state": self.finding.state.value,
            "detail": self.finding.detail,
            "note": self.note,
            "exception": self.exception.to_dict() if self.exception else None,
        }


@dataclass(frozen=True, slots=True)
class PreviousFinding:
    """A finding the previous promoted manifest recorded as still open."""

    fingerprint: str
    validator: str
    reason: str
    scope: str
    item: str


@dataclass(frozen=True, slots=True)
class PreviousManifest:
    """The still-open findings of the last promoted candidate, and that candidate."""

    candidate_sha: str
    findings: tuple[PreviousFinding, ...]


def is_finding(outcome: CheckOutcome) -> bool:
    """Apply the decision 9 table to one typed outcome."""
    if outcome.state is EvidenceState.PASS:
        return False
    return not (outcome.state is EvidenceState.SKIP and outcome.reason == REASON_POLICY_EXEMPT)


def findings_for(record: EvidenceRecord) -> tuple[Finding, ...]:
    """Return the findings one record carries: one per failed item, else one."""
    outcome = record.outcome
    if not is_finding(outcome):
        return ()
    items = record.items or ("",)
    return tuple(
        Finding(
            validator=outcome.validator,
            reason=outcome.reason,
            scope=outcome.scope,
            item=item,
            state=outcome.state,
            detail=outcome.detail,
        )
        for item in items
    )


def _shows_a_result(record: EvidenceRecord) -> bool:
    """A PASS counts only when it says it examined something; a finding always counts."""
    outcome = record.outcome
    if outcome.state is EvidenceState.PASS:
        return bool(outcome.examined)
    return is_finding(outcome)


def missing_outcomes(
    required: Iterable[str], bound: Iterable[EvidenceRecord], candidate: Candidate
) -> tuple[CheckOutcome, ...]:
    """Return one ``UNKNOWN`` outcome per required validator that proved nothing.

    A validator counts as present when it has a bound ``PASS`` that examined at
    least one item, or a bound record that already yields a finding. A ``PASS``
    that examined nothing (zero, or no count) proves nothing, which
    ``.claude/rules/ci-scripts.md`` MUST 12 names as the silent pass.

    A lone ``SKIP`` with ``policy.exempt`` does not count: the record is
    candidate-writable, and ADR-113 decision 9 accepts the exempt row only for a
    validator the applicability table marks not applicable, which is separate
    work. Until then a required validator must show a result.
    """
    present = {record.outcome.validator for record in bound if _shows_a_result(record)}
    return tuple(
        CheckOutcome.unknown(
            validator,
            reason=REASON_MISSING,
            scope=f"candidate {candidate.sha[:12]}",
            detail="no evidence bound to the candidate",
        )
        for validator in sorted(set(required) - present)
    )


def unreadable_outcomes(rejected: Iterable[RejectedEvidence]) -> tuple[CheckOutcome, ...]:
    """Return one ``UNKNOWN`` outcome per evidence file that could not be parsed.

    A binding rejection is not here: it counts only when its validator has no
    bound record, which :func:`missing_outcomes` already covers. A file that
    cannot be parsed has no trustworthy validator name, so it blocks on its own.
    """
    return tuple(
        CheckOutcome.unknown(
            item.validator or "evidence",
            reason=item.reason,
            scope=f"evidence file {item.source}",
            detail=item.detail,
        )
        for item in rejected
        if item.reason in (REASON_MALFORMED, REASON_UNREADABLE)
    )


def collect_findings(
    bound: Iterable[EvidenceRecord], synthesized: Iterable[CheckOutcome]
) -> tuple[Finding, ...]:
    """Return every finding from bound records and synthesized missing outcomes."""
    found: list[Finding] = []
    for record in bound:
        found.extend(findings_for(record))
    for outcome in synthesized:
        found.extend(findings_for(EvidenceRecord(outcome=outcome)))
    return tuple(found)


def _classify_one(
    finding: Finding,
    exception: PromotionException | None,
    today: date,
    verifier: ApprovalVerifier,
) -> ClassifiedFinding:
    if exception is None:
        return ClassifiedFinding(finding, FindingClass.UNRESOLVED)
    status = exception_status(exception, today, verifier)
    if status is ExceptionStatus.ACTIVE:
        return ClassifiedFinding(finding, FindingClass.ACCEPTED, exception)
    if status is ExceptionStatus.EXPIRED:
        return ClassifiedFinding(finding, FindingClass.EXPIRED, exception, "exception lapsed")
    return ClassifiedFinding(
        finding, FindingClass.UNRESOLVED, exception, f"exception not honoured: {status.value}"
    )


def classify_findings(
    findings: Iterable[Finding],
    exceptions: Iterable[PromotionException],
    today: date,
    verifier: ApprovalVerifier,
) -> tuple[ClassifiedFinding, ...]:
    """Class every current finding as accepted, expired, or unresolved."""
    by_fingerprint = {record.fingerprint: record for record in exceptions}
    return tuple(
        _classify_one(finding, by_fingerprint.get(finding.fingerprint), today, verifier)
        for finding in findings
    )


def passed_scopes(bound: Iterable[EvidenceRecord]) -> frozenset[tuple[str, str]]:
    """Return the ``(validator, scope)`` pairs with a bound ``PASS`` that examined something.

    The same rule as ``missing_outcomes``: a PASS that examined nothing proves
    nothing, so it cannot prove an old finding fixed either.
    """
    return frozenset(
        (record.outcome.validator, record.outcome.scope)
        for record in bound
        if record.outcome.state is EvidenceState.PASS and record.outcome.examined
    )


def remediated_findings(
    previous: Iterable[PreviousFinding],
    current: Iterable[Finding],
    passed: frozenset[tuple[str, str]],
) -> tuple[PreviousFinding, ...]:
    """Return previous open findings the candidate proves are fixed.

    A finding is remediated only when it no longer reproduces and its validator
    re-ran on the same scope and passed. A validator that went missing, was
    rejected for a SHA or digest mismatch, or dropped out of the required set
    leaves its old finding open: nothing re-ran, so nothing was fixed.
    """
    still_present = {finding.fingerprint for finding in current}
    return tuple(
        item
        for item in previous
        if item.fingerprint not in still_present and (item.validator, item.scope) in passed
    )


def _previous_finding(raw: dict[str, object]) -> PreviousFinding:
    fields = ("fingerprint", "validator", "reason", "scope", "item")
    values = [raw.get(key) for key in fields]
    if not all(isinstance(value, str) for value in values):
        raise ManifestError("a finding needs string fingerprint, validator, reason, scope, item")
    fingerprint, validator, reason, scope, item = (str(value) for value in values)
    return PreviousFinding(fingerprint, validator, reason, scope, item)


_CLASS_VALUES = frozenset(item.value for item in FindingClass)


def _checked_entry(entry: object) -> dict[str, object]:
    """Return a finding entry, or raise: a skipped entry would lose an open finding."""
    if not isinstance(entry, dict):
        raise ManifestError("every previous finding must be a JSON object")
    if entry.get("class") not in _CLASS_VALUES:
        raise ManifestError("every previous finding needs a class of the four finding classes")
    return entry


def parse_previous_manifest(document: object) -> PreviousManifest:
    """Return the still-open findings a previous manifest recorded.

    A ``remediated`` entry is not open, so it is not a baseline for the next
    comparison. A document that is not a promotion manifest raises: a baseline
    that silently read as empty would report every fixed finding as never seen.
    """
    if not isinstance(document, dict) or document.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ManifestError(f"previous manifest must be schema {MANIFEST_SCHEMA_VERSION!r}")
    candidate = document.get("candidate")
    sha = candidate.get("sha") if isinstance(candidate, dict) else None
    if not isinstance(sha, str) or not _SHA_RE.fullmatch(sha):
        raise ManifestError("previous manifest needs candidate.sha as a 40-character hex SHA")
    findings = document.get("findings")
    if not isinstance(findings, list):
        raise ManifestError("previous manifest 'findings' must be a list")
    still_open = tuple(
        _previous_finding(raw)
        for raw in (_checked_entry(entry) for entry in findings)
        if raw["class"] != FindingClass.REMEDIATED.value
    )
    return PreviousManifest(candidate_sha=sha, findings=still_open)


def load_previous_manifest(path: Path) -> PreviousManifest:
    """Read a previous manifest file. Raises ``ManifestError`` or ``OSError``."""
    with path.open("rb") as handle:
        data = handle.read(MAX_MANIFEST_BYTES + 1)
    if len(data) > MAX_MANIFEST_BYTES:
        raise ManifestError(f"previous manifest is larger than {MAX_MANIFEST_BYTES} bytes")
    try:
        document = json.loads(data.decode("utf-8"), parse_constant=_reject_constant)
    except (ValueError, RecursionError) as exc:
        raise ManifestError(f"previous manifest is not valid JSON: {type(exc).__name__}") from exc
    return parse_previous_manifest(document)


def _reject_constant(name: str) -> object:
    raise ValueError(f"non-finite number {name}")


def counts(classified: Iterable[ClassifiedFinding], remediated: int) -> dict[str, int]:
    """Return the per-class totals, every class present at zero."""
    tally = {item.value: 0 for item in FindingClass}
    for entry in classified:
        tally[entry.finding_class.value] += 1
    tally[FindingClass.REMEDIATED.value] = remediated
    return tally


def blocks_promotion(tally: Mapping[str, int]) -> bool:
    """Decision 9: promotion proceeds only when unresolved and expired are both zero."""
    return bool(tally[FindingClass.UNRESOLVED.value] or tally[FindingClass.EXPIRED.value])


def overall_state(outcomes: Iterable[CheckOutcome]) -> AggregateOutcome:
    """Aggregate every outcome worst-wins. An empty set is ``UNKNOWN``."""
    return aggregate("promotion", tuple(outcomes), GatePolicy())

"""Field checks for the metric artifact contract (#5639).

Each ``check_*`` function inspects one slice of a payload and returns a list
of :class:`Finding`. None of them raises on malformed input: a payload is
untrusted JSON, so a wrong type is a finding, not an exception.
``scripts/metrics/metric_artifact.py`` composes the checks and resolves the
status. Timestamps must be ISO-8601 with a zero UTC offset, which is how the
contract makes time windows timezone-normalized.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, TypeGuard

SCHEMA_VERSION = 1
STATUSES = ("PASS", "WARN", "BLOCKED", "INVALID")
KINDS = ("stock_snapshot", "event_flow", "same_cohort_rate", "reconstructed_estimate")
UNITS = ("issues", "prs", "reviews", "trailers", "receipts")
WINDOWED_KINDS = ("event_flow", "same_cohort_rate")
COUNT_KEYS = ("raw", "derived", "null", "duplicates", "excluded")
# A window that ends this close to retrieval can miss or include a record that
# lands between two reads, so the count may be off by one.
TIMING_RACE_MARGIN = timedelta(seconds=60)

_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True, slots=True)
class Finding:
    """One validation result: the status it forces, the field, and the reason."""

    status: str
    field: str
    message: str


def severity(status: str) -> int:
    """Rank a status so the worst one wins. Unknown statuses rank as INVALID."""
    return STATUSES.index(status) if status in STATUSES else len(STATUSES) - 1


def is_count(value: object) -> TypeGuard[int]:
    """True for a non-negative int. ``bool`` is an int subclass and is refused."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def parse_utc(value: object) -> datetime | None:
    """Parse an ISO-8601 string with a zero UTC offset, else return ``None``.

    ``datetime.fromisoformat`` rejects a trailing ``Z`` before Python 3.11, and
    the hook-portability floor is 3.10, so the suffix is rewritten first.
    """
    if not isinstance(value, str) or not value:
        return None
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        return None
    return parsed.astimezone(timezone.utc)


def section(payload: Mapping[str, Any], key: str, findings: list[Finding]) -> Mapping[str, Any]:
    """Return ``payload[key]`` when it is a mapping, else record INVALID and return ``{}``."""
    value = payload.get(key)
    if isinstance(value, Mapping):
        return value
    findings.append(Finding("INVALID", key, f"{key} must be an object"))
    return {}


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def check_envelope(payload: Mapping[str, Any]) -> list[Finding]:
    """Check identity fields: version, metric, kind, unit, repository, branch, cohort."""
    findings: list[Finding] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        findings.append(Finding("INVALID", "schema_version", f"must be {SCHEMA_VERSION}"))
    for key in ("metric", "branch", "cohort"):
        if not _text(payload.get(key)):
            findings.append(Finding("INVALID", key, f"{key} must be a non-empty string"))
    if payload.get("kind") not in KINDS:
        findings.append(Finding("INVALID", "kind", f"must be one of {', '.join(KINDS)}"))
    if payload.get("unit") not in UNITS:
        findings.append(Finding("INVALID", "unit", f"must be one of {', '.join(UNITS)}"))
    repository = payload.get("repository")
    if not isinstance(repository, str) or not _REPO_RE.match(repository):
        findings.append(Finding("INVALID", "repository", "must be owner/name"))
    return findings


def check_revision(payload: Mapping[str, Any]) -> list[Finding]:
    """Require a 40-hex source revision when the metric depends on source state."""
    findings: list[Finding] = []
    revision = payload.get("source_revision")
    code_dependent = payload.get("code_dependent")
    if not isinstance(code_dependent, bool):
        findings.append(Finding("INVALID", "code_dependent", "must be true or false"))
    if revision is not None and not (isinstance(revision, str) and _SHA_RE.match(revision)):
        findings.append(Finding("INVALID", "source_revision", "must be a 40-hex SHA or null"))
    if code_dependent is True and revision is None:
        findings.append(Finding("INVALID", "source_revision", "required when code_dependent"))
    return findings


def check_pagination(payload: Mapping[str, Any]) -> list[Finding]:
    """BLOCK on incomplete retrieval, and require the failure to be named."""
    findings: list[Finding] = []
    page = section(payload, "pagination", findings)
    if findings:
        return findings
    if not isinstance(page.get("complete"), bool):
        return [Finding("INVALID", "pagination.complete", "must be true or false")]
    if not is_count(page.get("pages_fetched")):
        findings.append(Finding("INVALID", "pagination.pages_fetched", "must be a count"))
    if page["complete"]:
        return findings
    findings.append(Finding("BLOCKED", "pagination", "retrieval is incomplete"))
    failed_page, failed_record = page.get("failed_page"), page.get("failed_record")
    if not ((is_count(failed_page) and failed_page >= 1) or _text(failed_record)):
        findings.append(
            Finding(
                "INVALID", "pagination", "incomplete run must name failed_page or failed_record"
            )
        )
    if not _text(page.get("failure")):
        findings.append(Finding("INVALID", "pagination.failure", "incomplete run must say why"))
    return findings


def _window_findings(
    kind: object, window: Mapping[str, Any]
) -> tuple[list[Finding], datetime | None]:
    findings: list[Finding] = []
    if window.get("timezone") != "UTC":
        findings.append(Finding("INVALID", "window.timezone", "must be UTC"))
    end = parse_utc(window.get("end"))
    if end is None:
        findings.append(Finding("INVALID", "window.end", "must be a UTC ISO-8601 timestamp"))
    raw_start = window.get("start")
    start = parse_utc(raw_start)
    if start is None and (kind in WINDOWED_KINDS or raw_start is not None):
        findings.append(Finding("INVALID", "window.start", "must be a UTC ISO-8601 timestamp"))
    if start is not None and end is not None and start >= end:
        findings.append(Finding("INVALID", "window", "start must be before end"))
    return findings, end


def check_time(payload: Mapping[str, Any], *, now: datetime, max_age: timedelta) -> list[Finding]:
    """Check retrieved_at, the event window, freshness, and the boundary timing race."""
    findings: list[Finding] = []
    window = section(payload, "window", findings)
    window_findings, end = _window_findings(payload.get("kind"), window)
    findings.extend(window_findings)
    retrieved = parse_utc(payload.get("retrieved_at"))
    if retrieved is None:
        findings.append(Finding("INVALID", "retrieved_at", "must be a UTC ISO-8601 timestamp"))
        return findings
    if retrieved > now:
        findings.append(Finding("INVALID", "retrieved_at", "is in the future"))
    elif now - retrieved > max_age:
        findings.append(Finding("BLOCKED", "retrieved_at", f"older than {max_age}; stale"))
    if end is None:
        return findings
    if end > retrieved:
        findings.append(Finding("INVALID", "window.end", "is after retrieved_at"))
    elif payload.get("kind") in WINDOWED_KINDS and retrieved - end < TIMING_RACE_MARGIN:
        findings.append(Finding("WARN", "window.end", "within 60s of retrieval; count may race"))
    return findings


def _counts_values(counts: Mapping[str, Any]) -> list[Finding]:
    bad = [key for key in COUNT_KEYS if not is_count(counts.get(key))]
    return [Finding("INVALID", f"counts.{key}", "must be a non-negative integer") for key in bad]


def check_counts(payload: Mapping[str, Any]) -> list[Finding]:
    """Check the count identity ``raw == derived + null + duplicates + excluded``."""
    findings: list[Finding] = []
    counts = section(payload, "counts", findings)
    if findings:
        return findings
    findings.extend(_counts_values(counts))
    if findings:
        return findings
    parts = sum(counts[key] for key in COUNT_KEYS if key != "raw")
    if counts["raw"] != parts:
        findings.append(
            Finding(
                "INVALID",
                "counts",
                f"raw {counts['raw']} != derived+null+duplicates+excluded {parts}",
            )
        )
    for key, note in (("null", "null or unknown"), ("duplicates", "duplicate")):
        if counts[key]:
            findings.append(Finding("WARN", f"counts.{key}", f"{counts[key]} {note} records"))
    if counts["raw"] == 0:
        findings.append(
            Finding("WARN", "counts.raw", "empty result; confirm it is not a query error")
        )
    return findings


def _number_values(payload: Mapping[str, Any]) -> list[Finding]:
    findings = []
    for key in ("numerator", "denominator"):
        value = payload.get(key)
        if value is not None and not is_count(value):
            findings.append(Finding("INVALID", key, "must be a non-negative integer or null"))
    return findings


def _rate_findings(numerator: int | None, denominator: int | None) -> list[Finding]:
    if denominator is None:
        return [Finding("INVALID", "denominator", "required for same_cohort_rate")]
    if numerator is not None and numerator > denominator:
        return [Finding("INVALID", "numerator", "exceeds denominator")]
    if denominator == 0:
        return [Finding("WARN", "denominator", "empty cohort; rate is undefined")]
    return []


def _tie_findings(payload: Mapping[str, Any], derived: int) -> list[Finding]:
    kind = payload.get("kind")
    numerator, denominator = payload.get("numerator"), payload.get("denominator")
    findings: list[Finding] = []
    if kind == "same_cohort_rate":
        findings.extend(_rate_findings(numerator, denominator))
        tied, field = denominator, "denominator"
    else:
        tied, field = numerator, "numerator"
    if kind != "reconstructed_estimate" and tied is not None and tied != derived:
        findings.append(Finding("INVALID", field, f"{tied} != counts.derived {derived}"))
    return findings


def check_numbers(payload: Mapping[str, Any]) -> list[Finding]:
    """Check numerator and denominator against the kind, the counts, and the declared status."""
    findings = _number_values(payload)
    if findings:
        return findings
    counts = payload.get("counts")
    derived = counts.get("derived") if isinstance(counts, Mapping) else None
    if is_count(derived):
        findings.extend(_tie_findings(payload, derived))
    numeric = payload.get("numerator") is not None or payload.get("denominator") is not None
    if payload.get("status") in ("BLOCKED", "INVALID") and numeric:
        findings.append(Finding("INVALID", "numerator", "numbers must be null on a failed run"))
    if payload.get("status") in ("PASS", "WARN") and payload.get("numerator") is None:
        findings.append(
            Finding("INVALID", "numerator", "required unless status is BLOCKED/INVALID")
        )
    return findings


def check_declaration(payload: Mapping[str, Any]) -> list[Finding]:
    """Check status, limitations, excluded_data, query, and the provisional kind."""
    findings: list[Finding] = []
    status = payload.get("status")
    if status not in STATUSES:
        findings.append(Finding("INVALID", "status", f"must be one of {', '.join(STATUSES)}"))
    for key in ("limitations", "excluded_data"):
        value = payload.get(key)
        if not (isinstance(value, list) and all(_text(item) for item in value)):
            findings.append(Finding("INVALID", key, f"{key} must be a list of strings"))
    query = payload.get("query")
    if not (isinstance(query, Mapping) and isinstance(query.get("parameters"), Mapping)):
        findings.append(Finding("INVALID", "query", "must be an object with parameters"))
    if status in ("WARN", "BLOCKED", "INVALID") and not payload.get("limitations"):
        findings.append(Finding("INVALID", "limitations", f"required when status is {status}"))
    if payload.get("kind") == "reconstructed_estimate":
        findings.append(Finding("WARN", "kind", "reconstructed estimate is provisional"))
    return findings

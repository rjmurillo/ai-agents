#!/usr/bin/env python3
"""Defect lineage record: schema checks, derived delay, and recheck (issue #5638).

A lineage record keeps the history of one reviewed chain: where a change was
introduced, who detected a problem and when, which follow-up changed it, and
what the live default branch shows now. A later fix makes the original defect
vanish from the current tree. The record keeps the chain and states the live
status separately, so analysis never reports a fixed finding as live and never
drops the evidence of a review race.

This module is pure. It reads and writes no files and runs no commands. The
CLI in ``defect_lineage.py`` supplies the live-SHA probe.

Record fields (schema_version 1, all timestamps UTC ``YYYY-MM-DDTHH:MM:SSZ``):

    id, repository, default_branch, claim
    supports        non-empty subset of defect, review_race, process_gap,
                    observation. ``observation`` stands alone.
    introduction    {pr, url, commit, merged_at}
    detection       {source, url, at}
    follow_up       null or {kind, pr, url, merged_at, commit}. ``kind`` is
                    defect_repair, planned_work, or cleanup.
    status          CURRENT, FIXED, REVERTED, SUPERSEDED, or UNVERIFIED. It
                    states whether ``claim`` still holds at the live SHA.
    status_history  append-only list of {status, live_sha, checked_at, basis}
    recheck         {description, command, path, pattern, live_when}. The claim
                    holds when ``pattern`` is present (or absent) in ``path``.
                    ``command`` is display text for a human. It is never run.
    limitations     non-empty list of what the record does not prove
    optional        detection_delay_seconds, reverted_by, superseded_by

Status rules: FIXED needs a merged defect_repair follow-up. REVERTED needs
``reverted_by``. SUPERSEDED needs ``superseded_by``. An observation-only record
claims no defect, so it can never be FIXED.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, cast

SCHEMA_VERSION = 1
STATUSES = ("CURRENT", "FIXED", "REVERTED", "SUPERSEDED", "UNVERIFIED")
SUPPORTS = ("defect", "review_race", "process_gap", "observation")
FOLLOW_UP_KINDS = ("defect_repair", "planned_work", "cleanup")
LIVE_WHEN = ("present", "absent")
PROBE_STATES = ("present", "absent", "unavailable")
TOP_LEVEL_KEYS = (
    "schema_version",
    "id",
    "repository",
    "default_branch",
    "claim",
    "supports",
    "introduction",
    "detection",
    "follow_up",
    "status",
    "status_history",
    "recheck",
    "limitations",
)

_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_COMMIT = re.compile(r"^[0-9a-f]{7,40}$")
_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class LineageError(Exception):
    """A record is invalid or a recheck cannot be applied. Carries each problem."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class Probe:
    """One observation of the recheck pattern at a live SHA."""

    state: str
    live_sha: str
    checked_at: str
    detail: str


def parse_timestamp(value: object) -> datetime | None:
    """Parse a strict seconds-resolution UTC timestamp, or return None."""
    if not isinstance(value, str) or not _TIMESTAMP.match(value):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _text(obj: Mapping[str, Any], key: str, where: str, problems: list[str]) -> str | None:
    value = obj.get(key)
    if isinstance(value, str) and value.strip():
        return value
    problems.append(f"{where}.{key} must be a non-empty string")
    return None


def _timestamp(
    obj: Mapping[str, Any], key: str, where: str, problems: list[str]
) -> datetime | None:
    parsed = parse_timestamp(obj.get(key))
    if parsed is None:
        problems.append(f"{where}.{key} must be a UTC timestamp like 2026-09-06T22:23:33Z")
    return parsed


def _url(obj: Mapping[str, Any], where: str, repository: str, problems: list[str]) -> None:
    url = _text(obj, "url", where, problems)
    if url is not None and not url.startswith(f"https://github.com/{repository}/"):
        problems.append(f"{where}.url must start with https://github.com/{repository}/")


def _pr_number(obj: Mapping[str, Any], where: str, problems: list[str]) -> None:
    pr = obj.get("pr")
    if isinstance(pr, bool) or not isinstance(pr, int) or pr < 1:
        problems.append(f"{where}.pr must be a positive integer")


def _commit(obj: Mapping[str, Any], where: str, problems: list[str]) -> None:
    value = obj.get("commit")
    if not isinstance(value, str) or not _COMMIT.match(value):
        problems.append(f"{where}.commit must be 7 to 40 lowercase hex characters")


def _section(record: Mapping[str, Any], key: str, problems: list[str]) -> Mapping[str, Any] | None:
    value = record.get(key)
    if isinstance(value, dict):
        return value
    problems.append(f"{key} must be an object")
    return None


def _check_header(record: Mapping[str, Any], problems: list[str]) -> str:
    missing = [key for key in TOP_LEVEL_KEYS if key not in record]
    if missing:
        problems.append("missing keys: " + ", ".join(missing))
    if record.get("schema_version") != SCHEMA_VERSION:
        problems.append(f"schema_version must be {SCHEMA_VERSION}")
    for key in ("id", "default_branch", "claim"):
        if key in record:
            _text(record, key, "record", problems)
    repository = record.get("repository")
    if isinstance(repository, str) and _REPOSITORY.match(repository):
        return repository
    problems.append("repository must look like owner/name")
    return "?/?"


def _check_supports(record: Mapping[str, Any], problems: list[str]) -> list[str]:
    supports = record.get("supports")
    if not isinstance(supports, list) or not supports:
        problems.append("supports must be a non-empty list")
        return []
    unknown = [item for item in supports if item not in SUPPORTS]
    if unknown:
        problems.append(f"supports has unknown values: {unknown}")
    if "observation" in supports and len(supports) > 1:
        problems.append("supports: observation cannot combine with a defect-class value")
    return [item for item in supports if item in SUPPORTS]


def _check_introduction(
    record: Mapping[str, Any], repository: str, problems: list[str]
) -> datetime | None:
    section = _section(record, "introduction", problems)
    if section is None:
        return None
    _pr_number(section, "introduction", problems)
    _url(section, "introduction", repository, problems)
    _commit(section, "introduction", problems)
    return _timestamp(section, "merged_at", "introduction", problems)


def _check_detection(
    record: Mapping[str, Any], repository: str, problems: list[str]
) -> datetime | None:
    section = _section(record, "detection", problems)
    if section is None:
        return None
    _text(section, "source", "detection", problems)
    _url(section, "detection", repository, problems)
    return _timestamp(section, "at", "detection", problems)


def _check_follow_up(
    record: Mapping[str, Any], repository: str, problems: list[str]
) -> tuple[str | None, datetime | None]:
    section = record.get("follow_up")
    if section is None:
        return None, None
    if not isinstance(section, dict):
        problems.append("follow_up must be null or an object")
        return None, None
    kind = section.get("kind")
    if kind not in FOLLOW_UP_KINDS:
        problems.append(f"follow_up.kind must be one of {FOLLOW_UP_KINDS}")
        kind = None
    _pr_number(section, "follow_up", problems)
    _url(section, "follow_up", repository, problems)
    if section.get("merged_at") is None:
        return kind, None
    _commit(section, "follow_up", problems)
    return kind, _timestamp(section, "merged_at", "follow_up", problems)


def _check_pointer(
    record: Mapping[str, Any], key: str, repository: str, problems: list[str]
) -> None:
    section = record.get(key)
    if section is None:
        return
    if not isinstance(section, dict):
        problems.append(f"{key} must be null or an object")
        return
    _pr_number(section, key, problems)
    _url(section, key, repository, problems)


def _check_latency(
    record: Mapping[str, Any],
    supports: list[str],
    merged: datetime | None,
    detected: datetime | None,
    problems: list[str],
) -> None:
    if merged is None or detected is None:
        return
    delta = int((detected - merged).total_seconds())
    if "review_race" in supports and delta <= 0:
        problems.append(
            "supports review_race but detection is not after the introduction merge "
            f"(delta {delta} s)"
        )
    stored = record.get("detection_delay_seconds")
    if stored is not None and stored != delta:
        problems.append(f"detection_delay_seconds is {stored!r} but the timestamps give {delta}")


def _check_ordering(
    kind: str | None,
    merged: datetime | None,
    detected: datetime | None,
    repaired: datetime | None,
    problems: list[str],
) -> None:
    if repaired is None:
        return
    if merged is not None and repaired < merged:
        problems.append("follow_up merged before the introduction merged")
    if kind == "defect_repair" and detected is not None and repaired < detected:
        problems.append("follow_up repaired a defect before it was detected")


def _check_status_requirements(
    record: Mapping[str, Any],
    supports: list[str],
    kind: str | None,
    repaired: datetime | None,
    problems: list[str],
) -> None:
    status = record.get("status")
    if status not in STATUSES:
        problems.append(f"status must be one of {STATUSES}")
        return
    if status == "FIXED" and (kind != "defect_repair" or repaired is None):
        problems.append("status FIXED needs a merged defect_repair follow_up")
    if status == "FIXED" and supports == ["observation"]:
        problems.append("an observation-only record claims no defect, so it cannot be FIXED")
    if status == "REVERTED" and not isinstance(record.get("reverted_by"), dict):
        problems.append("status REVERTED needs reverted_by")
    if status == "SUPERSEDED" and not isinstance(record.get("superseded_by"), dict):
        problems.append("status SUPERSEDED needs superseded_by")
    if supports == ["observation"] and kind == "defect_repair":
        problems.append("an observation-only record cannot have a defect_repair follow_up")


def _history_entry(entry: object, index: int, problems: list[str]) -> datetime | None:
    where = f"status_history[{index}]"
    if not isinstance(entry, dict):
        problems.append(f"{where} must be an object")
        return None
    if entry.get("status") not in STATUSES:
        problems.append(f"{where}.status must be one of {STATUSES}")
    live_sha = entry.get("live_sha")
    if not isinstance(live_sha, str) or not _FULL_SHA.match(live_sha):
        problems.append(f"{where}.live_sha must be a 40-character lowercase SHA")
    _text(entry, "basis", where, problems)
    return _timestamp(entry, "checked_at", where, problems)


def _check_history(
    record: Mapping[str, Any], repaired: datetime | None, problems: list[str]
) -> None:
    history = record.get("status_history")
    if not isinstance(history, list) or not history:
        problems.append("status_history must be a non-empty list")
        return
    times = [_history_entry(entry, index, problems) for index, entry in enumerate(history)]
    known = [time for time in times if time is not None]
    if any(later <= earlier for earlier, later in zip(known, known[1:], strict=False)):
        problems.append("status_history checked_at values must strictly increase")
    last = history[-1]
    if isinstance(last, dict) and last.get("status") != record.get("status"):
        problems.append("status does not match the last status_history entry")
    _check_fixed_entries(history, times, repaired, problems)


def _check_fixed_entries(
    history: list[Any],
    times: list[datetime | None],
    repaired: datetime | None,
    problems: list[str],
) -> None:
    if repaired is None:
        return
    for index, entry in enumerate(history):
        when = times[index]
        if isinstance(entry, dict) and entry.get("status") == "FIXED":
            if when is not None and when < repaired:
                problems.append(f"status_history[{index}] is FIXED before the follow_up merged")


def _check_recheck(record: Mapping[str, Any], problems: list[str]) -> None:
    section = _section(record, "recheck", problems)
    if section is None:
        return
    for key in ("description", "command", "path", "pattern"):
        _text(section, key, "recheck", problems)
    path = section.get("path")
    if isinstance(path, str) and (path.startswith("/") or ".." in path.split("/")):
        problems.append("recheck.path must be repository-relative without '..'")
    pattern = section.get("pattern")
    if isinstance(pattern, str):
        try:
            re.compile(pattern)
        except re.error as err:
            problems.append(f"recheck.pattern is not a valid regex: {err}")
    if section.get("live_when") not in LIVE_WHEN:
        problems.append(f"recheck.live_when must be one of {LIVE_WHEN}")


def _check_limitations(record: Mapping[str, Any], problems: list[str]) -> None:
    items = record.get("limitations")
    if not isinstance(items, list) or not items:
        problems.append("limitations must be a non-empty list")
    elif not all(isinstance(item, str) and item.strip() for item in items):
        problems.append("limitations entries must be non-empty strings")


def validate_record(record: object) -> list[str]:
    """Return every problem in a record. An empty list means valid."""
    if not isinstance(record, dict):
        return ["record must be a JSON object"]
    problems: list[str] = []
    repository = _check_header(record, problems)
    supports = _check_supports(record, problems)
    merged = _check_introduction(record, repository, problems)
    detected = _check_detection(record, repository, problems)
    kind, repaired = _check_follow_up(record, repository, problems)
    _check_pointer(record, "reverted_by", repository, problems)
    _check_pointer(record, "superseded_by", repository, problems)
    _check_latency(record, supports, merged, detected, problems)
    _check_ordering(kind, merged, detected, repaired, problems)
    _check_status_requirements(record, supports, kind, repaired, problems)
    _check_history(record, repaired, problems)
    _check_recheck(record, problems)
    _check_limitations(record, problems)
    return problems


def require_valid(record: object) -> dict[str, Any]:
    """Return the record when valid, else raise LineageError with every problem."""
    problems = validate_record(record)
    if problems:
        raise LineageError(problems)
    return cast(dict[str, Any], record)


def _required_time(value: object) -> datetime:
    parsed = parse_timestamp(value)
    if parsed is None:
        raise LineageError([f"not a UTC timestamp: {value!r}"])
    return parsed


def detection_delay_seconds(record: Mapping[str, Any]) -> int:
    """Seconds from the introduction merge to detection. Negative means pre-merge."""
    merged = _required_time(record["introduction"]["merged_at"])
    detected = _required_time(record["detection"]["at"])
    return int((detected - merged).total_seconds())


def repair_delay_seconds(record: Mapping[str, Any]) -> int | None:
    """Seconds from detection to the follow-up merge, or None without a merged one."""
    follow_up = record.get("follow_up")
    if not follow_up or follow_up.get("merged_at") is None:
        return None
    detected = _required_time(record["detection"]["at"])
    repaired = _required_time(follow_up["merged_at"])
    return int((repaired - detected).total_seconds())


def _has_merged_repair(record: Mapping[str, Any]) -> bool:
    follow_up = record.get("follow_up") or {}
    return follow_up.get("kind") == "defect_repair" and follow_up.get("merged_at") is not None


def classify_probe(record: Mapping[str, Any], probe: Probe) -> tuple[str, str]:
    """Map a probe to (status, basis) for the record's claim. Never guesses."""
    if probe.state == "unavailable":
        return "UNVERIFIED", f"recheck unavailable: {probe.detail}"
    holds = probe.state == record["recheck"]["live_when"]
    if holds and isinstance(record.get("reverted_by"), dict):
        return "REVERTED", f"claim holds again after the revert: {probe.detail}"
    if holds:
        return "CURRENT", f"claim holds: {probe.detail}"
    if isinstance(record.get("superseded_by"), dict):
        return "SUPERSEDED", f"claim no longer holds, superseded: {probe.detail}"
    if _has_merged_repair(record) and record["supports"] != ["observation"]:
        return "FIXED", f"claim no longer holds after the repair: {probe.detail}"
    return (
        "UNVERIFIED",
        "claim no longer holds, but no merged repair or superseding change is recorded: "
        f"{probe.detail}",
    )


def apply_recheck(record: Mapping[str, Any], probe: Probe) -> dict[str, Any]:
    """Return a copy with the probe applied. The chain and old history stay intact."""
    problems: list[str] = []
    if probe.state not in PROBE_STATES:
        problems.append(f"probe state must be one of {PROBE_STATES}")
    if not _FULL_SHA.match(probe.live_sha):
        problems.append("probe live_sha must be a 40-character lowercase SHA")
    if parse_timestamp(probe.checked_at) is None:
        problems.append("probe checked_at must be a UTC timestamp")
    if problems:
        raise LineageError(problems)
    current = require_valid(copy.deepcopy(dict(record)))
    last = _required_time(current["status_history"][-1]["checked_at"])
    if _required_time(probe.checked_at) <= last:
        raise LineageError(["probe checked_at must be later than the last status_history entry"])
    status, basis = classify_probe(current, probe)
    current["status"] = status
    current["status_history"].append(
        {
            "status": status,
            "live_sha": probe.live_sha,
            "checked_at": probe.checked_at,
            "basis": basis,
        }
    )
    return require_valid(current)

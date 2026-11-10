"""Scope code-scanning alerts to a diff and reduce them to rule id, path, and line.

Used by ``get_pr_code_scanning_alerts.py``. Pure functions over already-fetched
data; no I/O. Rules from the ADR-041 amendment 2026-11-09
(``.project-toolkit/analysis/adr-041-review-caller-rules.md``):

* Untrusted data: an alert passes on as a validated rule id, a path the diff
  touches, and a line. A rule id that fails ``^[A-Za-z0-9/_.-]{1,100}$`` is
  counted and dropped. No message or rule name is passed.
* Scoped: an alert is attached when any location (primary, related, or
  code-flow step) is in a file the diff touches. Others are counted by file.
* Loud: an open alert from the current analysis that has no SARIF result cannot
  be scoped, so the read is SKIPPED instead of silently narrowed.
"""

from __future__ import annotations

from typing import Any

from code_scanning_sarif import (
    first_location_in_diff,
    is_valid_rule_id,
    normalize_repo_path,
    sarif_result_locations,
)
from code_scanning_transport import SkipError

MAX_ATTACHED = 200
MAX_OTHER_FILES = 50


def _alert_primary_path(alert: dict[str, Any]) -> str | None:
    instance = alert.get("most_recent_instance")
    location = instance.get("location") if isinstance(instance, dict) else None
    return normalize_repo_path(location.get("path")) if isinstance(location, dict) else None


def _alert_commit_sha(alert: dict[str, Any]) -> str | None:
    instance = alert.get("most_recent_instance")
    sha = instance.get("commit_sha") if isinstance(instance, dict) else None
    return sha if isinstance(sha, str) else None


def _alert_rule_id(alert: dict[str, Any]) -> object:
    rule = alert.get("rule")
    return rule.get("id") if isinstance(rule, dict) else None


def _alert_number(alert: dict[str, Any]) -> int | None:
    number = alert.get("number")
    return number if isinstance(number, int) and not isinstance(number, bool) else None


def scope_alerts(
    alerts: list[Any],
    sarif_by_number: dict[int, Any],
    current_merge_shas: frozenset[str],
    changed_files: frozenset[str],
) -> dict[str, Any]:
    """Reduce open alerts to attached ``{rule_id, path, line}`` plus counts.

    Raises:
        SkipError: an alert has no number, or an alert from the current analysis
            has no SARIF result, so "any location" scoping cannot be completed.
    """
    attached: dict[tuple[str, str, int], dict[str, Any]] = {}
    other_by_file: dict[str, int] = {}
    counts = {"open": 0, "invalid_rule_id": 0, "not_in_current_analysis": 0}
    for alert in alerts:
        if not isinstance(alert, dict) or _alert_number(alert) is None:
            raise SkipError("alert record had an unexpected shape")
        counts["open"] += 1
        if _alert_commit_sha(alert) not in current_merge_shas:
            counts["not_in_current_analysis"] += 1
            continue
        number = _alert_number(alert)
        result = sarif_by_number.get(number) if number is not None else None
        if result is None:
            raise SkipError("an open alert is missing from the analysis SARIF")
        hit = first_location_in_diff(sarif_result_locations(result), changed_files)
        if hit is None:
            key = _alert_primary_path(alert) or "(unparseable path)"
            other_by_file[key] = other_by_file.get(key, 0) + 1
        elif not is_valid_rule_id(_alert_rule_id(alert)):
            counts["invalid_rule_id"] += 1
        else:
            rule_id = str(_alert_rule_id(alert))
            attached[(rule_id, hit[0], hit[1])] = {
                "rule_id": rule_id,
                "path": hit[0],
                "line": hit[1],
            }
    return _scoped_result(attached, other_by_file, counts)


def _scoped_result(
    attached: dict[tuple[str, str, int], dict[str, Any]],
    other_by_file: dict[str, int],
    counts: dict[str, int],
) -> dict[str, Any]:
    ordered = [attached[key] for key in sorted(attached)]
    other_sorted = sorted(other_by_file.items(), key=lambda item: (-item[1], item[0]))
    return {
        "alerts": ordered[:MAX_ATTACHED],
        "attached_omitted": max(0, len(ordered) - MAX_ATTACHED),
        "other_by_file": dict(other_sorted[:MAX_OTHER_FILES]),
        "other_files_omitted": max(0, len(other_sorted) - MAX_OTHER_FILES),
        "other_total": sum(other_by_file.values()),
        "counts": counts,
    }

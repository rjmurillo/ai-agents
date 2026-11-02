# mypy: disable-error-code="type-arg", follow-imports=skip
"""Shared logic for grouping and evaluating GitHub status check rollups.

This module encodes the required-check semantics used by both get_pr_checks.py
and test_pr_merge_ready.py, preventing drift between the two scripts.

The key insight: a check name's required status is the OR of all isRequired
flags across all row types (CheckRun and StatusContext) for that name.
This is documented in issue #2325 and PR #1887 retrospective.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections import defaultdict
from datetime import datetime, timezone

# A GitHub Actions check-run details URL carries the workflow run identity:
#   https://github.com/OWNER/REPO/actions/runs/<runId>/job/<jobId>
# Two jobs of the SAME run can publish the same check name on purpose (a
# conditional matrix leg, or two jobs deliberately sharing a name so branch
# protection sees one required context). Those are siblings, not supersessions.
_RUN_ID_PATTERN = re.compile(r"/actions/runs/(\d+)")


def extract_workflow_run_id(details_url: str | None) -> str | None:
    """Return the Actions workflow run id embedded in a check details URL.

    Returns None when the URL is absent or is not an Actions run URL (a
    StatusContext target URL, or a third-party check run). Callers must treat
    None as "provenance unknown" and must not group unknown rows together.
    """
    if not details_url:
        return None
    match = _RUN_ID_PATTERN.search(details_url)
    return match.group(1) if match else None


def extract_workflow_run_number(details_url: str | None) -> int | None:
    """Return the numeric Actions workflow run id from a details URL."""
    run_id = extract_workflow_run_id(details_url)
    return int(run_id) if run_id is not None else None


def partition_rows_by_run(
    rows: list[dict],
    url_key: str,
    run_id_key: str | None = None,
    run_attempt_key: str | None = None,
) -> list[list[dict]]:
    """Split same-named rows into groups that share one workflow attempt.

    GraphQL exposes ``runAttempt`` for Actions checks. A rerun keeps the same
    workflow run id, so grouping on the id alone conflates stale failures with
    the latest attempt. Rows without workflow identity remain singletons.

    Refs issue #4499: two jobs of one run named "Run Python Tests" (one
    FAILURE, one SKIPPED) were collapsed to the SKIPPED row, so the failure
    vanished and CIPassing reported true against a red PR.
    """
    by_run: dict[tuple[str, int], list[dict]] = {}
    order: list[tuple[str, int]] = []
    singletons: list[list[dict]] = []

    for row in rows:
        run_id_value = row.get(run_id_key) if run_id_key else None
        run_id = (
            str(run_id_value)
            if run_id_value is not None
            else extract_workflow_run_id(row.get(url_key))
        )
        if run_id is None:
            singletons.append([row])
            continue
        attempt_value = row.get(run_attempt_key) if run_attempt_key else None
        attempt = int(attempt_value) if attempt_value is not None else 1
        run_key = (run_id, attempt)
        if run_key not in by_run:
            by_run[run_key] = []
            order.append(run_key)
        by_run[run_key].append(row)

    return [by_run[run_key] for run_key in order] + singletons


def current_run_keys(
    runs: list[tuple[tuple[int, int], str | None]],
) -> set[tuple[int, int]]:
    """Return the newest (run id, attempt) key of each triggering event.

    One head SHA can carry a ``pull_request`` run and a ``push`` run of the
    same workflow. The ruleset evaluates both, so a newer run of one event
    must not supersede the other event's result. Within one event the newest
    run still wins, so a rerun replaces the stale failure it retried. Runs
    with no known event share one bucket, which keeps the old behavior for
    callers that cannot report an event.
    """
    latest: dict[str | None, tuple[int, int]] = {}
    for key, event in runs:
        if event not in latest or key > latest[event]:
            latest[event] = key
    return set(latest.values())


def group_checks_by_name(
    checks: list[dict],
) -> tuple[dict[str, dict], dict[str, bool], dict[str, list[str]]]:
    """Group checks by name, tracking required status and type.

    Returns (checks_by_name, is_required_by_name, check_types_by_name) where:
    - checks_by_name: maps check name to the normalized check dict
    - is_required_by_name: maps check name to OR of all isRequired values
    - check_types_by_name: maps check name to list of types present (for dedupe)

    The isRequired flag ORs across rows: if ANY row for a name has
    isRequired=true, the name is treated as required. This matches the
    test_pr_merge_ready.py _group_contexts_by_name logic.
    """
    checks_by_name: dict[str, dict] = {}
    is_required_by_name: dict[str, bool] = {}
    check_types_by_name: dict[str, list[str]] = defaultdict(list)

    for check in checks:
        name = check.get("Name", "")
        typename = check.get("Type", "")

        # Track type for dedupe ordering (CheckRun preferred over StatusContext).
        if typename and typename not in check_types_by_name[name]:
            check_types_by_name[name].append(typename)

        # OR the required flag: if any row for this name is required, the name
        # is treated as required.
        is_required_by_name[name] = is_required_by_name.get(name, False) or bool(
            check.get("IsRequired")
        )

        # Keep the first check of each name (caller has already deduplicated by
        # passing the winner from dedupe_checks).
        if name not in checks_by_name:
            checks_by_name[name] = check

    return checks_by_name, is_required_by_name, check_types_by_name


def extract_required_check_lists(
    checks: list[dict],
    is_required_by_name: dict[str, bool],
) -> tuple[list[str], list[str]]:
    """Extract pending and failed required check names.

    Returns (pending_required_names, failed_required_names) for structured
    output in JSON so downstream agents can distinguish pending vs. failed
    required checks.
    """
    pending_required = []
    failed_required = []

    for check in checks:
        name = check.get("Name", "")
        is_required = is_required_by_name.get(name, False)

        if not is_required:
            continue

        if check.get("IsFailing"):
            failed_required.append(name)
        # A check whose dedupe winner is passing (SUCCESS, NEUTRAL, or SKIPPED)
        # is not a pending required check, even when dedupe_checks ORed
        # IsPending=true onto the winner from a stale sibling row. The IsPending
        # OR is retained on the row for wait polling, but PendingRequiredChecks
        # must classify a completed-passing required check consistently with
        # test_pr_merge_ready.py, which treats it as non-blocking. Refs issue #2614:
        # a SKIPPED required check with a PENDING sibling was reported as pending.
        if check.get("IsPending") and not check.get("IsPassing"):
            pending_required.append(name)

    return pending_required, failed_required


def fetch_ruleset_required_contexts(
    owner: str, repo: str, branch: str = "main"
) -> list[str] | None:
    """Return the required status check context names from the branch ruleset.
    Uses ``gh api repos/{owner}/{repo}/rules/branches/{branch}`` (not the
    legacy ``/branches/{branch}/protection`` endpoint, which returns 404 for
    repos that use rulesets instead of branch protection).

    Returns a sorted list of context strings, or None if the API call fails
    (callers should treat None as unknown rather than empty). Refs issue #4359.
    """
    endpoint = f"repos/{owner}/{repo}/rules/branches/{branch}?per_page=100"
    result = subprocess.run(
        ["gh", "api", "--paginate", "--slurp", endpoint],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    if result.returncode != 0:
        return None
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, list):
        return None
    rules = (
        [rule for page in payload for rule in page]
        if payload and all(isinstance(page, list) for page in payload)
        else payload
    )

    contexts: list[str] = []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        if rule.get("type") != "required_status_checks":
            continue
        params = rule.get("parameters") or {}
        for check_entry in params.get("required_status_checks") or []:
            if isinstance(check_entry, dict):
                ctx = check_entry.get("context")
            else:
                ctx = None
            if ctx and isinstance(ctx, str):
                contexts.append(ctx)
    return sorted(set(contexts))


def find_missing_required(
    ruleset_contexts: list[str],
    reported_check_names: set[str],
) -> list[str]:
    """Return context names required by the ruleset but absent from the rollup.

    A context that the ruleset requires but that never triggered any check run
    is invisible to isRequired-based tooling (because isRequired is only set on
    checks that did report). This function bridges that gap. Refs issue #4359.
    """
    return sorted(c for c in ruleset_contexts if c not in reported_check_names)


# A required check can be absent from the rollup because its workflow has not
# created it yet (an aggregate job that starts after its split jobs finish
# takes 10 to 35 minutes), not because the event was dropped. Inside this
# window after the head commit, absence is "queued"; past it, "absent".
MISSING_GRACE_SECONDS = 2700

# Largest head-commit date ahead of the local clock that still counts as skew.
MAX_FUTURE_SKEW_SECONDS = 300


def head_commit_age_seconds(
    committed_at: str | None,
    now: datetime | None = None,
) -> float | None:
    """Return seconds since the head commit date, or None when unknown.

    ``committed_at`` is the ISO 8601 ``committedDate`` GraphQL returns. A
    missing, malformed, or naive timestamp yields None so callers fail closed.
    A date in the future (clock skew) clamps to zero.
    """
    if not committed_at or not isinstance(committed_at, str):
        return None
    try:
        parsed = datetime.fromisoformat(committed_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    current = now if now is not None else datetime.now(timezone.utc)
    return max(0.0, (current - parsed).total_seconds())


def _clock_age_seconds(
    timestamp: str | None,
    now: datetime | None = None,
) -> float | None:
    """Return signed seconds since ``timestamp``, or None when unparseable.

    Unlike :func:`head_commit_age_seconds` a future date stays negative, so a
    caller can tell clock skew from a forged date.
    """
    if not timestamp or not isinstance(timestamp, str):
        return None
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    current = now if now is not None else datetime.now(timezone.utc)
    return (current - parsed).total_seconds()


def missing_checks_queued(
    committed_at: str | None,
    grace_seconds: int = MISSING_GRACE_SECONDS,
    now: datetime | None = None,
    pushed_at: str | None = None,
) -> bool:
    """Return True when absent required checks may still be queued.

    True only when the head commit age is known and under ``grace_seconds``.
    Unknown age or a non-positive grace returns False, which keeps the
    pre-existing behavior of reporting the checks as never reported.

    ``committedDate`` is author-controlled, so it cannot open the window alone.
    A date more than ``MAX_FUTURE_SKEW_SECONDS`` ahead of the clock is forged
    or badly skewed: the clamp to zero in :func:`head_commit_age_seconds` would
    keep the window open on every poll, so it closes the window instead.
    ``pushed_at`` is an author-independent push time (for example the head ref
    update time). When supplied it caps the window the same way: the window is
    open only while both the commit and the push are inside ``grace_seconds``.
    """
    if grace_seconds <= 0:
        return False
    stamps = [committed_at] if pushed_at is None else [committed_at, pushed_at]
    for stamp in stamps:
        signed = _clock_age_seconds(stamp, now)
        if signed is None or signed < -MAX_FUTURE_SKEW_SECONDS or signed >= grace_seconds:
            return False
    return True

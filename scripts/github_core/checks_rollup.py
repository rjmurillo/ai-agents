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
) -> list[list[dict]]:
    """Split same-named rows into groups that share one workflow run.

    Rows whose workflow run id cannot be determined are each returned as their
    own single-row group, so cross-run precedence still applies to them exactly
    as it did before. Only rows proven to come from the same run are grouped,
    which keeps the change surgical: supersession semantics (issue #2208) are
    untouched for every row that is not a proven same-run sibling.

    Refs issue #4499: two jobs of one run named "Run Python Tests" (one
    FAILURE, one SKIPPED) were collapsed to the SKIPPED row, so the failure
    vanished and CIPassing reported true against a red PR.
    """
    by_run: dict[str, list[dict]] = {}
    order: list[str] = []
    singletons: list[list[dict]] = []

    for row in rows:
        run_id = extract_workflow_run_id(row.get(url_key))
        if run_id is None:
            singletons.append([row])
            continue
        if run_id not in by_run:
            by_run[run_id] = []
            order.append(run_id)
        by_run[run_id].append(row)

    return [by_run[run_id] for run_id in order] + singletons


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
        is_required_by_name[name] = (
            is_required_by_name.get(name, False) or bool(check.get("IsRequired"))
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
    endpoint = f"repos/{owner}/{repo}/rules/branches/{branch}"
    result = subprocess.run(
        ["gh", "api", endpoint],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    if result.returncode != 0:
        return None
    try:
        rules = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(rules, list):
        return None

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

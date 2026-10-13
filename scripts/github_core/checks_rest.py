"""Read a pull request's CI checks over REST.

GraphQL and REST carry separate quotas. When GraphQL refuses with a rate-limit
body (issue #6391), the REST endpoints for check runs and commit statuses keep
answering, so a caller can still read the checks. This module fetches them and
reshapes each row into the GraphQL ``statusCheckRollup`` node shape, so one
normalizer in the caller handles both transports.

Stricter/looser/different than canonical: GraphQL reports ``isRequired`` per
row. REST has no such field, so this module leaves ``isRequired`` False and the
caller marks required rows from the branch ruleset with
:func:`mark_required_from_ruleset`. A ruleset reports names; classic branch
protection is not read.

Standard library only: this module ships in the plugin lib trees.
"""

from __future__ import annotations

import json
import subprocess

from scripts.github_core.checks_rollup import extract_workflow_run_number

_TIMEOUT_SECONDS = 30
_PAGE_SIZE = 100

# REST ``mergeable_state`` values and the GraphQL ``MergeStateStatus`` enum
# share one vocabulary in different case, so upper-casing maps them.
_MERGEABLE_BY_REST_VALUE: dict[object, str] = {True: "MERGEABLE", False: "CONFLICTING"}


def _run_gh_api(args: list[str]) -> object:
    """Run ``gh api`` and return the parsed JSON body.

    Raises:
        RuntimeError: when gh exits non-zero, times out, or returns non-JSON.
            The message carries gh's own text so a caller can classify it.
    """
    try:
        result = subprocess.run(
            ["gh", "api", *args],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"REST request failed: {exc}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip() or "gh exited non-zero"
        raise RuntimeError(f"REST request failed: {detail}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"REST request returned non-JSON: {exc}") from exc


def _fetch_pages(endpoint: str, items_key: str) -> tuple[list[dict], int | None]:
    """Return every item under ``items_key`` across all pages, plus total_count.

    ``--slurp`` wraps the per-page objects in one outer list. ``total_count``
    comes from the first page; a caller compares it with the collected length
    to detect a truncated read.
    """
    separator = "&" if "?" in endpoint else "?"
    pages = _run_gh_api(["--paginate", "--slurp", f"{endpoint}{separator}per_page={_PAGE_SIZE}"])
    if not isinstance(pages, list) or not all(isinstance(page, dict) for page in pages):
        raise RuntimeError(f"REST response for {endpoint} is not a list of pages")
    items = [
        item for page in pages for item in (page.get(items_key) or []) if isinstance(item, dict)
    ]
    total = pages[0].get("total_count") if pages else 0
    return items, total if isinstance(total, int) else None


def to_graphql_check_run(run: dict) -> dict:
    """Reshape one REST check run into a GraphQL ``CheckRun`` node."""
    status = run.get("status")
    conclusion = run.get("conclusion")
    details_url = run.get("details_url") or ""
    run_id = extract_workflow_run_number(details_url)
    workflow_run = {"databaseId": run_id, "runAttempt": None} if run_id is not None else None
    return {
        "__typename": "CheckRun",
        "name": run.get("name", ""),
        "status": status.upper() if isinstance(status, str) else "",
        "conclusion": conclusion.upper() if isinstance(conclusion, str) else None,
        "detailsUrl": details_url,
        "checkSuite": {"workflowRun": workflow_run},
        "isRequired": False,
    }


def to_graphql_status_context(status: dict) -> dict:
    """Reshape one REST commit status into a GraphQL ``StatusContext`` node."""
    state = status.get("state")
    return {
        "__typename": "StatusContext",
        "context": status.get("context", ""),
        "state": state.upper() if isinstance(state, str) else "",
        "targetUrl": status.get("target_url") or "",
        "isRequired": False,
    }


def _merge_fields(pr: dict) -> tuple[str, str]:
    """Return (MergeState, MergeStateStatus) in the GraphQL vocabulary."""
    merge_state = _MERGEABLE_BY_REST_VALUE.get(pr.get("mergeable"), "UNKNOWN")
    state_status = pr.get("mergeable_state")
    status = state_status.upper() if isinstance(state_status, str) and state_status else "UNKNOWN"
    return merge_state, status


def fetch_checks_rest(owner: str, repo: str, pr_number: int) -> dict:
    """Read a PR's check runs and commit statuses over REST.

    Returns a snapshot dict: ``Number``, ``BaseBranch``, ``MergeState``,
    ``MergeStateStatus``, ``Nodes`` (GraphQL-shaped contexts), and
    ``PagesComplete`` (False when a total_count exceeds the rows collected).

    Raises:
        RuntimeError: on any REST failure, carrying gh's text. A 404 reads
            "Not Found" so a caller can report the PR as missing.
    """
    pr = _run_gh_api([f"repos/{owner}/{repo}/pulls/{pr_number}"])
    if not isinstance(pr, dict):
        raise RuntimeError("REST pull request response is not an object")
    sha = (pr.get("head") or {}).get("sha")
    if not sha:
        raise RuntimeError("REST pull request response has no head sha")

    runs, runs_total = _fetch_pages(f"repos/{owner}/{repo}/commits/{sha}/check-runs", "check_runs")
    statuses, statuses_total = _fetch_pages(
        f"repos/{owner}/{repo}/commits/{sha}/status", "statuses"
    )
    nodes = [to_graphql_check_run(run) for run in runs]
    nodes.extend(to_graphql_status_context(status) for status in statuses)

    merge_state, merge_state_status = _merge_fields(pr)
    return {
        "Number": pr.get("number", pr_number),
        "BaseBranch": (pr.get("base") or {}).get("ref"),
        "MergeState": merge_state,
        "MergeStateStatus": merge_state_status,
        "Nodes": nodes,
        "PagesComplete": _is_complete(runs, runs_total) and _is_complete(statuses, statuses_total),
    }


def _is_complete(items: list[dict], total: int | None) -> bool:
    """True unless the API reported more rows than the pages returned."""
    return total is None or total <= len(items)


def mark_required_from_ruleset(checks: list[dict], ruleset_contexts: list[str]) -> None:
    """Set ``IsRequired`` on normalized checks whose name the ruleset requires.

    Mutates ``checks`` in place. Matching is by exact name, the same key the
    ruleset uses for a required status check context.
    """
    required = set(ruleset_contexts)
    for check in checks:
        check["IsRequired"] = check.get("Name", "") in required

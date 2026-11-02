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

from .checks_rollup import extract_workflow_run_number
from .not_found import is_pr_not_found

_TIMEOUT_SECONDS = 30
_PAGE_SIZE = 100

# REST ``mergeable`` is a boolean, or null while GitHub still computes it (a
# first read right after a push often returns null, which falls through to
# ``UNKNOWN`` so ``MergeRefUsable`` is false until the computation finishes).
# ``_merge_fields`` upper-cases ``mergeable_state`` separately, because it shares
# the GraphQL ``MergeStateStatus`` vocabulary in different case.
_MERGEABLE_BY_REST_VALUE: dict[object, str] = {True: "MERGEABLE", False: "CONFLICTING"}


class PullRequestNotFoundError(RuntimeError):
    """The pull request read returned HTTP 404 on a readable repository.

    Only the pull request read raises this. A 404 from a later call (check
    runs, statuses, workflow runs) stays a plain RuntimeError, so a caller does
    not report a PR as missing when only a secondary endpoint failed.
    """


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


def _fetch_workflow_runs(owner: str, repo: str, sha: str) -> tuple[dict[int, dict], bool]:
    """Map workflow run id to its ``event`` and ``run_attempt`` for one head SHA.

    A check run carries neither field. Without the event, the caller cannot
    tell a ``pull_request`` run from a ``push`` run of the same check name, and
    a newer passing run of one event would hide a failing run of the other.
    Returns the map plus whether the pages were complete.

    Raises:
        RuntimeError: on any REST failure. The caller lets it propagate, so
            an unreadable event fails the fallback instead of guessing.
    """
    runs, total = _fetch_pages(f"repos/{owner}/{repo}/actions/runs?head_sha={sha}", "workflow_runs")
    by_id = {run["id"]: run for run in runs if isinstance(run.get("id"), int)}
    return by_id, _is_complete(runs, total)


def to_graphql_check_run(run: dict, workflow_runs: dict[int, dict] | None = None) -> dict:
    """Reshape one REST check run into a GraphQL ``CheckRun`` node.

    ``workflow_runs`` maps run id to the REST workflow run, which supplies the
    ``event`` and ``runAttempt`` that a check run does not carry. A run id
    absent from the map keeps both None.
    """
    status = run.get("status")
    conclusion = run.get("conclusion")
    details_url = run.get("details_url") or ""
    run_id = extract_workflow_run_number(details_url)
    workflow_run = None
    if run_id is not None:
        meta = (workflow_runs or {}).get(run_id) or {}
        workflow_run = {
            "databaseId": run_id,
            "runAttempt": meta.get("run_attempt"),
            "event": meta.get("event"),
        }
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


def _fetch_head_committed_at(owner: str, repo: str, sha: str) -> str | None:
    """Return the head commit's committer date, or None when it cannot be read.

    GraphQL reports this as ``committedDate``. The queued-required grace window
    needs it (issue #6389), but a failed read must not fail the whole fallback:
    None keeps an absent required check reported as never reported.
    """
    try:
        commit = _run_gh_api([f"repos/{owner}/{repo}/git/commits/{sha}"])
    except RuntimeError:
        return None
    committer = commit.get("committer") if isinstance(commit, dict) else None
    date = committer.get("date") if isinstance(committer, dict) else None
    return date if isinstance(date, str) and date else None


def _has_check_suites(owner: str, repo: str, sha: str) -> bool:
    """Return whether any check suite exists for the head SHA.

    GraphQL returns a ``statusCheckRollup`` with no contexts when check suites
    exist but no run has posted yet, and ``--wait`` keeps polling that state
    (#2304). An empty check-runs list cannot show it, so this reads the suites.
    One row is enough: ``total_count`` carries the full count.

    Raises:
        RuntimeError: on a REST failure or a malformed body, so the fallback
            fails closed instead of reading a fresh push as a no-CI PR.
    """
    body = _run_gh_api([f"repos/{owner}/{repo}/commits/{sha}/check-suites?per_page=1"])
    if not isinstance(body, dict):
        raise RuntimeError("REST check-suites response is not an object")
    total = body.get("total_count")
    if isinstance(total, int):
        return total > 0
    return bool(body.get("check_suites"))


def _pr_read_error(owner: str, repo: str, exc: RuntimeError) -> RuntimeError:
    """Classify a failed pull request read.

    REST answers 404 both for a missing PR and for a repository the token
    cannot see. GraphQL words those apart, and only a missing PR exits as not
    found, so a not-found read here probes the repository before claiming
    the PR is missing.
    """
    if not is_pr_not_found(str(exc)):
        return exc
    try:
        _run_gh_api([f"repos/{owner}/{repo}"])
    except RuntimeError as repo_exc:
        return RuntimeError(f"Cannot read repository {owner}/{repo}: {repo_exc}")
    return PullRequestNotFoundError(str(exc))


def _merge_fields(pr: dict) -> tuple[str, str]:
    """Return (MergeState, MergeStateStatus) in the GraphQL vocabulary."""
    merge_state = _MERGEABLE_BY_REST_VALUE.get(pr.get("mergeable"), "UNKNOWN")
    state_status = pr.get("mergeable_state")
    status = state_status.upper() if isinstance(state_status, str) and state_status else "UNKNOWN"
    return merge_state, status


def _dict_field(obj: dict, key: str) -> dict:
    """Return ``obj[key]`` when it is a dict, else an empty dict.

    A malformed payload then reads as a missing field (which the caller
    reports as RuntimeError) instead of raising AttributeError.
    """
    value = obj.get(key)
    return value if isinstance(value, dict) else {}


def fetch_checks_rest(owner: str, repo: str, pr_number: int) -> dict:
    """Read a PR's check runs and commit statuses over REST.

    Returns a snapshot dict: ``Number``, ``BaseBranch``, ``MergeState``,
    ``MergeStateStatus``, ``Nodes`` (GraphQL-shaped contexts),
    ``PagesComplete`` (False when a total_count exceeds the rows collected,
    including the workflow runs that supply each check run's event),
    ``HeadCommittedAt`` (None when the head commit date cannot be read),
    and ``HasCheckSuites`` (True when a check suite exists, even with no run).

    Raises:
        PullRequestNotFoundError: when the pull request read returns 404 and
            the repository itself is readable.
        RuntimeError: on any other REST failure, carrying gh's text.
    """
    try:
        pr = _run_gh_api([f"repos/{owner}/{repo}/pulls/{pr_number}"])
    except RuntimeError as exc:
        classified = _pr_read_error(owner, repo, exc)
        if classified is exc:
            raise
        raise classified from exc
    if not isinstance(pr, dict):
        raise RuntimeError("REST pull request response is not an object")
    sha = _dict_field(pr, "head").get("sha")
    if not sha:
        raise RuntimeError("REST pull request response has no head sha")

    runs, runs_total = _fetch_pages(f"repos/{owner}/{repo}/commits/{sha}/check-runs", "check_runs")
    statuses, statuses_total = _fetch_pages(
        f"repos/{owner}/{repo}/commits/{sha}/status", "statuses"
    )
    workflow_runs, workflow_runs_complete = _fetch_workflow_runs(owner, repo, sha)
    nodes = [to_graphql_check_run(run, workflow_runs) for run in runs]
    nodes.extend(to_graphql_status_context(status) for status in statuses)

    merge_state, merge_state_status = _merge_fields(pr)
    return {
        "Number": pr.get("number", pr_number),
        "BaseBranch": _dict_field(pr, "base").get("ref"),
        "MergeState": merge_state,
        "MergeStateStatus": merge_state_status,
        "Nodes": nodes,
        "PagesComplete": (
            _is_complete(runs, runs_total)
            and _is_complete(statuses, statuses_total)
            and workflow_runs_complete
        ),
        "HeadCommittedAt": _fetch_head_committed_at(owner, repo, sha),
        "HasCheckSuites": _has_check_suites(owner, repo, sha),
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

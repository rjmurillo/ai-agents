#!/usr/bin/env python3
"""Diagnose why a PR reports mergeStateStatus BLOCKED.

Cross-references the base branch ruleset required checks against the PR's
statusCheckRollup and unresolved review threads to produce a discriminated
cause list:

  MISSING  - required by the ruleset, never ran (produced no row in the rollup)
  FAILING  - required by the ruleset or isRequired=true, conclusion is failing
  THREADS  - unresolved review threads requiring resolution

When all gates are satisfied, reports "likely mergeable" because BLOCKED is not
authoritative: PRs with all gates satisfied have been observed to merge on the
first attempt.

Exit codes follow ADR-035:
    0 - Diagnostic produced
    2 - PR not found
    3 - API error
    4 - Auth error
"""

from __future__ import annotations

import os
import sys

_plugin_root = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT")
_workspace = os.environ.get("GITHUB_WORKSPACE")
if _plugin_root and os.path.isdir(os.path.join(_plugin_root, "lib", "github_core")):
    _lib_dir = os.path.join(_plugin_root, "lib")
elif _workspace:
    _lib_dir = os.path.join(_workspace, ".claude", "lib")
else:
    _lib_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "lib")
    )
if not os.path.isdir(_lib_dir):
    print(f"Plugin lib directory not found: {_lib_dir}", file=sys.stderr)
    sys.exit(2)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

import argparse  # noqa: E402
import subprocess  # noqa: E402
from typing import Any  # noqa: E402

from github_core.api import (  # noqa: E402
    assert_gh_authenticated,
    gh_graphql,
    resolve_repo_params,
)
from github_core.checks_rollup import group_checks_by_name  # noqa: E402
from github_core.output import (  # noqa: E402
    add_output_format_arg,
    get_output_format,
    write_skill_error,
    write_skill_output,
)
from github_core.review_threads import count_unresolved_threads  # noqa: E402

_SCRIPT_NAME = "why_pr_blocked.py"

# Passing conclusions: SKIPPED satisfies a required context per field data.
_PASSING_CONCLUSIONS = {"SUCCESS", "NEUTRAL", "SKIPPED"}
_FAILING_CONCLUSIONS = {
    "FAILURE", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED",
    "STALE", "STARTUP_FAILURE",
}
_PENDING_STATUSES = {"QUEUED", "IN_PROGRESS", "WAITING", "PENDING", "REQUESTED"}

_PR_QUERY = """\
query($owner: String!, $repo: String!, $number: Int!) {
    repository(owner: $owner, name: $repo) {
        pullRequest(number: $number) {
            number
            state
            baseRefName
            mergeable
            mergeStateStatus
            commits(last: 1) {
                nodes {
                    commit {
                        statusCheckRollup {
                            contexts(first: 100) {
                                pageInfo { hasNextPage endCursor }
                                nodes {
                                    ... on CheckRun {
                                        __typename name status conclusion
                                        isRequired(pullRequestNumber: $number)
                                    }
                                    ... on StatusContext {
                                        __typename context state
                                        isRequired(pullRequestNumber: $number)
                                    }
                                }
                            }
                        }
                    }
                }
            }
            reviewThreads(first: 100) {
                nodes { isResolved }
            }
        }
    }
}"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Diagnose why a PR is blocked.")
    p.add_argument("--owner", default="")
    p.add_argument("--repo", default="")
    p.add_argument("--pull-request", type=int, required=True)
    add_output_format_arg(p)
    return p


def _fetch_ruleset_contexts(owner: str, repo: str, base_branch: str) -> list[str]:
    """Return required context names from the branch ruleset. Empty on error."""
    import json as _json  # noqa: PLC0415

    result = subprocess.run(
        [
            "gh", "api",
            f"repos/{owner}/{repo}/rules/branches/{base_branch}",
            "--jq",
            (
                "[.[]"
                "| select(.type==\"required_status_checks\")"
                "| .parameters.required_status_checks[].context]"
            ),
        ],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        return []
    try:
        raw = result.stdout.strip()
        return list(_json.loads(raw)) if raw else []
    except Exception:  # noqa: BLE001
        return []


def _normalize_check(node: dict[str, Any]) -> dict[str, Any] | None:
    """Convert a GraphQL context node to a normalized dict."""
    typename = node.get("__typename")
    if typename == "CheckRun":
        status = node.get("status", "")
        conclusion = node.get("conclusion") or ""
        is_pending = status in _PENDING_STATUSES
        is_passing = conclusion in _PASSING_CONCLUSIONS
        is_failing = conclusion in _FAILING_CONCLUSIONS
        return {
            "Name": node.get("name", ""),
            "IsRequired": bool(node.get("isRequired", False)),
            "IsPending": is_pending,
            "IsPassing": is_passing,
            "IsFailing": is_failing,
        }
    if typename == "StatusContext":
        state = node.get("state", "")
        return {
            "Name": node.get("context", ""),
            "IsRequired": bool(node.get("isRequired", False)),
            "IsPending": state in ("PENDING", "EXPECTED"),
            "IsPassing": state == "SUCCESS",
            "IsFailing": state in ("FAILURE", "ERROR"),
        }
    return None


def diagnose(
    owner: str,
    repo: str,
    pr_number: int,
) -> dict[str, Any]:
    """Run the full blocked diagnostic for one PR. Returns the result dict."""
    try:
        data = gh_graphql(_PR_QUERY, {"owner": owner, "repo": repo, "number": pr_number})
    except RuntimeError as exc:
        msg = str(exc)
        if "Could not resolve" in msg or "not found" in msg:
            return {"Error": "NotFound", "Message": f"PR #{pr_number} not found"}
        return {"Error": "ApiError", "Message": f"GraphQL query failed: {msg}"}

    pr = (data.get("repository") or {}).get("pullRequest")
    if pr is None:
        return {"Error": "NotFound", "Message": f"PR #{pr_number} not found in response"}

    base_branch = pr.get("baseRefName", "")
    merge_state_status = pr.get("mergeStateStatus", "")

    # Collect raw check nodes from rollup.
    commits = (pr.get("commits") or {}).get("nodes") or []
    raw_nodes: list[dict[str, Any]] = []
    if commits:
        commit_obj = (commits[0].get("commit") or {})
        rollup = commit_obj.get("statusCheckRollup")
        if rollup:
            contexts_obj = rollup.get("contexts") or {}
            raw_nodes = list(contexts_obj.get("nodes") or [])

    checks = [n for node in raw_nodes if (n := _normalize_check(node)) is not None]

    # Group by name and OR the isRequired flag (same semantics as sibling
    # scripts).
    checks_by_name, is_required_by_name, _ = group_checks_by_name(checks)

    # Best verdict per name: passing beats failing beats pending.
    def _best(name: str) -> dict[str, Any]:
        return dict(checks_by_name[name])

    # Ruleset required contexts (ground truth independent of what reported).
    ruleset_required = _fetch_ruleset_contexts(owner, repo, base_branch) if base_branch else []

    # Reported context names.
    reported: set[str] = set(checks_by_name)

    # MISSING: required by ruleset but never reported.
    missing: list[str] = sorted(c for c in ruleset_required if c not in reported)

    # FAILING: required (by ruleset or isRequired) and conclusion is failing.
    required_names = set(ruleset_required) | {
        name for name, req in is_required_by_name.items() if req
    }
    failing: list[str] = sorted(
        name for name in required_names
        if name in checks_by_name and _best(name).get("IsFailing")
    )

    # PENDING: required and still running.
    pending_required: list[str] = sorted(
        name for name in required_names
        if name in checks_by_name and _best(name).get("IsPending")
    )

    # Unresolved review threads.
    thread_nodes = (pr.get("reviewThreads") or {}).get("nodes") or []
    unresolved_threads = count_unresolved_threads(thread_nodes)

    causes: list[str] = []
    if missing:
        causes.append(f"MISSING ({len(missing)} required check(s) never reported)")
    if failing:
        causes.append(f"FAILING ({len(failing)} required check(s))")
    if pending_required:
        causes.append(f"PENDING ({len(pending_required)} required check(s))")
    if unresolved_threads:
        causes.append(f"THREADS ({unresolved_threads} unresolved review thread(s))")

    likely_mergeable = not causes

    return {
        "Success": True,
        "Number": pr_number,
        "Owner": owner,
        "Repo": repo,
        "BaseBranch": base_branch,
        "MergeStateStatus": merge_state_status,
        "LikelyMergeable": likely_mergeable,
        "Causes": causes,
        "MissingRequiredChecks": missing,
        "FailingRequiredChecks": failing,
        "PendingRequiredChecks": pending_required,
        "UnresolvedThreads": unresolved_threads,
        "RulesetRequiredContexts": ruleset_required,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    fmt = get_output_format(args.output_format)

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo

    result = diagnose(owner, repo, args.pull_request)

    if result.get("Error") == "NotFound":
        write_skill_error(
            result["Message"], 2, error_type="NotFound",
            output_format=fmt, script_name=_SCRIPT_NAME,
        )
        return 2

    if result.get("Error") == "ApiError":
        write_skill_error(
            result["Message"], 3, error_type="ApiError",
            output_format=fmt, script_name=_SCRIPT_NAME,
        )
        return 3

    causes = result.get("Causes") or []
    if result.get("LikelyMergeable"):
        summary = f"PR #{args.pull_request}: likely mergeable (no blocking causes found)"
        status = "PASS"
    else:
        summary = f"PR #{args.pull_request} BLOCKED: {'; '.join(causes)}"
        status = "FAIL"

    write_skill_output(
        result,
        output_format=fmt,
        human_summary=summary,
        status=status,
        script_name=_SCRIPT_NAME,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Rerun the failed GitHub Actions jobs of a pull request, without raw gh.

Targets, one of:
- ``--pull-request N``: every completed failed run for the PR head SHA.
- ``--run-id ID``: that one run.
- ``--run-id ID --job-id JOB``: rerun a single job of that run.

REST calls (checked against docs.github.com/en/rest/actions/workflow-runs on
2026-10-29):
- ``GET /repos/{o}/{r}/actions/runs?head_sha=SHA`` lists runs for a commit.
- ``POST /repos/{o}/{r}/actions/runs/{id}/rerun-failed-jobs`` answers 201.
- ``POST /repos/{o}/{r}/actions/jobs/{id}/rerun`` answers 201; 403 is documented.

Behavior:
- A run that is not ``completed`` cannot be rerun. With only such runs the
  script exits 1 with ``reason: run_in_progress`` and the run status.
- The run list is read lossless: pages are walked until ``total_count`` unique
  runs are seen. A short page, a non-object page, a missing ``total_count``, or
  the page cap before that point exits 3 with ``reason: pagination_incomplete``.
  Runs are deduplicated by run id.
- A 403 that says the run cannot be retried is an authoritative refusal. It is
  never retried. The script exits 100 with ``reason: cannot_be_retried``, names
  the refused runs, and prints the documented fallbacks on stderr and in
  ``Data.fallbacks``. Other runs in the same PR still get their rerun.
- The refusal wording is matched on ``cannot be retried``, ``cannot be rerun``
  and ``cannot be re-run``. A 403 with other wording falls through to exit 3
  with the API text shown, so the agent reads it instead of guessing.

Output uses the standard skill envelope (ADR-056). Exit codes follow ADR-035:
    0 - Success (reruns requested, or no failed runs to rerun)
    1 - Invalid parameters, or the only candidate runs are still in progress
    2 - PR or run not found
    3 - External error (API failure, timeout, incomplete pagination)
    4 - Auth error
  100 - Script-specific: GitHub refused the rerun (run cannot be retried)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, NoReturn

_plugin_root = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root and os.path.isdir(os.path.join(_plugin_root, "lib", "github_core")):
    _lib_dir = os.path.join(_plugin_root, "lib")
else:
    _lib_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "lib")
    )
if not os.path.isdir(_lib_dir):
    print(f"Plugin lib directory not found: {_lib_dir}", file=sys.stderr)
    sys.exit(2)  # Config error per ADR-035
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import (
    check_gh_auth,
    describe_gh_auth_failure,
    is_auth_failure_text,
    resolve_repo_params,
    sanitize_failure_detail,
)
from github_core.gh_client import GhCliClient
from github_core.not_found import is_pr_not_found
from github_core.output import (
    add_output_format_arg,
    write_skill_error,
    write_skill_output,
)

_SCRIPT_NAME = "rerun_failed_jobs.py"
EXIT_REFUSED = 100
_PAGE_SIZE = 100
_MAX_PAGES = 50
_FAILED_CONCLUSIONS = frozenset({"failure", "timed_out", "cancelled", "startup_failure"})
_REFUSAL_MARKERS = ("cannot be retried", "cannot be rerun", "cannot be re-run")
_RATE_LIMIT_MARKERS = ("rate limit", "abuse detection")

# Source: the review skill's marker doc (marker-and-no-task.md): after the marker
# lands, a clean merge of origin/main needs no new review.
FALLBACKS = (
    "If origin/main has moved, merge it into the branch cleanly (no conflict edits). "
    "The pre-push marker gate allows a clean merge of origin/main without a new review, "
    "and the new head starts fresh runs.",
    "update_pr_branch.py (github skill) does the same merge server side; pass --expected-head-sha.",
    "If main has not moved, do not push an empty commit: it invalidates the SHA-bound "
    "review marker. Ask a human to rerun the workflow from the Actions UI.",
)


def is_cannot_retry_refusal(text: str) -> bool:
    """Return True when API or gh text says GitHub will not rerun this run."""
    lowered = (text or "").lower()
    return any(marker in lowered for marker in _REFUSAL_MARKERS)


@dataclass(frozen=True)
class _Ctx:
    repo: str
    output_format: str
    pull_request: int | None
    run_id: int | None


class _ExitOneParser(argparse.ArgumentParser):
    """Argparse exits 2 on bad input; ADR-035 reserves 2 for not-found, so use 1."""

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        print(f"{self.prog}: error: {message}", file=sys.stderr)
        raise SystemExit(1)


def build_parser() -> argparse.ArgumentParser:
    parser = _ExitOneParser(
        description="Rerun failed GitHub Actions jobs for a PR or run.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument("--pull-request", type=int, help="Pull request number")
    parser.add_argument("--run-id", type=int, help="Workflow run ID")
    parser.add_argument("--job-id", type=int, help="Rerun only this job (requires --run-id)")
    add_output_format_arg(parser)
    return parser


def _emit_error(
    ctx: _Ctx, message: str, code: int, error_type: str, reason: str, **extra: Any
) -> NoReturn:
    """Emit the error envelope with a machine-readable reason, then exit."""
    data = {"reason": reason, "pull_request": ctx.pull_request, "run_id": ctx.run_id, **extra}
    write_skill_error(
        message,
        code,
        error_type=error_type,
        output_format=ctx.output_format,
        script_name=_SCRIPT_NAME,
        extra=data,
    )
    raise SystemExit(code)


def _fail_api(ctx: _Ctx, what: str, exc: Exception, **extra: Any) -> NoReturn:
    """Map a client exception to the matching exit code and envelope."""
    text = str(exc)
    detail = sanitize_failure_detail(text) or type(exc).__name__
    if isinstance(exc, subprocess.TimeoutExpired):
        _emit_error(ctx, f"{what} timed out; outcome unknown", 3, "Timeout", "timeout", **extra)
    if is_auth_failure_text(text):
        _emit_error(ctx, f"Not authorized: {what}: {detail}", 4, "AuthError", "auth", **extra)
    if is_pr_not_found(text):
        _emit_error(ctx, f"Not found: {what}: {detail}", 2, "NotFound", "not_found", **extra)
    if any(marker in text.lower() for marker in _RATE_LIMIT_MARKERS):
        _emit_error(ctx, f"{what}: {detail}", 3, "RateLimitError", "rate_limited", **extra)
    _emit_error(ctx, f"{what} failed: {detail}", 3, "ApiError", "api_error", **extra)


def _get(client: Any, ctx: _Ctx, endpoint: str, what: str) -> Any:
    try:
        return client.rest_get(endpoint)
    except (RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
        _fail_api(ctx, what, exc)


def _run_summary(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": run.get("id"),
        "name": run.get("name"),
        "status": run.get("status"),
        "conclusion": run.get("conclusion"),
        "html_url": run.get("html_url"),
    }


def _incomplete(ctx: _Ctx, why: str) -> NoReturn:
    _emit_error(
        ctx,
        f"Run list is incomplete, refusing to act on a partial set: {why}",
        3,
        "ApiError",
        "pagination_incomplete",
    )


def _page_items(ctx: _Ctx, page: Any, number: int) -> tuple[list[Any], int]:
    """Validate one run-list page; return (items, total_count)."""
    if not isinstance(page, dict) or not isinstance(page.get("workflow_runs"), list):
        _incomplete(ctx, f"page {number} is not an object with a workflow_runs list")
    total = page.get("total_count")
    if isinstance(total, bool) or not isinstance(total, int):
        _incomplete(ctx, f"page {number} has no integer total_count")
    return page["workflow_runs"], total


def list_runs_for_sha(client: Any, ctx: _Ctx, sha: str) -> list[dict[str, Any]]:
    """Return every run for ``sha``, deduplicated by run id, or exit 3."""
    unique: dict[int, dict[str, Any]] = {}
    for number in range(1, _MAX_PAGES + 1):
        endpoint = (
            f"repos/{ctx.repo}/actions/runs?head_sha={sha}&per_page={_PAGE_SIZE}&page={number}"
        )
        page = _get(client, ctx, endpoint, f"Listing runs (page {number})")
        items, total = _page_items(ctx, page, number)
        for item in items:
            if isinstance(item, dict) and isinstance(item.get("id"), int):
                unique.setdefault(item["id"], item)
        if len(unique) >= total:
            return list(unique.values())
        if len(items) < _PAGE_SIZE:
            _incomplete(ctx, f"saw {len(unique)} of {total} runs, then page {number} ended")
    _incomplete(ctx, f"saw {len(unique)} runs after the {_MAX_PAGES}-page cap")


def _pr_head_sha(client: Any, ctx: _Ctx) -> str:
    pr = _get(client, ctx, f"repos/{ctx.repo}/pulls/{ctx.pull_request}", "Reading PR")
    head = pr.get("head") if isinstance(pr, dict) else None
    sha = head.get("sha") if isinstance(head, dict) else None
    if not isinstance(sha, str) or not sha:
        _emit_error(ctx, "PR response has no head SHA", 3, "ApiError", "api_error")
    return sha


def _single_run(client: Any, ctx: _Ctx) -> dict[str, Any]:
    run = _get(client, ctx, f"repos/{ctx.repo}/actions/runs/{ctx.run_id}", "Reading run")
    if not isinstance(run, dict) or not isinstance(run.get("id"), int):
        _emit_error(ctx, "Run response was not a run object", 3, "ApiError", "api_error")
    return run


def _post_rerun(client: Any, ctx: _Ctx, endpoint: str) -> bool:
    """POST one rerun. True on success, False on a refusal, exit otherwise."""
    try:
        client.rest_post(endpoint, {})
    except (RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
        if is_cannot_retry_refusal(str(exc)):
            return False
        _fail_api(ctx, "Rerun request", exc)
    return True


def _rerun_all(
    client: Any, ctx: _Ctx, runs: list[dict[str, Any]], job_id: int | None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    done: list[dict[str, Any]] = []
    refused: list[dict[str, Any]] = []
    for run in runs:
        if job_id is None:
            endpoint = f"repos/{ctx.repo}/actions/runs/{run['id']}/rerun-failed-jobs"
            entry = {**_run_summary(run), "action": "rerun_failed_jobs"}
        else:
            endpoint = f"repos/{ctx.repo}/actions/jobs/{job_id}/rerun"
            entry = {**_run_summary(run), "action": "rerun_job", "job_id": job_id}
        (done if _post_rerun(client, ctx, endpoint) else refused).append(entry)
    return done, refused


def _partition(runs: list[dict[str, Any]]) -> tuple[list[dict], list[dict]]:
    """Split runs into (completed and failed, not completed)."""
    failed = [
        r
        for r in runs
        if r.get("status") == "completed" and r.get("conclusion") in _FAILED_CONCLUSIONS
    ]
    active = [r for r in runs if r.get("status") != "completed"]
    return failed, active


def _report_refusal(ctx: _Ctx, done: list, refused: list, data: dict[str, Any]) -> NoReturn:
    ids = ", ".join(str(r["run_id"]) for r in refused)
    for line in FALLBACKS:
        print(f"[FALLBACK] {line}", file=sys.stderr)
    _emit_error(
        ctx,
        f"GitHub refused the rerun of run(s) {ids}: the run cannot be retried. "
        "Do not retry; use a fallback.",
        EXIT_REFUSED,
        "ApiError",
        "cannot_be_retried",
        reruns=done,
        refused=refused,
        fallbacks=list(FALLBACKS),
        **data,
    )


def _resolve_targets(client: Any, ctx: _Ctx, job_id: int | None) -> tuple[list, list, dict]:
    """Return (failed runs, in-progress runs, extra Data) for the chosen mode."""
    if ctx.pull_request is not None:
        sha = _pr_head_sha(client, ctx)
        failed, active = _partition(list_runs_for_sha(client, ctx, sha))
        return failed, active, {"head_sha": sha}
    run = _single_run(client, ctx)
    failed, active = _partition([run])
    if job_id is not None and not active:
        failed = [run]  # an explicit job rerun does not require a failed run
    return failed, active, {"run_status": run.get("status")}


def _run(client: Any, ctx: _Ctx, job_id: int | None) -> int:
    failed, active, extra = _resolve_targets(client, ctx, job_id)
    active_view = [_run_summary(r) for r in active]
    if not failed and active:
        _emit_error(
            ctx,
            "Only in-progress runs found; a run that is not completed cannot be rerun. "
            f"Status: {', '.join(str(r['status']) for r in active_view)}",
            1,
            "InvalidParams",
            "run_in_progress",
            in_progress_runs=active_view,
            **extra,
        )
    done, refused = _rerun_all(client, ctx, failed, job_id)
    if refused:
        _report_refusal(ctx, done, refused, extra)
    reason = "rerun_requested" if done else "no_failed_runs"
    data = {
        "reason": reason,
        "pull_request": ctx.pull_request,
        "run_id": ctx.run_id,
        "reruns": done,
        "skipped_in_progress": active_view,
        **extra,
    }
    summary = f"Rerun requested for {len(done)} run(s); {len(active_view)} still in progress"
    if not done:
        summary = "No failed runs to rerun"
    write_skill_output(
        data,
        output_format=ctx.output_format,
        human_summary=summary,
        status="WARNING" if active_view else "PASS",
        script_name=_SCRIPT_NAME,
    )
    return 0


def _validate(args: argparse.Namespace) -> str:
    """Return an error message for invalid argument combinations, else empty."""
    for flag in ("pull_request", "run_id", "job_id"):
        value = getattr(args, flag)
        if value is not None and value < 1:
            return f"--{flag.replace('_', '-')} must be a positive integer"
    if (args.pull_request is None) == (args.run_id is None):
        return "Provide exactly one of --pull-request or --run-id"
    if args.job_id is not None and args.run_id is None:
        return "--job-id requires --run-id"
    return ""


def main(argv: list[str] | None = None, client: Any = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    ctx = _Ctx("", args.output_format, args.pull_request, args.run_id)
    problem = _validate(args)
    if problem:
        _emit_error(ctx, problem, 1, "InvalidParams", "invalid_params")
    auth = check_gh_auth()
    if not auth.is_authenticated:
        message, code, error_type = describe_gh_auth_failure(auth)
        _emit_error(ctx, message, code, error_type, "auth")
    resolved = resolve_repo_params(args.owner, args.repo)
    ctx = _Ctx(
        f"{resolved.owner}/{resolved.repo}", args.output_format, args.pull_request, args.run_id
    )
    return _run(client or GhCliClient(), ctx, args.job_id)


if __name__ == "__main__":
    raise SystemExit(main())

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
- PR mode needs an open PR (exit 1, ``pr_not_open``). It keeps the newest run per
  workflow and event (by ``run_number``), so a superseded run is never rerun. It
  drops runs that belong to other PRs (a run whose ``pull_requests`` list is
  non-empty and lacks this PR, as happens when two branches share a commit);
  their ids go in ``Data.skipped_other_pr_run_ids``. A run with an empty
  ``pull_requests`` list, such as a fork PR run, cannot be attributed and is kept.
- ``cancelled`` runs are never rerun by run, in either mode. They are listed in
  ``Data.skipped_cancelled``, since a human or a concurrency group may have
  cancelled them on purpose, and GitHub's docs do not say whether
  ``rerun-failed-jobs`` covers cancelled jobs. An explicit ``--job-id`` reruns
  that job whatever the run conclusion, and then ``skipped_cancelled`` is empty.
- ``--job-id`` is checked against ``--run-id`` first (exit 1, ``job_run_mismatch``).
- A run that is not ``completed`` cannot be rerun. With only such runs the
  script exits 1 with ``reason: run_in_progress`` and the run status. With both
  failed and in-progress runs it reruns the failed ones and lists the others in
  ``Data.skipped_in_progress``.
- The run list is read lossless: pages are walked until ``total_count`` unique
  runs are seen. A short page, a non-object page, a missing ``total_count``, or
  the page cap before that point exits 3 with ``reason: pagination_incomplete``.
  Runs are deduplicated by run id.
- Every run is attempted. Every envelope from the rerun step (exit 0, 3, 4 and
  100) carries ``reruns``, ``refused``, ``failed``, ``not_attempted_run_ids``,
  ``skipped_in_progress`` and ``skipped_cancelled``, so a failure never hides
  what landed. Early exits (1, 2, and 3 before any POST) carry ``reason`` only.
  An auth or rate-limit fault stops the batch, since the rest would fail the same
  way. The run that hit it is listed in ``failed`` with ``stopped_batch: true``.
- A 403 that says the run cannot be retried is an authoritative refusal. It is
  never retried. With no other failure the script exits 100 with
  ``reason: cannot_be_retried``, and prints the documented fallbacks on stderr
  and in ``Data.fallbacks``. Other runs in the same PR still get their rerun.
- The refusal wording is matched on ``cannot be retried``, ``cannot be rerun``
  and ``cannot be re-run``. A permission 403 ("Resource not accessible by
  integration") exits 4 with ``reason: auth``. A rate-limit 403 exits 3 with
  ``reason: rate_limited``. Any other wording exits 3 with the API text shown,
  so the agent reads it instead of guessing.
- Auth is REST-only: a session where GraphQL is blocked but repository REST works
  is allowed, as in the other REST-only scripts.
- Branch on ``Data.reason``, not ``Error.Type``: a refusal and a 500 are both ``ApiError``.

Output uses the standard skill envelope (ADR-056). Exit codes follow ADR-035:
    0 - Success (reruns requested, or no failed runs to rerun)
    1 - PR not open, job not in run, or only in-progress runs
    2 - Bad arguments (ADR-035 usage error, ``reason: invalid_params``), or PR, run,
        or job not found on a read (the sibling scripts' convention; branch on
        ``Data.reason``). Argparse type errors print usage on stderr and carry
        no envelope.
    3 - External error (API failure, timeout, incomplete pagination, a failed POST)
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
    assert_gh_authenticated,
    is_auth_failure_text,
    is_rate_limit_refusal,
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
from github_core.protocol import GitHubClient

_SCRIPT_NAME = "rerun_failed_jobs.py"
EXIT_REFUSED = 100
_PAGE_SIZE = 100
_MAX_PAGES = 50
_FAILED_CONCLUSIONS = frozenset({"failure", "timed_out", "startup_failure"})
_CANCELLED = "cancelled"
_REFUSAL_MARKERS = ("cannot be retried", "cannot be rerun", "cannot be re-run")

# Source: the review skill's marker doc (marker-and-no-task.md): after the marker
# lands, a clean merge of the validator's base ref needs no new review. The
# validator defaults that ref to origin/main and takes --base-ref for other bases.
FALLBACKS = (
    "If the PR base branch has moved, merge it into the branch cleanly (no conflict "
    "edits). The pre-push marker gate allows a clean merge of the base ref without a "
    "new review (origin/main by default, --base-ref otherwise), and the new head "
    "starts fresh runs.",
    "update_pr_branch.py (github skill) merges the base into the PR head on GitHub; "
    "pass --expected-head-sha.",
    "If the base branch has not moved, do not push an empty commit: it invalidates the SHA-bound "
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


@dataclass
class _Batch:
    """Outcome of the rerun POSTs, so every exit path can report what landed."""

    done: list[dict[str, Any]]
    refused: list[dict[str, Any]]
    failed: list[dict[str, Any]]
    not_attempted: list[int]

    def view(self) -> dict[str, Any]:
        return {
            "reruns": self.done,
            "refused": self.refused,
            "failed": self.failed,
            "not_attempted_run_ids": self.not_attempted,
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
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
    if is_rate_limit_refusal(text):
        _emit_error(ctx, f"{what}: {detail}", 3, "RateLimitError", "rate_limited", **extra)
    _emit_error(ctx, f"{what} failed: {detail}", 3, "ApiError", "api_error", **extra)


def _get(client: GitHubClient, ctx: _Ctx, endpoint: str, what: str) -> Any:
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


def list_runs_for_sha(client: GitHubClient, ctx: _Ctx, sha: str) -> list[dict[str, Any]]:
    """Return every run for ``sha``, deduplicated by run id, or exit 3."""
    unique: dict[int, dict[str, Any]] = {}
    dropped = 0
    for number in range(1, _MAX_PAGES + 1):
        endpoint = (
            f"repos/{ctx.repo}/actions/runs?head_sha={sha}&per_page={_PAGE_SIZE}&page={number}"
        )
        page = _get(client, ctx, endpoint, f"Listing runs (page {number})")
        items, total = _page_items(ctx, page, number)
        for item in items:
            if isinstance(item, dict) and isinstance(item.get("id"), int):
                unique.setdefault(item["id"], item)
            else:
                dropped += 1
        note = f" ({dropped} malformed item(s) skipped)" if dropped else ""
        if len(unique) >= total:
            return list(unique.values())
        if len(items) < _PAGE_SIZE:
            _incomplete(ctx, f"saw {len(unique)} of {total} runs, then page {number} ended{note}")
    _incomplete(ctx, f"saw {len(unique)} runs after the {_MAX_PAGES}-page cap")


def _read_pr(client: GitHubClient, ctx: _Ctx) -> str:
    """Return the PR head SHA; exit 1 unless the PR is open."""
    pr = _get(client, ctx, f"repos/{ctx.repo}/pulls/{ctx.pull_request}", "Reading PR")
    if not isinstance(pr, dict):
        _emit_error(ctx, "PR response was not an object", 3, "ApiError", "api_error")
    head = pr.get("head")
    sha = head.get("sha") if isinstance(head, dict) else None
    if not isinstance(sha, str) or not sha:
        _emit_error(ctx, "PR response has no head SHA", 3, "ApiError", "api_error")
    if pr.get("state") != "open":
        _emit_error(
            ctx,
            f"PR #{ctx.pull_request} is {pr.get('state') or 'in an unknown state'}; "
            "rerunning CI on a PR that is not open spends minutes for no merge outcome",
            1,
            "InvalidParams",
            "pr_not_open",
            state=pr.get("state"),
        )
    return sha


def _single_run(client: GitHubClient, ctx: _Ctx) -> dict[str, Any]:
    run = _get(client, ctx, f"repos/{ctx.repo}/actions/runs/{ctx.run_id}", "Reading run")
    if not isinstance(run, dict) or not isinstance(run.get("id"), int):
        _emit_error(ctx, "Run response was not a run object", 3, "ApiError", "api_error")
    return run


def _require_job_in_run(client: GitHubClient, ctx: _Ctx, job_id: int) -> None:
    """Exit 1 unless job ``job_id`` belongs to run ``--run-id``."""
    job = _get(client, ctx, f"repos/{ctx.repo}/actions/jobs/{job_id}", "Reading job")
    owner_run = job.get("run_id") if isinstance(job, dict) else None
    if not isinstance(owner_run, int):
        _emit_error(ctx, f"Job {job_id} response has no integer run_id", 3, "ApiError", "api_error")
    if owner_run != ctx.run_id:
        _emit_error(
            ctx,
            f"Job {job_id} belongs to run {owner_run}, not run {ctx.run_id}",
            1,
            "InvalidParams",
            "job_run_mismatch",
            job_id=job_id,
            job_run_id=owner_run,
        )


def _latest_per_workflow(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the newest run per (workflow_id, event).

    A superseded run (older ``run_number``) must not be rerun: it can join the
    newer run's concurrency group and cancel it, or replace its result.
    """
    latest: dict[tuple[Any, Any], tuple[tuple[int, int], dict[str, Any]]] = {}
    for run in runs:
        key = (run.get("workflow_id"), run.get("event"))
        number = run.get("run_number")
        rank = (number if isinstance(number, int) else 0, run["id"])
        if key not in latest or rank > latest[key][0]:
            latest[key] = (rank, run)
    return [run for _, run in latest.values()]


def _split_other_pr_runs(
    runs: list[dict[str, Any]], pull_request: int
) -> tuple[list[dict[str, Any]], list[int]]:
    """Drop runs that belong to other PRs; return (kept runs, dropped run ids).

    A run's head SHA names a commit, and two branches can share one. A run whose
    ``pull_requests`` list is non-empty and lacks ``pull_request`` belongs to
    other PRs. An empty or missing list cannot be attributed (a fork PR run has
    one), so the run is kept.
    """
    kept: list[dict[str, Any]] = []
    dropped: list[int] = []
    for run in runs:
        linked = run.get("pull_requests")
        numbers = [p.get("number") for p in linked if isinstance(p, dict)] if linked else []
        if numbers and pull_request not in numbers:
            dropped.append(run["id"])
        else:
            kept.append(run)
    return kept, dropped


def _partition(runs: list[dict[str, Any]]) -> tuple[list[dict], list[dict], list[dict]]:
    """Split runs into (rerun targets, still running, skipped cancelled)."""
    completed = [r for r in runs if r.get("status") == "completed"]
    targets = [r for r in completed if r.get("conclusion") in _FAILED_CONCLUSIONS]
    cancelled = [r for r in completed if r.get("conclusion") == _CANCELLED]
    active = [r for r in runs if r.get("status") != "completed"]
    return targets, active, cancelled


def _rerun_request(ctx: _Ctx, run: dict[str, Any], job_id: int | None) -> tuple[str, dict]:
    if job_id is None:
        endpoint = f"repos/{ctx.repo}/actions/runs/{run['id']}/rerun-failed-jobs"
        return endpoint, {**_run_summary(run), "action": "rerun_failed_jobs"}
    endpoint = f"repos/{ctx.repo}/actions/jobs/{job_id}/rerun"
    return endpoint, {**_run_summary(run), "action": "rerun_job", "job_id": job_id}


def _record_failure(
    ctx: _Ctx,
    batch: _Batch,
    entry: dict[str, Any],
    exc: Exception,
    remaining: list[int],
    extra: dict[str, Any],
) -> None:
    """File one failed POST. Auth and rate-limit faults stop the batch."""
    text = str(exc)
    detail = sanitize_failure_detail(text) or type(exc).__name__
    if is_cannot_retry_refusal(text):
        batch.refused.append({**entry, "detail": detail})
    elif isinstance(exc, subprocess.TimeoutExpired):
        batch.failed.append({**entry, "detail": "timed out; outcome unknown", "timed_out": True})
    elif is_auth_failure_text(text) or is_rate_limit_refusal(text):
        batch.failed.append({**entry, "detail": detail, "timed_out": False, "stopped_batch": True})
        batch.not_attempted = remaining
        stop_data = {**extra, **batch.view()}
        if batch.refused:
            _print_fallbacks()
            stop_data["fallbacks"] = list(FALLBACKS)
        _fail_api(ctx, "Rerun request", exc, **stop_data)
    else:
        batch.failed.append({**entry, "detail": detail, "timed_out": False})


def _rerun_all(
    client: GitHubClient,
    ctx: _Ctx,
    targets: list[dict[str, Any]],
    job_id: int | None,
    extra: dict[str, Any],
) -> _Batch:
    batch = _Batch([], [], [], [])
    for index, run in enumerate(targets):
        endpoint, entry = _rerun_request(ctx, run, job_id)
        try:
            client.rest_post(endpoint, {})
        except (RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
            remaining = [t["id"] for t in targets[index + 1 :]]
            _record_failure(ctx, batch, entry, exc, remaining, extra)
            continue
        batch.done.append(entry)
    return batch


def _print_fallbacks() -> None:
    for line in FALLBACKS:
        print(f"[FALLBACK] {line}", file=sys.stderr)


def _report_batch_errors(ctx: _Ctx, batch: _Batch, extra: dict[str, Any]) -> NoReturn:
    """Exit for a batch with failed or refused runs; every outcome stays visible."""
    if batch.refused:
        _print_fallbacks()
    refused_ids = ", ".join(str(r["run_id"]) for r in batch.refused)
    data = {**batch.view(), **extra}
    if batch.refused:
        data["fallbacks"] = list(FALLBACKS)
    if batch.failed:
        failed_ids = ", ".join(str(r["run_id"]) for r in batch.failed)
        timed_out = all(r["timed_out"] for r in batch.failed)
        _emit_error(
            ctx,
            f"Rerun request failed for run(s) {failed_ids}"
            + ("; a timeout leaves the outcome unknown" if timed_out else "")
            + f". Requested for {len(batch.done)} other run(s).",
            3,
            "Timeout" if timed_out else "ApiError",
            "timeout" if timed_out else "api_error",
            **data,
        )
    _emit_error(
        ctx,
        f"GitHub refused the rerun of run(s) {refused_ids}: the run cannot be retried. "
        "Do not retry; use a fallback.",
        EXIT_REFUSED,
        "ApiError",
        "cannot_be_retried",
        **data,
    )


def _resolve_targets(
    client: GitHubClient, ctx: _Ctx, job_id: int | None
) -> tuple[list, list, list, dict]:
    """Return (rerun targets, in-progress runs, skipped cancelled, extra Data)."""
    if ctx.pull_request is not None:
        sha = _read_pr(client, ctx)
        listed = list_runs_for_sha(client, ctx, sha)
        own, other_pr = _split_other_pr_runs(listed, ctx.pull_request)
        targets, active, cancelled = _partition(_latest_per_workflow(own))
        return targets, active, cancelled, {"head_sha": sha, "skipped_other_pr_run_ids": other_pr}
    run = _single_run(client, ctx)
    if job_id is not None:
        _require_job_in_run(client, ctx, job_id)
    targets, active, cancelled = _partition([run])
    if job_id is not None and not active:
        targets, cancelled = [run], []  # an explicit job rerun ignores the run conclusion
    return targets, active, cancelled, {"run_status": run.get("status")}


def _run(client: GitHubClient, ctx: _Ctx, job_id: int | None) -> int:
    targets, active, cancelled, extra = _resolve_targets(client, ctx, job_id)
    active_view = [_run_summary(r) for r in active]
    if not targets and active:
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
    cancelled_view = [_run_summary(r) for r in cancelled]
    extra = {**extra, "skipped_in_progress": active_view, "skipped_cancelled": cancelled_view}
    batch = _rerun_all(client, ctx, targets, job_id, extra)
    if batch.failed or batch.refused:
        _report_batch_errors(ctx, batch, extra)
    data = {
        "reason": "rerun_requested" if batch.done else "no_failed_runs",
        "pull_request": ctx.pull_request,
        "run_id": ctx.run_id,
        **batch.view(),
        **extra,
    }
    skipped = len(active_view) + len(cancelled_view)
    summary = f"Rerun requested for {len(batch.done)} run(s); {skipped} skipped"
    if not batch.done:
        summary = "No failed runs to rerun"
    write_skill_output(
        data,
        output_format=ctx.output_format,
        human_summary=summary,
        status="WARNING" if skipped else "PASS",
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


def main(argv: list[str] | None = None, client: GitHubClient | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    ctx = _Ctx("", args.output_format, args.pull_request, args.run_id)
    problem = _validate(args)
    if problem:
        _emit_error(ctx, problem, 2, "InvalidParams", "invalid_params")
    assert_gh_authenticated(rest_only=True)
    resolved = resolve_repo_params(args.owner, args.repo)
    ctx = _Ctx(
        f"{resolved.owner}/{resolved.repo}", args.output_format, args.pull_request, args.run_id
    )
    return _run(client or GhCliClient(), ctx, args.job_id)


if __name__ == "__main__":
    raise SystemExit(main())

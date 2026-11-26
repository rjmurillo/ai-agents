#!/usr/bin/env python3
"""Read one GitHub Actions workflow run: jobs, conclusions, pending approvals.

Agents investigating CI hit three run-level questions the PR-scoped scripts
cannot answer:

- What state is this run in (queued, waiting, in_progress, completed)?
- Which jobs and steps failed inside it?
- Is it waiting on an environment protection approval, and in which
  environment? The ``pending_deployments`` endpoint answers this; before this
  script, agents either asked a human to look at the Actions page or probed
  raw ``gh api`` endpoints.

Read-only. Approving a deployment stays a human action in the GitHub UI; this
script only makes the wait visible.

Exit codes follow ADR-035. The script never mutates, so exit 1 cannot occur:
    0 - The run was read; inspect Data.jobs and Data.pending_deployments
    2 - No run with this id exists in the repository
    3 - The API read failed
    4 - Auth error
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from skill_bootstrap import ensure_plugin_paths

ensure_plugin_paths(__file__, (".claude", "lib"))

from get_workflow_runs import normalize_run
from github_core.api import (
    assert_gh_authenticated,
    gh_api_get,
    resolve_repo_params,
)
from github_core.output import (
    add_output_format_arg,
    get_output_format,
    write_skill_error,
    write_skill_output,
)

_SCRIPT_NAME = "get_workflow_run.py"


def normalize_job(job: dict) -> dict:
    failed_steps = [
        {"name": step.get("name"), "number": step.get("number")}
        for step in job.get("steps") or []
        if step.get("conclusion") == "failure"
    ]
    return {
        "id": job.get("id"),
        "name": job.get("name"),
        "status": job.get("status"),
        "conclusion": job.get("conclusion"),
        "started_at": job.get("started_at"),
        "completed_at": job.get("completed_at"),
        "runner_labels": job.get("labels"),
        "failed_steps": failed_steps,
        "url": job.get("html_url"),
    }


def normalize_pending_deployment(dep: dict) -> dict:
    environment = dep.get("environment") or {}
    reviewers = []
    for entry in dep.get("reviewers") or []:
        reviewer = entry.get("reviewer") or {}
        if isinstance(reviewer, dict):
            name = reviewer.get("login") or reviewer.get("name")
            if name:
                reviewers.append(name)
    return {
        "environment": environment.get("name") if isinstance(environment, dict) else environment,
        "wait_minutes": dep.get("wait_timer"),
        "reviewers": reviewers,
    }


_HELP_EPILOG = """\
examples:
  %(prog)s --run-id 44220804544
  %(prog)s --run-id 44220804544 --output-format human

exit codes:
  0  success
  2  usage, configuration, or not-found error
  3  external service or API error
  4  auth error
"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Read one workflow run with jobs and pending approvals.",
        epilog=_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--owner", default="")
    p.add_argument("--repo", default="")
    p.add_argument("--run-id", type=int, required=True)
    add_output_format_arg(p)
    return p


def _build_summary(
    run: dict,
    run_id: int,
    data: dict,
    jobs_read: bool,
    jobs_capped: bool,
    pending_deployments: list[dict],
) -> str:
    failed_jobs = [job["name"] for job in data["jobs"] if job["conclusion"] == "failure"]
    bits = [f"run {run_id}: {run.get('status')}/{run.get('conclusion') or 'pending'}"]
    if not jobs_read:
        bits.append("jobs unread; empty jobs list is not evidence of a green run")
    elif jobs_capped:
        bits.append("jobs list capped at 100; later pages not scanned")
    if jobs_read and failed_jobs:
        bits.append(f"failed jobs: {', '.join(failed_jobs[:5])}")
    if pending_deployments:
        envs = ", ".join(str(dep["environment"]) for dep in pending_deployments)
        if any(dep["reviewers"] for dep in pending_deployments):
            bits.append(f"waiting on environment approval: {envs}")
        else:
            bits.append(f"environment wait timer pending (no approval required): {envs}")
    return "; ".join(bits)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    fmt = get_output_format(args.output_format)

    assert_gh_authenticated(rest_only=True)
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo
    run_id = args.run_id

    run, run_error = gh_api_get(f"repos/{owner}/{repo}/actions/runs/{run_id}")
    if run is None:
        not_found = "404" in run_error or "Not Found" in run_error
        write_skill_error(
            f"Run {run_id} not found" if not_found else f"Run read failed: {run_error}",
            2 if not_found else 3,
            error_type="NotFound" if not_found else "ApiError",
            output_format=fmt,
            script_name=_SCRIPT_NAME,
        )
        return 2 if not_found else 3

    jobs_payload, jobs_error = gh_api_get(
        f"repos/{owner}/{repo}/actions/runs/{run_id}/jobs?per_page=100"
    )
    jobs: list[dict] = []
    jobs_read = True
    jobs_capped = False
    if jobs_payload is None:
        jobs_read = False
    else:
        jobs = jobs_payload.get("jobs") or []
        if len(jobs) >= 100:
            # A busy workflow can paginate; say so rather than truncate silently.
            jobs_capped = True

    pending, pending_error = gh_api_get(
        f"repos/{owner}/{repo}/actions/runs/{run_id}/pending_deployments"
    )
    pending_deployments: list[dict] = []
    pending_read = True
    if pending is None:
        # 404 means no pending deployments on some API versions; permission
        # errors mean we cannot say. Distinguish neither here: mark unread.
        if "404" in pending_error or "Not Found" in pending_error:
            pending_deployments = []
        else:
            pending_read = False
    elif isinstance(pending, list):
        pending_deployments = [normalize_pending_deployment(dep) for dep in pending]

    data = {
        **normalize_run(run),
        "run_id": run_id,
        "jobs": [normalize_job(job) for job in jobs],
        "jobs_read": jobs_read,
        "jobs_capped": jobs_capped,
        "jobs_error": None if jobs_read else jobs_error,
        "pending_deployments": pending_deployments,
        "pending_deployments_read": pending_read,
        "waiting_on_environment_approval": (
            None if not pending_read else any(dep["reviewers"] for dep in pending_deployments)
        ),
    }

    summary = _build_summary(run, run_id, data, jobs_read, jobs_capped, pending_deployments)

    write_skill_output(
        data,
        output_format=fmt,
        human_summary=summary,
        status="WARNING" if not jobs_read else "PASS",
        script_name=_SCRIPT_NAME,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

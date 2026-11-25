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

Exit codes follow ADR-035:
    0 - Success
    2 - Usage, configuration, or not-found error
    3 - External service or API error
    4 - Auth error
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from skill_bootstrap import ensure_plugin_paths

ensure_plugin_paths(__file__, (".claude", "lib"))

from github_core.api import (
    assert_gh_authenticated,
    resolve_repo_params,
)
from github_core.output import (
    add_output_format_arg,
    get_output_format,
    write_skill_error,
    write_skill_output,
)

_SCRIPT_NAME = "get_workflow_run.py"


def _gh_api(endpoint: str) -> tuple[dict | list | None, str]:
    result = subprocess.run(
        ["gh", "api", endpoint],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        detail = (
            result.stderr.strip()
            or result.stdout.strip()
            or f"gh api {endpoint} failed with no stderr or stdout output"
        )
        return None, detail
    try:
        return json.loads(result.stdout), ""
    except json.JSONDecodeError as exc:
        return None, f"Failed to decode response for {endpoint}: {exc}"


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
    reviewer = dep.get("current_reviewer") or {}
    return {
        "environment": environment.get("name") if isinstance(environment, dict) else environment,
        "wait_minutes": dep.get("wait_timer"),
        "current_reviewer": reviewer.get("login") if isinstance(reviewer, dict) else None,
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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    fmt = get_output_format(args.output_format)

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo
    run_id = args.run_id

    run, run_error = _gh_api(f"repos/{owner}/{repo}/actions/runs/{run_id}")
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

    jobs_payload, jobs_error = _gh_api(
        f"repos/{owner}/{repo}/actions/runs/{run_id}/jobs?per_page=100"
    )
    jobs: list[dict] = []
    jobs_read = True
    if jobs_payload is None:
        jobs_read = False
    else:
        jobs = jobs_payload.get("jobs") or []
        if len(jobs) >= 100:
            # A busy workflow can paginate; say so rather than truncate silently.
            jobs_read = "capped"

    pending, pending_error = _gh_api(
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
        "run_id": run_id,
        "name": run.get("name"),
        "workflow_path": run.get("path"),
        "status": run.get("status"),
        "conclusion": run.get("conclusion"),
        "event": run.get("event"),
        "branch": run.get("head_branch"),
        "head_sha": run.get("head_sha"),
        "run_number": run.get("run_number"),
        "run_attempt": run.get("run_attempt"),
        "created_at": run.get("created_at"),
        "updated_at": run.get("updated_at"),
        "url": run.get("html_url"),
        "pull_requests": [
            {"number": pr.get("number"), "head_branch": (pr.get("head") or {}).get("ref")}
            for pr in run.get("pull_requests") or []
        ],
        "jobs": [normalize_job(job) for job in jobs],
        "jobs_read": jobs_read,
        "pending_deployments": pending_deployments,
        "pending_deployments_read": pending_read,
        "waiting_on_environment_approval": bool(pending_deployments),
    }

    failed_jobs = [job["name"] for job in data["jobs"] if job["conclusion"] == "failure"]
    summary_bits = [f"run {run_id}: {run.get('status')}/{run.get('conclusion') or 'pending'}"]
    if failed_jobs:
        summary_bits.append(f"failed jobs: {', '.join(failed_jobs[:5])}")
    if pending_deployments:
        envs = ", ".join(str(dep["environment"]) for dep in pending_deployments)
        summary_bits.append(f"waiting on environment approval: {envs}")

    write_skill_output(
        data,
        output_format=fmt,
        human_summary="; ".join(summary_bits),
        status="PASS",
        script_name=_SCRIPT_NAME,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

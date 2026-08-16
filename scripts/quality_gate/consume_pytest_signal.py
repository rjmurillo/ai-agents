#!/usr/bin/env python3
"""Consume the pytest.yml workflow verdict instead of re-running the suite.

Issue #4822: ``ai-pr-quality-gate.yml`` duplicated the full pytest execution
already performed by ``pytest.yml``. This script resolves the authoritative
verdict from ``pytest.yml`` and outputs ``pytest_status`` and
``pytest_summary`` in the same format ``run_pytest.py`` produced, so
downstream consumers (``generate_test_summary.py``, the external-signal gate)
are unchanged.

The resolution reuses ``resolve_pytest_signal.resolve()`` which queries the
GitHub API for the pytest.yml run matching the current PR head SHA, then
classifies its jobs by step names to distinguish a real executor from a
pass-through placeholder.

When pytest.yml has not completed yet (PENDING), this script retries with
exponential backoff up to a configurable deadline. If the deadline expires the
status remains PENDING, which the QA agent treats as informational rather than
blocking.

Input env vars:
    GITHUB_REPOSITORY  - owner/repo
    PR_NUMBER          - pull request number
    EXPECTED_HEAD_SHA  - 40 hex head sha the caller tested
    GITHUB_OUTPUT      - path to the GitHub Actions output file
    GH_TOKEN           - GitHub token for API calls

Exit codes (ADR-035):
    0 - status resolved and written (including PENDING/UNKNOWN, since this
        job is continue-on-error and must not change the workflow verdict)
    2 - configuration error (missing or invalid inputs)
"""

from __future__ import annotations

import argparse
import importlib
import math
import os
import sys
import time
from functools import partial
from pathlib import Path


# Import the resolution machinery from the shadow module.
# Supports both package-relative (pytest) and bare (script execution) paths.
def _import_resolve_module():  # noqa: ANN202
    try:
        return importlib.import_module(".resolve_pytest_signal", __package__)
    except (ImportError, TypeError):  # pragma: no cover - script execution path
        return importlib.import_module("resolve_pytest_signal")


_mod = _import_resolve_module()
EXIT_CONFIG = _mod.EXIT_CONFIG
EXIT_OK = _mod.EXIT_OK
STATUS_FAIL = _mod.STATUS_FAIL
STATUS_PASS = _mod.STATUS_PASS
STATUS_PENDING = _mod.STATUS_PENDING
STATUS_SKIPPED = _mod.STATUS_SKIPPED
STATUS_UNKNOWN = _mod.STATUS_UNKNOWN
REASON_NO_JOB = _mod.REASON_NO_JOB
Resolution = _mod.Resolution
resolve = _mod.resolve
run_gh = _mod.run_gh
sanitize = _mod.sanitize

_SUMMARY_TEMPLATES = {
    STATUS_PASS: "All tests passed (resolved from pytest.yml)",
    STATUS_FAIL: "Tests failed (resolved from pytest.yml)",
    STATUS_SKIPPED: "Tests skipped (no Python test inputs changed)",
    STATUS_PENDING: "pytest.yml has not completed yet",
}

DEFAULT_DEADLINE_SECONDS = 720.0
DEFAULT_POLL_INTERVAL = 15.0
MAX_POLL_INTERVAL = 60.0
BACKOFF_FACTOR = 1.5


def _wait_for_resolution(
    runner: object,
    *,
    repo: str,
    pr: str,
    expected_sha: str,
    workflow: str,
    job_name: str,
    deadline: float,
    poll_interval: float,
) -> Resolution:
    """Resolve with retries until non-PENDING or deadline expires."""
    start = time.monotonic()
    interval = poll_interval
    resolution = resolve(
        runner, repo=repo, pr=pr, expected_sha=expected_sha, workflow=workflow, job_name=job_name
    )

    def _is_transient(r: Resolution) -> bool:
        """PENDING or UNKNOWN/no-job are transient (job not yet created)."""
        if r.status == STATUS_PENDING:
            return True
        if r.status == STATUS_UNKNOWN and r.reason == REASON_NO_JOB:
            return True
        return False

    while _is_transient(resolution) and (time.monotonic() - start) < deadline:
        sleep_time = min(interval, deadline - (time.monotonic() - start))
        if sleep_time <= 0:
            break
        label = "pending" if resolution.status == STATUS_PENDING else "waiting for job creation"
        print(f"pytest.yml is {label}, waiting {sleep_time:.0f}s...", file=sys.stderr)
        time.sleep(sleep_time)
        interval = min(interval * BACKOFF_FACTOR, MAX_POLL_INTERVAL)
        resolution = resolve(
            runner,
            repo=repo,
            pr=pr,
            expected_sha=expected_sha,
            workflow=workflow,
            job_name=job_name,
        )
    return resolution


def format_summary(resolution: Resolution) -> str:
    """Return a one-line summary matching run_pytest.py's output convention."""
    template = _SUMMARY_TEMPLATES.get(resolution.status)
    if template:
        return template
    return f"pytest.yml resolved to {resolution.status}: {sanitize(resolution.reason)}"


def write_outputs(output_path: Path, status: str, summary: str) -> None:
    """Append pytest_status and pytest_summary to GITHUB_OUTPUT."""
    with output_path.open("a", encoding="utf-8") as handle:
        handle.write(f"pytest_status={status}\n")
        handle.write(f"pytest_summary={summary}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--pr", default=os.environ.get("PR_NUMBER", ""))
    parser.add_argument(
        "--expected-head-sha",
        default=os.environ.get("EXPECTED_HEAD_SHA", ""),
    )
    parser.add_argument("--workflow", default="pytest.yml")
    parser.add_argument("--job-name", default="Run Python Tests")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument(
        "--deadline",
        type=float,
        default=float(os.environ.get("PYTEST_SIGNAL_DEADLINE", DEFAULT_DEADLINE_SECONDS)),
        help="Maximum seconds to wait for pytest.yml to complete.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=DEFAULT_POLL_INTERVAL,
        help="Initial poll interval in seconds.",
    )
    args = parser.parse_args(argv)

    repo = args.repo.strip()
    pr = args.pr.strip()
    expected_sha = args.expected_head_sha.strip().lower()

    # Validation
    import re
    import subprocess

    if not re.match(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$", repo):
        print("error: --repo or GITHUB_REPOSITORY must be owner/repo", file=sys.stderr)
        return EXIT_CONFIG
    if not re.match(r"^[1-9][0-9]{0,9}$", pr):
        print("error: --pr or PR_NUMBER must be a positive integer", file=sys.stderr)
        return EXIT_CONFIG

    # Resolve SHA from PR when not provided (e.g. workflow_dispatch)
    if not expected_sha:
        try:
            result = subprocess.run(
                ["gh", "api", f"repos/{repo}/pulls/{pr}", "--jq", ".head.sha"],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=True,
            )
            expected_sha = result.stdout.strip().lower()
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            print(f"error: failed to resolve head SHA for PR #{pr}: {exc}", file=sys.stderr)
            return EXIT_CONFIG

    if not re.match(r"^[0-9a-f]{40}$", expected_sha):
        print(
            "error: --expected-head-sha or EXPECTED_HEAD_SHA must be 40 hex characters",
            file=sys.stderr,
        )
        return EXIT_CONFIG
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        print("error: --timeout must be a finite positive number", file=sys.stderr)
        return EXIT_CONFIG

    runner = partial(run_gh, timeout=args.timeout)
    resolution = _wait_for_resolution(
        runner,
        repo=repo,
        pr=pr,
        expected_sha=expected_sha,
        workflow=args.workflow,
        job_name=args.job_name,
        deadline=args.deadline,
        poll_interval=args.poll_interval,
    )

    status = resolution.status
    summary = format_summary(resolution)
    print(f"Resolved pytest status: {status}")
    print(f"Summary: {summary}")
    print(f"Reason: {resolution.reason}")

    github_output = os.environ.get("GITHUB_OUTPUT")
    if not github_output:
        print("note: GITHUB_OUTPUT is unset, outputs printed only", file=sys.stderr)
        return EXIT_OK
    write_outputs(Path(github_output), status, summary)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())

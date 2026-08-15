#!/usr/bin/env python3
"""Resolve the authoritative pytest.yml verdict for a pull request head.

Issue #4822 phase 1 (shadow mode). ``ai-pr-quality-gate.yml`` runs the whole
pytest suite a second time so the QA agent has a pass/fail string; this module
reads the verdict ``pytest.yml`` already produced for the same head commit so
that duplicate can be retired later. It only OBSERVES: nothing consumes its
outputs and the local run stays authoritative.

Step names, not check names, decide the verdict. Mirrored from
``.github/workflows/pytest.yml`` and verified with ``yaml.safe_load`` on
2026-08-09: jobs ``test`` and ``skip-tests`` BOTH declare ``name: Run Python
Tests``, ``test`` alone owns ``- name: Run pytest``, and ``skip-tests`` alone
owns ``- name: Skip tests (no Python test inputs changed)``. ``skip-tests``
exists because branch protection requires SUCCESS, not SKIPPED, for a required
check (issue #1168), so a green "Run Python Tests" means either "the suite
passed" or "the suite never ran" and only the step names tell those apart. Live
run 31360441685 is the proof: run conclusion and both job conclusions are
``success`` while the executor's ``Run pytest`` step is ``skipped``. That shape
and four other replayed runs are tabulated in
``.agents/qa/pr-4845-shadow-pytest-signal-test-report.md`` and pinned as
fixtures in ``tests/quality_gate/test_resolve_pytest_signal.py``. The rules
stricter than the name match live with the code that applies them: freshness in
``resolve``, pull request binding in ``binds_to_pr``, the never-ran executor in
``job_status``, worst-sibling escalation in ``aggregate``.

Exit codes (ADR-035): 0 once a status is resolved and emitted, which is EVERY
resolution outcome including UNKNOWN from an API failure, because a shadow must
never change the job's verdict; 2 for a config error (bad repo, PR number, SHA,
or workflow file name), which is a wiring bug rather than a signal.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path

EXIT_OK = 0
EXIT_CONFIG = 2

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_SKIPPED = "SKIPPED"
STATUS_PENDING = "PENDING"
STATUS_STALE = "STALE"
STATUS_CANCELLED = "CANCELLED"
STATUS_UNKNOWN = "UNKNOWN"
STATUS_UNCLASSIFIED = "UNCLASSIFIED"

# Worst wins. A sibling failure must never be masked by a sibling success, and
# PASS is the only status that asserts the suite actually ran and was green.
_SEVERITY = {
    STATUS_PASS: 0,
    STATUS_SKIPPED: 1,
    STATUS_UNCLASSIFIED: 2,
    STATUS_UNKNOWN: 3,
    STATUS_PENDING: 4,
    STATUS_CANCELLED: 5,
    STATUS_FAIL: 6,
}

AGREE = "AGREE"
DISAGREE = "DISAGREE"
UNCOMPARED = "UNCOMPARED"
# One greppable token per invocation, so "how many shadow samples did we
# collect" is answerable from run logs without a consumer reading the outputs.
SAMPLE_MARKER = "shadow-pytest-sample"
# Vocabulary of run_pytest.py, the local step this shadow is compared against.
LOCAL_STATUSES = frozenset({STATUS_PASS, STATUS_FAIL, STATUS_SKIPPED, "ERROR"})

DEFAULT_WORKFLOW = "pytest.yml"
DEFAULT_JOB_NAME = "Run Python Tests"
EXECUTOR_STEP_NAME = "Run pytest"
GATE_STEP_NAME = "Require test and coverage success"
PASS_THROUGH_STEP_NAME = "Skip tests (no Python test inputs changed)"

KIND_EXECUTOR = "executor"
KIND_PASS_THROUGH = "pass-through"
KIND_UNCLASSIFIED = "unclassified"

# Insertion order IS tier order: the first tier holding a job decides. The value
# is the status a tier reports for a job that completed green, because an
# executor ran the suite, a pass-through only stood in for it, and an
# unclassified job proves nothing.
_GREEN_STATUS = {
    KIND_EXECUTOR: STATUS_PASS,
    KIND_PASS_THROUGH: STATUS_SKIPPED,
    KIND_UNCLASSIFIED: STATUS_UNCLASSIFIED,
}

# Statuses a lower-tier sibling may hold without disturbing the deciding tier.
# UNCLASSIFIED means the sibling completed successfully but proves nothing.
BENIGN_SIBLING_STATUSES = frozenset({STATUS_PASS, STATUS_SKIPPED, STATUS_UNCLASSIFIED})

REASON_STALE_HEAD = "the expected head sha is not the live pull request head"
REASON_LIVE_HEAD_UNREADABLE = "the live pull request head could not be read"
REASON_LIVE_HEAD_MALFORMED = "the live pull request head is not a 40 hex sha"
REASON_RUNS_UNREADABLE = "the pytest workflow run list could not be read"
REASON_NO_RUN = "no pytest pull_request run exists for the expected head sha"
REASON_RUN_NOT_BOUND = (
    "the pytest runs for the expected head sha belong to a different pull request"
)
REASON_JOBS_UNREADABLE = "the pytest workflow job list could not be read"
REASON_NO_JOB = "the run has no job matching the pytest check name"

_SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{40}$")
_REPO_PATTERN = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")
_PR_PATTERN = re.compile(r"^[1-9][0-9]{0,9}$")
_WORKFLOW_PATTERN = re.compile(r"^[A-Za-z0-9._-]+\.ya?ml$")
_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9 ,.()/_-]")

# GitHub's completed-conclusion vocabulary. An absent key is a gap in the table,
# not a decided mapping, so it resolves to UNKNOWN and says so on stderr
# (testing rule 15: a silent catch-all makes matching entries dead).
_CONCLUSION_STATUS = {
    "success": STATUS_PASS,
    "failure": STATUS_FAIL,
    "timed_out": STATUS_FAIL,
    "startup_failure": STATUS_FAIL,
    "cancelled": STATUS_CANCELLED,
    "skipped": STATUS_SKIPPED,
}

GhRunner = Callable[[Sequence[str]], "subprocess.CompletedProcess[str]"]


def sanitize(text: str, limit: int = 160) -> str:
    """Collapse whitespace and drop every character outside the safe set."""
    return _UNSAFE_CHARS.sub("", " ".join(text.split()))[:limit]


def _text(mapping: Mapping[str, object], key: str) -> str:
    """Return ``mapping[key]`` as text, treating an explicit null as absent."""
    value = mapping.get(key)
    return "" if value is None else str(value)


@dataclass(frozen=True, slots=True)
class Resolution:
    status: str
    reason: str


@dataclass(frozen=True, slots=True)
class Run:
    run_id: int
    attempt: int
    started_at: str


@dataclass(frozen=True, slots=True)
class Job:
    name: str
    status: str
    conclusion: str
    steps: tuple[tuple[str, str], ...]

    def step_conclusion(self, step_name: str) -> str | None:
        """Return the named step's conclusion, or None when it is absent."""
        for name, conclusion in self.steps:
            if name == step_name:
                return conclusion
        return None


def run_gh(argv: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
    """Invoke ``gh`` with an argument vector. No shell, ever."""
    return subprocess.run(
        ["gh", *argv],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def gh_json(runner: GhRunner, path: str, label: str) -> Mapping[str, object] | None:
    """Return the JSON object from ``gh api <path>``, or None when unusable.

    A 403, a missing ``gh``, a timeout, malformed JSON, and a non-object body
    are one outcome to the caller: no usable data. The subprocess stderr is
    never printed, because an API error body can carry text this module must not
    place in the log.
    """
    try:
        completed = runner(["api", path])
    except (OSError, subprocess.SubprocessError):
        print(f"gh api could not be launched for {label}", file=sys.stderr)
        return None
    if completed.returncode != 0:
        print(f"gh api returned exit {completed.returncode} for {label}", file=sys.stderr)
        return None
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        print(f"gh api returned invalid JSON for {label}", file=sys.stderr)
        return None
    return payload if isinstance(payload, Mapping) else None


def binds_to_pr(item: Mapping[str, object], pr: str, repo: str) -> bool:
    """Whether a run provably belongs to the requested pull request.

    A head SHA alone does not identify a pull request, so matching on SHA would
    let one pull request's verdict be reported for another. Primary binding is
    ``pull_requests[]``, which GitHub empties once a pull request closes and for
    fork runs, so an empty list is normal and cannot be a failure by itself. The
    fallback then requires same-repo against the already-validated repo
    constant, which a fork by definition cannot satisfy. Residual risk,
    accepted: under that fallback two same-repo pull requests sharing one head
    commit are indistinguishable, but both ran the identical tree.
    """
    linked = item.get("pull_requests")
    if isinstance(linked, list) and linked:
        return any(isinstance(entry, Mapping) and _text(entry, "number") == pr for entry in linked)
    head_repo = item.get("head_repository")
    head_name = _text(head_repo, "full_name") if isinstance(head_repo, Mapping) else ""
    return head_name.casefold() == repo.casefold()


def parse_runs(
    payload: Mapping[str, object], expected_sha: str, *, pr: str, repo: str
) -> tuple[tuple[Run, ...], int] | None:
    """Return runs for ``expected_sha`` bound to ``pr`` and the count that were
    not, or None when the payload is unusable.

    Push runs are dropped here as well as in the query string, because the API
    filter is a request and this filter is a guarantee. Runs matching the SHA
    that bind to no pull request are counted rather than silently dropped, so
    the caller can tell "nothing has run yet" from "something ran for another".
    """
    raw = payload.get("workflow_runs")
    if not isinstance(raw, list):
        return None
    runs: list[Run] = []
    rejected = 0
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        run_id = _text(item, "id")
        if (
            _text(item, "event") != "pull_request"
            or _text(item, "head_sha").lower() != expected_sha
            or not run_id.isdigit()
        ):
            continue
        if not binds_to_pr(item, pr, repo):
            rejected += 1
            continue
        attempt = _text(item, "run_attempt")
        started = _text(item, "run_started_at") or _text(item, "created_at")
        runs.append(Run(int(run_id), int(attempt) if attempt.isdigit() else 1, started))
    return tuple(runs), rejected


def select_latest_run(runs: Sequence[Run]) -> Run:
    """Return the newest run: start time, then attempt, then run id, because
    start time orders separate runs, attempt orders re-runs of one, and GitHub
    run ids increase over time.
    """
    return max(runs, key=lambda run: (run.started_at, run.attempt, run.run_id))


def parse_job(item: Mapping[str, object]) -> Job:
    """Build a Job from one API entry, tolerating nulls and missing steps."""
    raw = item.get("steps")
    steps = raw if isinstance(raw, list) else ()
    return Job(
        _text(item, "name"),
        _text(item, "status"),
        _text(item, "conclusion"),
        tuple((_text(s, "name"), _text(s, "conclusion")) for s in steps if isinstance(s, Mapping)),
    )


def classify(job: Job) -> str:
    """Classify a job as executor, pass-through, or unclassified."""
    if job.step_conclusion(EXECUTOR_STEP_NAME) is not None:
        return KIND_EXECUTOR
    if job.step_conclusion(GATE_STEP_NAME) is not None:
        return KIND_EXECUTOR
    if job.step_conclusion(PASS_THROUGH_STEP_NAME) is not None:
        return KIND_PASS_THROUGH
    return KIND_UNCLASSIFIED


def job_status(job: Job, kind: str) -> str:
    """Resolve one job to a status, given the tier ``classify`` placed it in."""
    if job.status != "completed":
        return STATUS_PENDING
    status = _CONCLUSION_STATUS.get(job.conclusion)
    if status is None:
        print(f"note unrecognized job conclusion {sanitize(job.conclusion, 32)}", file=sys.stderr)
        return STATUS_UNKNOWN
    if status != STATUS_PASS:
        return status
    if kind == KIND_EXECUTOR and job.step_conclusion(EXECUTOR_STEP_NAME) == "skipped":
        return STATUS_SKIPPED
    return _GREEN_STATUS[kind]


def aggregate(jobs: Sequence[Job]) -> Resolution:
    """Reduce same-named jobs to one status, executors first.

    The first non-empty tier DECIDES, so a pass-through sibling can neither
    rescue a failing suite nor manufacture a PASS, and the best a pass-through
    tier can say is SKIPPED. Deciding is not silencing: a lower tier cannot
    improve the verdict but can still worsen it, because every job here carries
    the same required check name, so a failed, cancelled, or still-running
    sibling means that check is not green however well the executor did. Without
    that escalation an executor PASS masked a pass-through FAIL and this
    reported a green check GitHub was showing as red.
    """
    if not jobs:
        return Resolution(STATUS_UNKNOWN, REASON_NO_JOB)
    populated = [
        (kind, [job_status(job, kind) for job in jobs if classify(job) == kind])
        for kind in _GREEN_STATUS
    ]
    tiers = [tier for tier in populated if tier[1]]
    kind, deciding = tiers[0]
    base = max(deciding, key=_SEVERITY.__getitem__)
    unhealthy = [
        status
        for _, statuses in tiers[1:]
        for status in statuses
        if status not in BENIGN_SIBLING_STATUSES
    ]
    status = max([base, *unhealthy], key=_SEVERITY.__getitem__)
    if status == STATUS_UNCLASSIFIED:
        status = STATUS_UNKNOWN
    if base == STATUS_UNCLASSIFIED:
        base = STATUS_UNKNOWN
    reason = f"{len(deciding)} {kind} job(s) of {len(jobs)} matching job(s) resolve to {base}"
    if unhealthy:
        reason += f", raised to {status} by {len(unhealthy)} unhealthy sibling job(s)"
    return Resolution(status, reason)


def resolve(
    runner: GhRunner, *, repo: str, pr: str, expected_sha: str, workflow: str, job_name: str
) -> Resolution:
    """Resolve the pytest workflow verdict for ``expected_sha``.

    Freshness is settled first: the expected SHA must still be the live head of
    the pull request, so a stale head short-circuits before any run is listed
    and no verdict for a superseded commit can be read. GitHub's lag in updating
    ``refs/pull/<n>/head`` after a push surfaces as STALE, never a false PASS.
    """
    expected_sha = expected_sha.lower()
    head = gh_json(runner, f"repos/{repo}/git/ref/pull/{pr}/head", "the live head ref")
    if head is None:
        return Resolution(STATUS_UNKNOWN, REASON_LIVE_HEAD_UNREADABLE)
    obj = head.get("object")
    live_sha = _text(obj, "sha") if isinstance(obj, Mapping) else ""
    if not _SHA_PATTERN.match(live_sha):
        return Resolution(STATUS_UNKNOWN, REASON_LIVE_HEAD_MALFORMED)
    if live_sha.lower() != expected_sha:
        return Resolution(STATUS_STALE, REASON_STALE_HEAD)

    runs_path = (
        f"repos/{repo}/actions/workflows/{workflow}/runs"
        f"?event=pull_request&head_sha={expected_sha}&per_page=100"
    )
    listing = gh_json(runner, runs_path, "the workflow runs")
    scan = None if listing is None else parse_runs(listing, expected_sha, pr=pr, repo=repo)
    if scan is None:
        return Resolution(STATUS_UNKNOWN, REASON_RUNS_UNREADABLE)
    bound, rejected = scan
    if not bound:
        if rejected:
            return Resolution(STATUS_UNKNOWN, REASON_RUN_NOT_BOUND)
        return Resolution(STATUS_PENDING, REASON_NO_RUN)

    run = select_latest_run(bound)
    jobs_path = f"repos/{repo}/actions/runs/{run.run_id}/attempts/{run.attempt}/jobs?per_page=100"
    payload = gh_json(runner, jobs_path, "the run jobs")
    raw = None if payload is None else payload.get("jobs")
    if not isinstance(raw, list):
        return Resolution(STATUS_UNKNOWN, REASON_JOBS_UNREADABLE)
    jobs = [parse_job(item) for item in raw if isinstance(item, Mapping)]
    return aggregate([job for job in jobs if job.name == job_name])


def compare(status: str, local_status: str) -> tuple[str, str]:
    """Compare the resolved status against the local run's status."""
    local = sanitize(local_status, 32).strip().upper()
    if not local:
        return UNCOMPARED, "no local pytest status was supplied"
    if local not in LOCAL_STATUSES:
        return UNCOMPARED, "the local pytest status token is not recognized"
    if local == status:
        return AGREE, f"both report {status}"
    return DISAGREE, f"the resolver reports {status} and the local run reports {local}"


def emit(resolution: Resolution, agreement: str, agreement_reason: str) -> dict[str, str]:
    """Print the shadow result and return the sanitized output pairs.

    A shadow that only speaks when it disagrees is indistinguishable from one
    that never ran, so a workflow collecting zero samples would look exactly
    like a healthy one. Every invocation therefore prints one ``SAMPLE_MARKER``
    notice, making the sample count greppable from run logs, and anything short
    of agreement warns rather than passing quietly. Every printed value comes
    from this module's fixed vocabulary, so the line cannot be forged by API
    data.
    """
    compared = agreement in (AGREE, DISAGREE)
    outputs = {
        "shadow_pytest_status": resolution.status,
        "shadow_pytest_reason": sanitize(resolution.reason),
        "shadow_pytest_agreement": agreement,
        "shadow_pytest_compared": "true" if compared else "false",
    }
    for key, value in outputs.items():
        print(f"{key}={value}")
    print(
        f"::notice::{SAMPLE_MARKER} status={resolution.status} "
        f"agreement={agreement} compared={outputs['shadow_pytest_compared']}"
    )
    if agreement != AGREE:
        problem = "disagreement" if agreement == DISAGREE else "collected no sample"
        print(
            f"::warning::Shadow pytest signal {problem}. "
            f"{sanitize(agreement_reason)}. {sanitize(resolution.reason)}"
        )
    return outputs


def _config_error(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return EXIT_CONFIG


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--pr", default=os.environ.get("PR_NUMBER", ""))
    parser.add_argument(
        "--expected-head-sha",
        default=os.environ.get("EXPECTED_HEAD_SHA", ""),
        help="The 40 hex head sha the caller believes it tested.",
    )
    parser.add_argument("--local-status", default=os.environ.get("LOCAL_PYTEST_STATUS", ""))
    parser.add_argument("--workflow", default=DEFAULT_WORKFLOW)
    parser.add_argument("--job-name", default=DEFAULT_JOB_NAME)
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args(argv)
    repo = args.repo.strip()
    pr = args.pr.strip()
    expected_sha = args.expected_head_sha.strip().lower()
    workflow = args.workflow.strip()
    job_name = args.job_name

    if not _REPO_PATTERN.match(repo):
        return _config_error("--repo or GITHUB_REPOSITORY must be owner/repo")
    if not _PR_PATTERN.match(pr):
        return _config_error("--pr or PR_NUMBER must be a positive integer")
    if not _SHA_PATTERN.match(expected_sha):
        return _config_error("--expected-head-sha or EXPECTED_HEAD_SHA must be 40 hex characters")
    if not _WORKFLOW_PATTERN.match(workflow):
        return _config_error("--workflow must be a workflow file name")
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        return _config_error("--timeout must be a finite positive number")

    runner = partial(run_gh, timeout=args.timeout)
    resolution = resolve(
        runner, repo=repo, pr=pr, expected_sha=expected_sha, workflow=workflow, job_name=job_name
    )
    agreement, agreement_reason = compare(resolution.status, args.local_status)
    outputs = emit(resolution, agreement, agreement_reason)

    github_output = os.environ.get("GITHUB_OUTPUT")
    if not github_output:
        print("note GITHUB_OUTPUT is unset, outputs were printed only", file=sys.stderr)
        return EXIT_OK
    with Path(github_output).open("a", encoding="utf-8") as handle:
        for key, value in outputs.items():
            handle.write(f"{key}={value}\n")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())

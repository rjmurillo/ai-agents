#!/usr/bin/env python3
"""Resolve the authoritative pytest.yml verdict for a pull request head.

Issue #4822 phase 1 (shadow mode). ``ai-pr-quality-gate.yml`` runs the whole
pytest suite a second time so the QA agent has a pass/fail string. This module
reads the verdict that ``pytest.yml`` already produced for the same head commit
so the duplicate run can be retired later. This phase only OBSERVES: it emits a
status alongside the local run and warns when the two disagree. Nothing
consumes its outputs and the local run stays authoritative.

Canonical source mirrored, read 2026-08-09 from
``.github/workflows/pytest.yml``. Two jobs declare the SAME check name, which
is why a name match alone cannot decide anything:

* ``test`` (line 111) -> ``name: Run Python Tests`` (line 112), and its
  suite-executing step is ``- name: Run pytest`` (line 260).
* ``skip-tests`` (line 427) -> ``name: Run Python Tests`` (line 428), whose
  only real step is
  ``- name: Skip tests (no Python test inputs changed)`` (line 441).

``skip-tests`` exists because branch protection requires SUCCESS, not SKIPPED,
for a required check (pytest.yml comment above line 427, issue #1168). So a
green "Run Python Tests" means either "the suite passed" or "the suite never
ran", and the ONLY way to tell them apart is the step names. Verified with
``yaml.safe_load`` over that file on 2026-08-09: those two jobs are the only
ones carrying the name, ``Run pytest`` appears in ``test`` alone, and
``Skip tests (no Python test inputs changed)`` appears in ``skip-tests`` alone.

Divergence from the canonical source (stricter than a plain name match):

* An executor job whose ``Run pytest`` step is itself ``skipped`` reports
  SKIPPED, not PASS. That step carries
  ``if: steps.should-run.outputs.skip != 'true'`` (pytest.yml line 262), so the
  job can succeed with the suite never executed.
* Where duplicate job names disagree, the worst outcome wins. A sibling failure
  is never masked by a sibling success. The tier that decides the verdict can
  only be overruled downward: a failed, cancelled, or still-running sibling
  carrying the same required check name escalates the result, because that
  check is not green in GitHub no matter how well the executor did.
* PASS is claimed only from an executor job. A pass-through-only run is
  SKIPPED, never PASS.
* A run must bind to the requested pull request number, not merely to the head
  SHA, because one commit can head several pull requests at once.

Payload shapes observed against the live API on 2026-08-09, each confirmed to
resolve as stated by running this module's parser over the captured response:

* Run 31360441685: run conclusion ``success`` and BOTH "Run Python Tests" jobs
  ``success``, yet the executor's ``Run pytest`` step is ``skipped``. Resolves
  to SKIPPED. This is the exact commit-was-never-tested case that a run-level
  or job-level conclusion read would have reported as PASS.
* Run 31355229018: one executor job green with the suite actually run, one
  pass-through job ``skipped`` with an EMPTY step list. Resolves to PASS.
* Run 31362376502: both jobs ``cancelled`` with empty step lists, so both are
  unclassified. Resolves to CANCELLED, never PASS.
* Run 31361938848: executor still running, ``conclusion: null`` and its
  ``Run pytest`` step conclusion null. Resolves to PENDING.
* Run 31360447277: ``startup_failure``, the jobs list is empty. Resolves to
  UNKNOWN, because no job means no verdict to read.

Note from those shapes: a job's ``steps`` list is empty when the job itself was
skipped or cancelled, so step-name classification silently degrades to
"unclassified" rather than mis-reading such a job as an executor.

Freshness rules:

* The expected head SHA must be exactly 40 hex characters.
* The live pull request head is re-read from ``refs/pull/<n>/head`` in the base
  repository. A mismatch is STALE, because the workflow payload's SHA can be
  several pushes behind by the time this runs.
* Only ``event == "pull_request"`` runs count. ``pytest.yml`` also triggers on
  ``push`` (line 19) and a push run of the same commit has a different job set,
  so accepting one would report a verdict for a different check.
* A run must also bind to the requested pull request. See ``binds_to_pr``.

Permissions. Listing workflow runs and jobs needs ``actions: read``. The live
head is read through ``GET /repos/{owner}/{repo}/git/ref/pull/{n}/head``, a Git
references endpoint covered by ``contents: read``, which the calling job
already holds. That is why no ``pull-requests`` scope is added. Known limit:
``refs/pull/<n>/head`` is updated by GitHub shortly after a push, so a race
window reports the previous head, which surfaces as STALE, never as a false
PASS.

Output safety. Every emitted reason is built from the fixed vocabulary in this
module plus integers and validated SHAs. No branch name, commit message, run
title, or other fork-controlled text is ever read into an output, and
``sanitize`` strips anything outside ``[A-Za-z0-9 ,.()/_-]`` and collapses
whitespace as a second line of defence, so no value can forge a ``::workflow``
command or inject a newline into ``GITHUB_OUTPUT``.

Input env vars (all overridable by the matching CLI flag):
    GITHUB_REPOSITORY   - ``owner/repo``.
    PR_NUMBER           - pull request number.
    EXPECTED_HEAD_SHA   - 40 hex head SHA the caller believes it tested.
    LOCAL_PYTEST_STATUS - status from the local ``Run pytest`` step.
    GITHUB_OUTPUT       - optional. Outputs are written when set.

Outputs (named apart from the existing pytest_status/pytest_summary so no
current consumer can pick them up by accident):
    shadow_pytest_status     - the resolved status.
    shadow_pytest_reason     - the sanitized fixed-vocabulary reason.
    shadow_pytest_agreement  - AGREE, DISAGREE, or UNCOMPARED.
    shadow_pytest_compared   - "true" only when a real comparison happened, so
                               collected samples can be counted rather than
                               assumed. See ``emit`` for why that matters.

Exit codes (ADR-035):
    0 - a status was resolved and emitted. EVERY resolution outcome exits 0,
        including UNKNOWN from an API failure, because this step observes and
        must never change the job's verdict while in shadow mode.
    2 - config error. The invocation itself is invalid (bad repo, PR number,
        SHA, or workflow file name), which is a wiring bug, not a signal.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
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

# Worst wins. A sibling failure must never be masked by a sibling success, and
# PASS is the only status that asserts the suite actually ran and was green.
_SEVERITY = {
    STATUS_PASS: 0,
    STATUS_SKIPPED: 1,
    STATUS_UNKNOWN: 2,
    STATUS_PENDING: 3,
    STATUS_CANCELLED: 4,
    STATUS_FAIL: 5,
}

AGREE = "AGREE"
DISAGREE = "DISAGREE"
UNCOMPARED = "UNCOMPARED"

# One greppable token per invocation, so "how many shadow samples did we
# collect" is answerable from run logs without a consumer reading the outputs.
SAMPLE_MARKER = "shadow-pytest-sample"

# Vocabulary of scripts/quality_gate/run_pytest.py, the local step this shadow
# signal is compared against.
LOCAL_STATUSES = frozenset({STATUS_PASS, STATUS_FAIL, STATUS_SKIPPED, "ERROR"})

DEFAULT_WORKFLOW = "pytest.yml"
DEFAULT_JOB_NAME = "Run Python Tests"
EXECUTOR_STEP_NAME = "Run pytest"
PASS_THROUGH_STEP_NAME = "Skip tests (no Python test inputs changed)"

KIND_EXECUTOR = "executor"
KIND_PASS_THROUGH = "pass-through"
KIND_UNCLASSIFIED = "unclassified"

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

# GitHub's completed-conclusion vocabulary. An absent key is a gap in the
# table, not a decided mapping, so it resolves to UNKNOWN and says so on
# stderr (testing rule 15: a silent catch-all makes matching entries dead).
_CONCLUSION_STATUS = {
    "success": STATUS_PASS,
    "failure": STATUS_FAIL,
    "timed_out": STATUS_FAIL,
    "startup_failure": STATUS_FAIL,
    "cancelled": STATUS_CANCELLED,
    "skipped": STATUS_SKIPPED,
}

GhRunner = Callable[[Sequence[str]], "subprocess.CompletedProcess[str]"]

__all__ = [
    "Job",
    "Resolution",
    "Run",
    "RunScan",
    "aggregate",
    "binds_to_pr",
    "classify",
    "compare",
    "main",
    "parse_runs",
    "resolve",
    "sanitize",
    "select_latest_run",
]


def sanitize(text: str, limit: int = 160) -> str:
    """Collapse whitespace and drop every character outside the safe set."""

    return _UNSAFE_CHARS.sub("", " ".join(text.split()))[:limit]


def _text(mapping: Mapping[str, object], key: str) -> str:
    """Return ``mapping[key]`` as text, treating an explicit null as absent."""

    value = mapping.get(key)
    return "" if value is None else str(value)


@dataclass(frozen=True, slots=True)
class Resolution:
    """A resolved status and the fixed-vocabulary reason behind it."""

    status: str
    reason: str


@dataclass(frozen=True, slots=True)
class Run:
    """The identity of one workflow run attempt."""

    run_id: int
    attempt: int
    started_at: str


@dataclass(frozen=True, slots=True)
class Job:
    """One job of a run, with the step names needed to classify it."""

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


def gh_json(runner: GhRunner, path: str, label: str) -> tuple[bool, object]:
    """Return ``(ok, payload)`` for ``gh api <path>``.

    A 403, a missing ``gh``, a timeout, and malformed JSON are all the same
    outcome to the caller: no usable data. The subprocess stderr is never
    printed, because an API error body can carry text this module must not
    place in the log.
    """

    try:
        completed = runner(["api", path])
    except (OSError, subprocess.SubprocessError):
        print(f"gh api could not be launched for {label}", file=sys.stderr)
        return False, None
    if completed.returncode != 0:
        print(f"gh api returned exit {completed.returncode} for {label}", file=sys.stderr)
        return False, None
    try:
        return True, json.loads(completed.stdout)
    except json.JSONDecodeError:
        print(f"gh api returned invalid JSON for {label}", file=sys.stderr)
        return False, None


def fetch_live_head(runner: GhRunner, repo: str, pr: str) -> tuple[str, Resolution | None]:
    """Re-read the pull request head from ``refs/pull/<pr>/head``."""

    ok, payload = gh_json(runner, f"repos/{repo}/git/ref/pull/{pr}/head", "the live head ref")
    if not ok or not isinstance(payload, Mapping):
        return "", Resolution(STATUS_UNKNOWN, REASON_LIVE_HEAD_UNREADABLE)
    obj = payload.get("object")
    sha = _text(obj, "sha") if isinstance(obj, Mapping) else ""
    if not _SHA_PATTERN.match(sha):
        return "", Resolution(STATUS_UNKNOWN, REASON_LIVE_HEAD_MALFORMED)
    return sha.lower(), None


def binds_to_pr(item: Mapping[str, object], pr: str, repo: str) -> bool:
    """Whether a run provably belongs to the requested pull request.

    A head SHA alone does not identify a pull request. The same commit can be
    the head of several pull requests at once, so matching on SHA would let one
    pull request's verdict be reported for another.

    Primary binding is ``pull_requests[]``, which GitHub populates with the
    pull requests a run belongs to. Observed live on 2026-08-10: runs for the
    open pull requests 4832, 4833, 4834, and 4817 each carried exactly their
    own number, and every run belonging to the merged pull request 4819
    carried an EMPTY list. GitHub empties that array once the pull request
    closes, and it is empty for fork runs, so an empty list is normal and
    cannot be treated as a failure by itself.

    The fallback for an empty list proves the run is same-repo by comparing
    ``head_repository.full_name`` against the repository this module was
    configured with. That is a comparison, never an ingestion: the value is
    tested for equality with an already-validated constant and is never
    emitted, stored, or used to build a request. A fork cannot satisfy it,
    because a fork's full name is by definition not the upstream's.

    Residual risk, accepted and bounded: when the array is empty, two same-repo
    pull requests sharing one head commit are indistinguishable here. Both
    would have run the identical tree, and the caller has already proved this
    SHA is the live head of the requested pull request, so the verdict still
    describes the code under test.
    """

    linked = item.get("pull_requests")
    if isinstance(linked, list) and linked:
        return any(isinstance(entry, Mapping) and _text(entry, "number") == pr for entry in linked)
    head_repo = item.get("head_repository")
    head_name = _text(head_repo, "full_name") if isinstance(head_repo, Mapping) else ""
    return head_name.casefold() == repo.casefold()


@dataclass(frozen=True, slots=True)
class RunScan:
    """Runs bound to the requested pull request, and how many did not bind."""

    bound: tuple[Run, ...]
    rejected: int


def parse_runs(payload: object, expected_sha: str, *, pr: str, repo: str) -> RunScan | None:
    """Return the runs for ``expected_sha`` bound to ``pr``, or None if unusable.

    Push runs are dropped here as well as in the query string, because the API
    filter is a request and this filter is a guarantee. Runs that match the SHA
    but cannot be bound to this pull request are counted rather than silently
    dropped, so the caller can tell "nothing has run yet" apart from "something
    ran for a different pull request".
    """

    if not isinstance(payload, Mapping):
        return None
    raw = payload.get("workflow_runs")
    if not isinstance(raw, list):
        return None
    runs: list[Run] = []
    rejected = 0
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        if _text(item, "event") != "pull_request":
            continue
        if _text(item, "head_sha").lower() != expected_sha:
            continue
        run_id = _text(item, "id")
        if not run_id.isdigit():
            continue
        if not binds_to_pr(item, pr, repo):
            rejected += 1
            continue
        attempt = _text(item, "run_attempt")
        started = _text(item, "run_started_at") or _text(item, "created_at")
        runs.append(
            Run(
                run_id=int(run_id),
                attempt=int(attempt) if attempt.isdigit() else 1,
                started_at=started,
            )
        )
    return RunScan(bound=tuple(runs), rejected=rejected)


def select_latest_run(runs: Sequence[Run]) -> Run:
    """Return the newest run, preferring the highest attempt on a tie.

    Start time orders separate runs, attempt orders re-runs of one run, and the
    run id breaks a remaining tie because GitHub run ids increase over time.
    """

    return max(runs, key=lambda run: (run.started_at, run.attempt, run.run_id))


def parse_job(item: Mapping[str, object]) -> Job:
    """Build a Job from one API entry, tolerating nulls and missing steps."""

    raw_steps = item.get("steps")
    steps: tuple[tuple[str, str], ...] = ()
    if isinstance(raw_steps, list):
        steps = tuple(
            (_text(step, "name"), _text(step, "conclusion"))
            for step in raw_steps
            if isinstance(step, Mapping)
        )
    return Job(
        name=_text(item, "name"),
        status=_text(item, "status"),
        conclusion=_text(item, "conclusion"),
        steps=steps,
    )


def fetch_jobs(
    runner: GhRunner, repo: str, run: Run, job_name: str
) -> tuple[list[Job], Resolution | None]:
    """Return the run attempt's jobs carrying ``job_name``."""

    path = f"repos/{repo}/actions/runs/{run.run_id}/attempts/{run.attempt}/jobs?per_page=100"
    ok, payload = gh_json(runner, path, "the run jobs")
    if not ok or not isinstance(payload, Mapping):
        return [], Resolution(STATUS_UNKNOWN, REASON_JOBS_UNREADABLE)
    raw = payload.get("jobs")
    if not isinstance(raw, list):
        return [], Resolution(STATUS_UNKNOWN, REASON_JOBS_UNREADABLE)
    jobs = [parse_job(item) for item in raw if isinstance(item, Mapping)]
    return [job for job in jobs if job.name == job_name], None


def classify(job: Job) -> str:
    """Classify a job as executor, pass-through, or unclassified."""

    if job.step_conclusion(EXECUTOR_STEP_NAME) is not None:
        return KIND_EXECUTOR
    if job.step_conclusion(PASS_THROUGH_STEP_NAME) is not None:
        return KIND_PASS_THROUGH
    return KIND_UNCLASSIFIED


def _completed_status(job: Job) -> str:
    status = _CONCLUSION_STATUS.get(job.conclusion)
    if status is None:
        print(
            f"note unrecognized job conclusion {sanitize(job.conclusion, 32)}",
            file=sys.stderr,
        )
        return STATUS_UNKNOWN
    return status


def executor_status(job: Job) -> str:
    """Status of a job that owns the suite-executing step."""

    if job.status != "completed":
        return STATUS_PENDING
    status = _completed_status(job)
    if status != STATUS_PASS:
        return status
    if job.step_conclusion(EXECUTOR_STEP_NAME) == "skipped":
        return STATUS_SKIPPED
    return STATUS_PASS


def pass_through_status(job: Job) -> str:
    """Status of a job that only exists to satisfy a required check."""

    if job.status != "completed":
        return STATUS_PENDING
    status = _completed_status(job)
    return STATUS_SKIPPED if status == STATUS_PASS else status


def unclassified_status(job: Job) -> str:
    """Status of a job whose steps do not identify what it did."""

    if job.status != "completed":
        return STATUS_PENDING
    status = _completed_status(job)
    return STATUS_UNKNOWN if status == STATUS_PASS else status


_TIERS: tuple[tuple[str, Callable[[Job], str], str], ...] = (
    (KIND_EXECUTOR, executor_status, KIND_EXECUTOR),
    (KIND_PASS_THROUGH, pass_through_status, KIND_PASS_THROUGH),
    (KIND_UNCLASSIFIED, unclassified_status, KIND_UNCLASSIFIED),
)

# Statuses a lower-tier sibling may hold without disturbing the deciding tier.
# PASS, SKIPPED, and UNKNOWN are the NORMAL outcomes of a job that did not run
# the suite: pass-through jobs exist to be green without testing, and a skipped
# or unrecognized job is not evidence of anything. UNKNOWN stays benign on
# purpose, because "I could not classify this sibling" must never erase a PASS
# an executor job directly observed. Everything else (PENDING, CANCELLED, FAIL)
# means the check as a whole is not settled and green, so it escalates.
BENIGN_SIBLING_STATUSES = frozenset({STATUS_PASS, STATUS_SKIPPED, STATUS_UNKNOWN})


def worst(statuses: Iterable[str]) -> str:
    """Return the highest-severity status. Failure beats every sibling."""

    return max(statuses, key=lambda status: _SEVERITY[status])


def _tier_statuses(jobs: Sequence[Job]) -> list[tuple[str, list[str]]]:
    """Per-tier statuses in tier order, skipping tiers with no jobs.

    Every job lands in exactly one tier: ``classify`` returns one of the three
    kinds and ``_TIERS`` covers all three, so a non-empty job list always
    yields at least one non-empty tier.
    """

    tiers = [
        (label, [mapper(job) for job in jobs if classify(job) == kind])
        for kind, mapper, label in _TIERS
    ]
    return [(label, statuses) for label, statuses in tiers if statuses]


def aggregate(jobs: Sequence[Job]) -> Resolution:
    """Reduce same-named jobs to one status, executors first.

    The first non-empty tier DECIDES the verdict, so a pass-through sibling can
    neither rescue a failing suite nor manufacture a PASS, and only when no
    executor ran at all does the pass-through tier speak, where the best it can
    say is SKIPPED.

    Deciding is not the same as silencing. A lower tier cannot improve the
    verdict, but it can still make it worse: every job here carries the same
    required check name, so a failed, cancelled, or still-running sibling means
    that check is not green no matter how well the executor did. Those statuses
    escalate through ``worst``. Without this, an executor PASS masked a
    pass-through FAIL and the resolver reported a green check that GitHub was
    showing as red.
    """

    if not jobs:
        return Resolution(STATUS_UNKNOWN, REASON_NO_JOB)

    tiers = _tier_statuses(jobs)
    label, deciding = tiers[0]
    base = worst(deciding)
    unhealthy = [
        status
        for _, statuses in tiers[1:]
        for status in statuses
        if status not in BENIGN_SIBLING_STATUSES
    ]
    status = worst([base, *unhealthy])
    reason = f"{len(deciding)} {label} job(s) of {len(jobs)} matching job(s) resolve to {base}"
    if unhealthy:
        reason += f", raised to {status} by {len(unhealthy)} unhealthy sibling job(s)"
    return Resolution(status, reason)


def resolve(
    runner: GhRunner,
    *,
    repo: str,
    pr: str,
    expected_sha: str,
    workflow: str,
    job_name: str,
) -> Resolution:
    """Resolve the pytest workflow verdict for ``expected_sha``."""

    live_sha, failure = fetch_live_head(runner, repo, pr)
    if failure is not None:
        return failure
    if live_sha != expected_sha:
        return Resolution(STATUS_STALE, REASON_STALE_HEAD)

    path = (
        f"repos/{repo}/actions/workflows/{workflow}/runs"
        f"?event=pull_request&head_sha={expected_sha}&per_page=100"
    )
    ok, payload = gh_json(runner, path, "the workflow runs")
    scan = parse_runs(payload, expected_sha, pr=pr, repo=repo) if ok else None
    if scan is None:
        return Resolution(STATUS_UNKNOWN, REASON_RUNS_UNREADABLE)
    if not scan.bound:
        if scan.rejected:
            return Resolution(STATUS_UNKNOWN, REASON_RUN_NOT_BOUND)
        return Resolution(STATUS_PENDING, REASON_NO_RUN)

    jobs, failure = fetch_jobs(runner, repo, select_latest_run(scan.bound), job_name)
    if failure is not None:
        return failure
    return aggregate(jobs)


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

    Liveness. A shadow that only speaks when it disagrees is indistinguishable
    from a shadow that never ran, so a workflow silently collecting zero
    samples would look exactly like a healthy one. Every invocation therefore
    prints exactly one ``SAMPLE_MARKER`` notice, which makes the sample count
    greppable from run logs and annotations, and any invocation that produced
    NO usable comparison says so as a warning rather than passing quietly.

    Every value in the notice comes from this module's fixed vocabulary, so the
    line cannot be forged by API data.
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
    if agreement == DISAGREE:
        print(
            f"::warning::Shadow pytest signal disagreement. {sanitize(agreement_reason)}. "
            f"{sanitize(resolution.reason)}"
        )
    elif not compared:
        print(
            f"::warning::Shadow pytest signal collected no sample. "
            f"{sanitize(agreement_reason)}. {sanitize(resolution.reason)}"
        )
    return outputs


def write_outputs(output_path: Path, outputs: Mapping[str, str]) -> None:
    """Append the shadow outputs to the GitHub Actions output file."""

    with output_path.open("a", encoding="utf-8") as handle:
        for key, value in outputs.items():
            handle.write(f"{key}={value}\n")


def build_parser() -> argparse.ArgumentParser:
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
    return parser


def _config_error(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return EXIT_CONFIG


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo = args.repo.strip()
    pr = args.pr.strip()
    expected_sha = args.expected_head_sha.strip().lower()
    workflow = args.workflow.strip()

    if not _REPO_PATTERN.match(repo):
        return _config_error("--repo or GITHUB_REPOSITORY must be owner/repo")
    if not _PR_PATTERN.match(pr):
        return _config_error("--pr or PR_NUMBER must be a positive integer")
    if not _SHA_PATTERN.match(expected_sha):
        return _config_error("--expected-head-sha or EXPECTED_HEAD_SHA must be 40 hex characters")
    if not _WORKFLOW_PATTERN.match(workflow):
        return _config_error("--workflow must be a workflow file name")

    resolution = resolve(
        partial(run_gh, timeout=args.timeout),
        repo=repo,
        pr=pr,
        expected_sha=expected_sha,
        workflow=workflow,
        job_name=args.job_name,
    )
    agreement, agreement_reason = compare(resolution.status, args.local_status)
    outputs = emit(resolution, agreement, agreement_reason)

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        write_outputs(Path(github_output), outputs)
    else:
        print("note GITHUB_OUTPUT is unset, outputs were printed only", file=sys.stderr)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())

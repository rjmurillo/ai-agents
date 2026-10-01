#!/usr/bin/env python3
"""Decide whether a workflow run's evidence may count, and corroborate it with the job result.

ADR-113 decisions 2 and 5, issue #5636. Quoted from
``.project-toolkit/architecture/ADR-113-promotion-gate-evidence-and-exceptions.md``.

Decision 5:

    "The aggregator verifies every result through the workflow-run API, never
    from the artifact body: the run's event, workflow path, ref, and `head_sha`
    must match, and a check-run must come from the GitHub Actions app with its
    `integration_id` pinned, because a same-named check-run from another writer
    is otherwise indistinguishable. [...] An artifact is accepted only when its
    workflow run id passes those checks. The aggregator never deserializes an
    artifact from a run that fails them, per ADR-101."

Decision 2:

    "A job status other than `completed` reads as `UNKNOWN`. For a completed
    job, the conclusion `success` corroborates; `failure`, `timed_out`,
    `action_required`, and `startup_failure` read as `FAIL`; `neutral`,
    `skipped`, `cancelled`, `stale`, an absent check-run, and any conclusion not
    listed here read as `UNKNOWN`. A matrix job corroborates only when every one
    of its check-runs is `success`. [...] The result is the worse of the
    artifact's state and the check-run's."

This module holds the pure checks over decoded API payloads. Nothing here
touches the network or a file, so every branch is testable with a dict.

Stricter/looser/different than canonical:

- Decision 5 names an ``integration_id`` pin. The check-run payload carries the
  creating app as ``app.id``, and this module pins ``app.id`` to the GitHub
  Actions app id, 15368. That is the same pin under the field name the REST
  response uses. It is weaker than the separate publishing App ADR-101 Phase 0
  calls for, as decision 5 says: a head-defined run and a base run both come from
  the Actions app.
- Decision 2 reads "the job's check-run". This module reads the job list of the
  latest attempt of the verified run to learn which jobs are current, then
  requires each one's check-run (same id) to be pinned to the Actions app and to
  name this run in ``details_url``. A re-run attempt therefore replaces the
  earlier attempt instead of adding a failed check-run beside it.
- ``push`` runs must be on the default branch, and ``merge_group`` runs on a
  ``gh-readonly-queue/`` branch. Decision 5 says "ref" without naming the rule.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from scripts.validation.evidence import CheckOutcome, EvidenceState, worst_state
from scripts.validation.promotion_evidence import EvidenceRecord

ACTIONS_APP_ID = 15368
COMMIT_EVENTS = frozenset({"push", "merge_group"})
MERGE_QUEUE_BRANCH_PREFIX = "gh-readonly-queue/"

REASON_RUN_INCOMPLETE = "run.incomplete"
REASON_RUN_SHA = "run.sha_mismatch"
REASON_RUN_EVENT = "run.event_not_promotable"
REASON_RUN_WORKFLOW = "run.workflow_mismatch"
REASON_RUN_REF = "run.ref_mismatch"
REASON_RUN_FORK = "run.repository_mismatch"
REASON_CHECK_ABSENT = "checkrun.absent"
REASON_CHECK_APP = "checkrun.app_mismatch"
REASON_CHECK_RUN = "checkrun.run_mismatch"
REASON_CHECK_NOT_COMPLETED = "checkrun.not_completed"
REASON_CHECK_UNRECOGNIZED = "checkrun.unrecognized"

_FAIL_CONCLUSIONS = frozenset({"failure", "timed_out", "action_required", "startup_failure"})
_CONCLUSION_SLUG = re.compile(r"[a-z_]{1,30}")
_REPOSITORY_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")


@dataclass(frozen=True, slots=True)
class Corroboration:
    """What the job's check-runs say about one validator in one run."""

    state: EvidenceState
    reason: str = ""
    detail: str = ""


def _repository_id(run: Mapping[str, Any], key: str) -> int | None:
    section = run.get(key)
    value = section.get("id") if isinstance(section, Mapping) else None
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _on_expected_branch(event: object, branch: object, default_branch: str) -> bool:
    if not isinstance(branch, str) or not branch:
        return False
    if event == "push":
        return bool(default_branch) and branch == default_branch
    return event == "merge_group" and branch.startswith(MERGE_QUEUE_BRANCH_PREFIX)


def run_problem(
    run: Mapping[str, Any], *, candidate_sha: str, workflow: str, default_branch: str
) -> str | None:
    """Return the reason a workflow run may not supply evidence, or None.

    Every field is read from the API payload and any missing or mistyped field
    fails the check: a run that cannot be described is not a run to trust.
    """
    if run.get("status") != "completed":
        return REASON_RUN_INCOMPLETE
    if run.get("head_sha") != candidate_sha:
        return REASON_RUN_SHA
    event = run.get("event")
    if event not in COMMIT_EVENTS:
        return REASON_RUN_EVENT
    if run.get("path") != workflow:
        return REASON_RUN_WORKFLOW
    if not _on_expected_branch(event, run.get("head_branch"), default_branch):
        return REASON_RUN_REF
    head, base = _repository_id(run, "head_repository"), _repository_id(run, "repository")
    if head is None or head != base:
        return REASON_RUN_FORK
    return None


def _conclusion_reason(conclusion: object) -> str:
    if isinstance(conclusion, str) and _CONCLUSION_SLUG.fullmatch(conclusion):
        return f"checkrun.{conclusion}"
    return REASON_CHECK_UNRECOGNIZED


def _check_run_state(check_run: Mapping[str, Any]) -> Corroboration:
    if check_run.get("status") != "completed":
        return Corroboration(EvidenceState.UNKNOWN, REASON_CHECK_NOT_COMPLETED)
    conclusion = check_run.get("conclusion")
    if conclusion == "success":
        return Corroboration(EvidenceState.PASS)
    state = EvidenceState.FAIL if conclusion in _FAIL_CONCLUSIONS else EvidenceState.UNKNOWN
    return Corroboration(state, _conclusion_reason(conclusion))


def _check_run_problem(
    check_run: Mapping[str, Any] | None,
    *,
    job_id: int,
    job_name: str,
    run_id: int,
    repository: str,
) -> str | None:
    """Return why this check-run cannot corroborate the job, or None."""
    if check_run is None:
        return REASON_CHECK_ABSENT
    app = check_run.get("app")
    app_id = app.get("id") if isinstance(app, Mapping) else None
    if app_id != ACTIONS_APP_ID or isinstance(app_id, bool):
        return REASON_CHECK_APP
    expected_url = f"https://github.com/{repository}/actions/runs/{run_id}/job/{job_id}"
    if check_run.get("name") != job_name or check_run.get("details_url") != expected_url:
        return REASON_CHECK_RUN
    return None


def _current_job_ids(jobs: Sequence[Mapping[str, Any]], job_name: str, run_id: int) -> list[int]:
    ids: list[int] = []
    for job in jobs:
        identifier = job.get("id")
        if (
            job.get("name") == job_name
            and job.get("run_id") == run_id
            and isinstance(identifier, int)
            and not isinstance(identifier, bool)
        ):
            ids.append(identifier)
    return ids


def corroborate(
    *,
    job_name: str,
    run_id: int,
    repository: str,
    latest_jobs: Sequence[Mapping[str, Any]],
    check_runs: Mapping[int, Mapping[str, Any]],
) -> Corroboration:
    """Read the check-runs of the job the table names, in the latest attempt of one run.

    ``latest_jobs`` is the job list of the run's latest attempt, ``check_runs``
    maps a check-run id (equal to the job id) to its payload. A matrix job has
    one check-run per leg and every one must be ``success``; the worst leg
    decides. A job with no current entry, or no pinned check-run, is ``UNKNOWN``.
    """
    if not _REPOSITORY_RE.fullmatch(repository):
        return Corroboration(EvidenceState.UNKNOWN, REASON_CHECK_RUN, "repository name is invalid")
    ids = _current_job_ids(latest_jobs, job_name, run_id)
    if not ids:
        return Corroboration(EvidenceState.UNKNOWN, REASON_CHECK_ABSENT, "no current job")
    legs: list[Corroboration] = []
    for job_id in ids:
        check_run = check_runs.get(job_id)
        problem = _check_run_problem(
            check_run, job_id=job_id, job_name=job_name, run_id=run_id, repository=repository
        )
        if problem or check_run is None:
            legs.append(Corroboration(EvidenceState.UNKNOWN, problem or REASON_CHECK_ABSENT))
        else:
            legs.append(_check_run_state(check_run))
    worst = worst_state(leg.state for leg in legs)
    return next(leg for leg in legs if leg.state is worst)


def combine(record: EvidenceRecord, corroboration: Corroboration) -> EvidenceRecord:
    """Return the worse of the artifact's state and the check-run's, as one record.

    An artifact that is already as bad or worse is returned unchanged. When the
    check-run is worse, the record keeps its revision, scope, digest, and items,
    and takes the check-run's state and reason, so the finding names the source
    that failed.
    """
    outcome = record.outcome
    if worst_state([outcome.state, corroboration.state]) is outcome.state:
        return record
    downgraded = CheckOutcome(
        validator=outcome.validator,
        state=corroboration.state,
        revision=outcome.revision,
        scope=outcome.scope,
        reason=corroboration.reason,
        detail=corroboration.detail or "the job's check-run is worse than its evidence artifact",
        duration_seconds=outcome.duration_seconds,
    )
    return EvidenceRecord(
        outcome=downgraded, digest=record.digest, items=record.items, source=record.source
    )

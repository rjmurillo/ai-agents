"""The pre-push tier boundary from ADR-104, pinned against `lefthook.yml`.

Issue context: a pre-push that runs the whole pytest suite measured 679s on a
4-CPU container for a one-file Markdown push, 475s of it in `python-tests`.
A container restart during that window killed the push, and the session then
had to restart, re-derive its state, and push again. The local suite was a
duplicate of CI's `pytest.yml` partition matrix, so the copy of a remote gate
was the thing stopping the push from reaching the gate it was imitating.

ADR-104 draws the boundary: pre-push blocks on checks that are cheap and would
otherwise waste a CI run, and delegates whole-suite execution to CI. Two wires
carry that decision, and both are easy to unpick by accident:

- `pre-pr-validation` claims the fast stage already ran, so the runner can skip
  the four gates that stage duplicates. If the claim outlives the scheduling
  that makes it true, gates go unrun on a real push.
- the four gates name the fast-stage jobs they defer to. A rename on either
  side orphans the reference silently, because a name that matches nothing
  reads exactly like a name that matches.

Coverage:

- positive: the flag is set on the one job whose scheduling justifies it, and
  every `already_run_by` reference resolves to a real fast-stage job.
- negative: no other pre-push or pre-commit job sets the flag; no gate defers
  to a job scheduled at or after `pre-pr-validation`.
- edge: the deferral set is non-empty, so the wiring assertions cannot pass
  vacuously by quantifying over nothing.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
_LEFTHOOK = REPO_ROOT / "lefthook.yml"

_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))
import pre_pr_sequence  # noqa: E402

DEDUPE_JOB = "pre-pr-validation"


def _config() -> dict[str, Any]:
    data = yaml.safe_load(_LEFTHOOK.read_text(encoding="utf-8"))
    assert isinstance(data, dict), "lefthook.yml must parse to a YAML mapping."
    return data


def _jobs_in_entry(entry: dict[str, Any]) -> list[dict[str, Any]]:
    group = entry.get("group")
    if not isinstance(group, dict):
        return [entry]
    out: list[dict[str, Any]] = []
    for job in group.get("jobs", []):
        if isinstance(job, dict):
            out.extend(_jobs_in_entry(job))
    return out


def _entries(hook: str) -> list[dict[str, Any]]:
    jobs = _config()[hook]["jobs"]
    return [entry for entry in jobs if isinstance(entry, dict)]


def _all_jobs(hook: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entry in _entries(hook):
        out.extend(_jobs_in_entry(entry))
    return out


def _entry_index_of(hook: str, job_name: str) -> int | None:
    for index, entry in enumerate(_entries(hook)):
        if any(job.get("name") == job_name for job in _jobs_in_entry(entry)):
            return index
    return None


def _jobs_setting_flag(hook: str) -> set[str]:
    flag = pre_pr_sequence.FAST_STAGE_RAN_ENV
    return {
        str(job.get("name"))
        for job in _all_jobs(hook)
        if isinstance(job.get("env"), dict) and flag in job["env"]
    }


def _deferrals() -> dict[str, str]:
    return {
        gate.name: gate.already_run_by
        for gate in pre_pr_sequence._SEQUENCE
        if gate.already_run_by
    }


class TestFastStageClaim:
    """Only a job the scheduler guarantees ran after the fast stage may claim it."""

    def test_the_dedupe_job_sets_the_flag(self) -> None:
        assert _jobs_setting_flag("pre-push") == {DEDUPE_JOB}

    def test_the_flag_is_set_to_exactly_one(self) -> None:
        job = next(j for j in _all_jobs("pre-push") if j.get("name") == DEDUPE_JOB)
        assert job["env"][pre_pr_sequence.FAST_STAGE_RAN_ENV] == "1"

    def test_no_pre_commit_job_claims_a_pre_push_stage(self) -> None:
        """pre-commit has no fast stage to inherit the claim from."""
        assert _jobs_setting_flag("pre-commit") == set()

    def test_the_claim_rests_on_piped_scheduling(self) -> None:
        """Flipping the hook to parallel would run both stages at once.

        The claim is only true because a piped hook cannot start this job
        until every earlier entry passed.
        """
        assert _config()["pre-push"].get("piped") is True


class TestDeferralsResolve:
    """Every gate that defers must name a job that runs, and runs first."""

    def test_there_is_something_to_check(self) -> None:
        assert _deferrals(), (
            "No gate carries `already_run_by`, so every assertion below passes "
            "vacuously. If the deduplication was removed on purpose, remove "
            "this module with it."
        )

    @pytest.mark.parametrize(
        "gate_name",
        sorted(
            name
            for name, job in _deferrals().items()
            # One gate defers to the eight ratchet jobs as a set rather than to
            # a single named job; `TestRatchetDeferral` covers that one.
            if not job.startswith("the ")
        ),
    )
    def test_the_named_job_exists_in_pre_push(self, gate_name: str) -> None:
        job_name = _deferrals()[gate_name]
        assert _entry_index_of("pre-push", job_name) is not None, (
            f"Gate {gate_name!r} defers to pre-push job {job_name!r}, which is "
            "not in lefthook.yml. A rename on either side leaves the gate "
            "skipped on every real push with nothing running in its place."
        )

    @pytest.mark.parametrize(
        "gate_name",
        sorted(
            name for name, job in _deferrals().items() if not job.startswith("the ")
        ),
    )
    def test_the_named_job_precedes_the_dedupe_job(self, gate_name: str) -> None:
        job_name = _deferrals()[gate_name]
        deferred_to = _entry_index_of("pre-push", job_name)
        dedupe = _entry_index_of("pre-push", DEDUPE_JOB)
        assert deferred_to is not None and dedupe is not None
        assert deferred_to < dedupe, (
            f"{job_name!r} is scheduled at or after {DEDUPE_JOB!r}, so it has "
            f"not necessarily run when {gate_name!r} decides to skip itself."
        )


class TestRatchetDeferral:
    """The Count Ratchets gate defers to the fast stage's ratchet jobs."""

    def test_every_ratchet_the_gate_would_run_has_a_fast_stage_job(self) -> None:
        from checks_ratchet import RATCHETS

        missing = [
            ratchet.job_name
            for ratchet in RATCHETS
            if _entry_index_of("pre-push", ratchet.job_name) is None
        ]
        assert not missing, (
            f"Count Ratchets defers to the fast stage, but {missing} have no "
            "pre-push job there. Those ratchets would run nowhere on a push."
        )

    def test_every_ratchet_job_precedes_the_dedupe_job(self) -> None:
        from checks_ratchet import RATCHETS

        dedupe = _entry_index_of("pre-push", DEDUPE_JOB)
        assert dedupe is not None
        late = [
            ratchet.job_name
            for ratchet in RATCHETS
            if (index := _entry_index_of("pre-push", ratchet.job_name)) is not None
            and index >= dedupe
        ]
        assert not late, f"{late} run at or after {DEDUPE_JOB}; the skip is unsafe."

"""The pre-push deferral boundary from ADR-104, pinned against `lefthook.yml`.

Issue context: a pre-push that ran the whole pytest suite measured 679s on a
4-CPU container for a one-file Markdown push, 498.52s of it in `python-tests`.
A container restart during that window killed the push. ADR-104 draws the
boundary: pre-push blocks on checks that are cheap and would otherwise waste a
CI run, and delegates whole-suite execution to CI.

The first deferral attempt trusted piped ordering but ignored target globs.
Issue #5317 makes the four targets unconditional, so piped ordering now proves
they ran and passed before pre-pr-validation starts.

Coverage:

- positive: the hook is still piped, which the fast-fail staging depends on.
- negative: a synthetic glob on any target makes the soundness check fail.
- edge: direct pre-PR callers leave the scheduler flag unset.
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

FAST_STAGE_FLAG = "AI_AGENTS_PRE_PR_FAST_STAGE_RAN"
EXPECTED_DEFERRALS = {
    "Count Ratchets": "count-ratchets",
    "Unreachable Code Detection": "python-unreachable-statements",
    "Path Normalization": "path-normalization",
    "Planning Artifacts": "planning-artifacts",
}


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


def _all_jobs(hook: str) -> list[dict[str, Any]]:
    jobs = _config()[hook]["jobs"]
    out: list[dict[str, Any]] = []
    for entry in jobs:
        if isinstance(entry, dict):
            out.extend(_jobs_in_entry(entry))
    return out


def _job_named(hook: str, name: str) -> dict[str, Any] | None:
    for job in _all_jobs(hook):
        if job.get("name") == name:
            return job
    return None


def _deferrals() -> dict[str, str]:
    """Gate name to the lefthook job it claims already ran it, if any."""
    return {
        gate.name: getattr(gate, "already_run_by", "")
        for gate in pre_pr_sequence._SEQUENCE
        if getattr(gate, "already_run_by", "")
    }


class TestPipedSchedulingStillHolds:
    """The fast-fail staging depends on it, whatever else changes."""

    def test_pre_push_is_piped(self) -> None:
        assert _config()["pre-push"].get("piped") is True


class TestDeferralClaimIsScoped:
    """Only the lefthook pre-PR job may claim the fast stage passed."""

    def test_only_pre_pr_validation_claims_the_fast_stage_ran(self) -> None:
        offenders = {
            str(job.get("name"))
            for hook in ("pre-push", "pre-commit")
            for job in _all_jobs(hook)
            if isinstance(job.get("env"), dict) and FAST_STAGE_FLAG in job["env"]
        }
        assert offenders == {"pre-pr-validation"}

    def test_exactly_the_duplicate_gates_defer(self) -> None:
        assert _deferrals() == EXPECTED_DEFERRALS


# The four gates the reverted skip would have deferred, by their `_SEQUENCE`
# name. Deletion is the limit case of the skip this module exists to prevent:
# a gate that is gone is skipped on every push, by every hook, permanently.
# The deferral tests below check that no gate *claims* another job ran it, which
# says nothing about a gate that is simply no longer there.
FORMERLY_DEFERRED_GATES = (
    "Count Ratchets",
    "Unreachable Code Detection",
    "Path Normalization",
    "Planning Artifacts",
)


class TestTheDeferredGatesStillExist:
    """A deleted gate is a permanently skipped gate.

    Raised by a spec-validation pass against the claim that these four "are no
    longer skippable": the deferral tests below reject the mechanism that was
    reverted, and would not notice the blunter version of the same outcome.
    """

    def test_every_formerly_deferred_gate_is_still_in_the_sequence(self) -> None:
        present = {gate.name for gate in pre_pr_sequence._SEQUENCE}
        missing = [name for name in FORMERLY_DEFERRED_GATES if name not in present]
        assert missing == [], (
            f"{missing} left the pre-PR sequence. These are the gates the "
            "reverted skip would have deferred; each is a whole-tree scan that "
            "the glob-gated fast-stage jobs do not substitute for on every "
            "change class. Removing one reproduces the defect this module "
            "documents, without the flag that made it reviewable."
        )

    def test_the_presence_check_notices_a_removed_gate(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Negative control: delete a real gate and the check above must fail.

        The earlier version asserted that an invented name was absent from
        `_SEQUENCE`. That is true of any string nobody used, so it held whether
        or not the guard above still discriminated, and review on PR #5319 said
        so. It is the same vacuous-control shape this branch has now found four
        times: a control written after the conclusion was settled, inheriting
        it instead of testing for it.

        This removes one of the four gates the guard is about and requires the
        guard to name it. Nothing on disk changes: `_SEQUENCE` is patched for
        the duration of this test.
        """
        target = FORMERLY_DEFERRED_GATES[0]
        survivors = tuple(gate for gate in pre_pr_sequence._SEQUENCE if gate.name != target)
        assert len(survivors) == len(pre_pr_sequence._SEQUENCE) - 1, (
            f"{target!r} is not in _SEQUENCE to begin with, so removing it "
            "changes nothing and this control proves nothing. The guard above "
            "should already be failing."
        )
        monkeypatch.setattr(pre_pr_sequence, "_SEQUENCE", survivors)

        with pytest.raises(AssertionError, match=target):
            self.test_every_formerly_deferred_gate_is_still_in_the_sequence()


def _unsound_deferrals() -> list[str]:
    unsound: list[str] = []
    for gate_name, job_name in _deferrals().items():
        job = _job_named("pre-push", job_name)
        if job is None:
            unsound.append(f"{gate_name} defers to {job_name!r}, which does not exist")
        elif job.get("glob") is not None:
            unsound.append(
                f"{gate_name} defers to {job_name!r}, which carries "
                f"glob={job['glob']!r} and so does not run on every push"
            )
    return unsound


class TestEveryDeferralIsSound:
    def test_a_deferral_target_must_not_be_glob_gated(self) -> None:
        assert _unsound_deferrals() == []

    def test_the_rule_rejects_a_globbed_target(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        real_lookup = _job_named

        def lookup(hook: str, name: str) -> dict[str, Any] | None:
            job = real_lookup(hook, name)
            if name == "count-ratchets" and job is not None:
                return {**job, "glob": "**/*.py"}
            return job

        monkeypatch.setattr(sys.modules[__name__], "_job_named", lookup)
        assert any("Count Ratchets" in item for item in _unsound_deferrals())


# ADR-104 rule 9. A job that cannot fail is not a gate, and pre-push carries six
# of them. Five guarantee it in their own code, where a reader of the script can
# see it: `ruff --exit-zero`, or a handler whose only top-level return is
# `return 0`. `worktree-gc-report` is the exception and the hazard:
# `gc_worktrees.py` returns 2 or 3 on failure and the job appends `|| echo ...`
# here to swallow it (issue #4257). Nothing in the script says so.
#
# The direction that fails silently is a NEW job written this way. A gate whose
# exit is discarded in YAML reports OK on every push, and the pipe carries on to
# the next job, so it is indistinguishable from a passing gate for exactly the
# reason a glob-skipped job is (see this module's docstring). Sizing, budget
# ratchets, and the container clamp all still apply to it, so nothing else in
# this suite notices.
EXIT_SWALLOWING_PREPUSH_JOBS = frozenset({"worktree-gc-report"})


class TestNonBlockingJobsAreDeclaredNotDiscovered:
    """ADR-104 rule 9: state the mechanism next to the job."""

    def test_only_known_jobs_discard_their_exit_status(self) -> None:
        discarding = {
            str(job.get("name")) for job in _all_jobs("pre-push") if "||" in str(job.get("run", ""))
        }
        unexpected = discarding - EXIT_SWALLOWING_PREPUSH_JOBS
        assert unexpected == set(), (
            f"{sorted(unexpected)} discard a non-zero exit with `||` in "
            "lefthook.yml, so they cannot fail a push and nothing in the "
            "script they run says so. Either make the job blocking, or add it "
            "to EXIT_SWALLOWING_PREPUSH_JOBS with the issue that decided it "
            "and check the placement question in ADR-104 rule 9: a job that "
            "cannot fail earns a local slot only if a developer acts on its "
            "output before the PR exists."
        )

    def test_every_declared_swallower_still_swallows(self) -> None:
        """Negative control: the entry above is not stale.

        If `worktree-gc-report` were made blocking, the assertion above would
        still pass while the allowlist quietly documented the wrong thing.
        """
        for name in EXIT_SWALLOWING_PREPUSH_JOBS:
            job = _job_named("pre-push", name)
            assert job is not None, f"{name!r} is missing from pre-push."
            assert "||" in str(job.get("run", "")), (
                f"{name!r} no longer discards its exit status. If it is a "
                "blocking gate now, drop it from EXIT_SWALLOWING_PREPUSH_JOBS "
                "and size its cap as a gate rather than as a reporter."
            )

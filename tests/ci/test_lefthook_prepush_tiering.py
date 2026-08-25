"""The pre-push tier boundary from ADR-104, pinned against `lefthook.yml`.

Issue context: a pre-push that ran the whole pytest suite measured 679s on a
4-CPU container for a one-file Markdown push, 498.52s of it in `python-tests`.
A container restart during that window killed the push. ADR-104 draws the
boundary: pre-push blocks on checks that are cheap and would otherwise waste a
CI run, and delegates whole-suite execution to CI.

This module exists mostly to keep one specific mistake from coming back.

An earlier revision of this branch skipped four `pre_pr.py` gates on the claim
that the pre-push fast stage had already run them, justified by the hook being
`piped: true`. That claim is false, and the test written to protect it checked
the wrong half: it resolved job names and entry order, which catches a rename,
and never read `glob`. Piping proves no earlier job FAILED. It does not prove
one RAN. Measured on lefthook 2.1.10 against a fixture repo with one
glob-gated job and one un-gated job, pushing a docs-only commit::

    |  py-only-gate (skip) no matching push files
    |  always-gate > ALWAYS GATE RAN
    summary: (done in 0.02 seconds)   OK always-gate
    EXIT=0

A glob-skipped job is indistinguishable from a passed one. Every deferral
target carried a `glob:` and `pre-pr-validation` carries none, so on a
Markdown-only push the Python-globbed jobs never ran and the skip removed the
gate instead of deduplicating it. The skip was reverted (issue #5316).

Coverage:

- positive: the hook is still piped, which the fast-fail staging depends on.
- negative: no pre-push or pre-commit job claims a fast stage ran, and no gate
  in the pre-PR sequence carries a deferral.
- edge: if a deferral is ever reintroduced, its target must carry no `glob`,
  which is the condition that would make the claim true.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
_LEFTHOOK = REPO_ROOT / "lefthook.yml"

_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))
import pre_pr_sequence  # noqa: E402

# The reverted flag. Named as a literal because the constant it used to match
# no longer exists, and this test's job is to notice if either comes back.
REVERTED_FAST_STAGE_FLAG = "AI_AGENTS_PRE_PR_FAST_STAGE_RAN"


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


class TestTheUnsoundSkipStaysReverted:
    """Regression guard for the defect described in this module's docstring."""

    def test_no_job_claims_the_fast_stage_ran(self) -> None:
        offenders = {
            str(job.get("name"))
            for hook in ("pre-push", "pre-commit")
            for job in _all_jobs(hook)
            if isinstance(job.get("env"), dict)
            and REVERTED_FAST_STAGE_FLAG in job["env"]
        }
        assert offenders == set(), (
            f"{sorted(offenders)} set {REVERTED_FAST_STAGE_FLAG}. That flag "
            "asserted a fast-stage job had run, which `piped: true` does not "
            "prove for a glob-gated job. See this module's docstring and the "
            "lefthook 2.1.10 measurement in it before reintroducing it."
        )

    def test_no_gate_defers_to_a_scheduler_claim(self) -> None:
        assert _deferrals() == {}, (
            f"Gates {sorted(_deferrals())} carry a deferral. If this is "
            "deliberate, the next test states the condition that makes a "
            "deferral sound; satisfy it."
        )


class TestAnyFutureDeferralMustBeSound:
    """The condition that would make the reverted skip correct.

    Kept live rather than deleted with the feature: this is the assertion the
    original test should have carried, and it is what a reviewer needs the
    next time someone proposes the same optimization.
    """

    def test_a_deferral_target_must_not_be_glob_gated(self) -> None:
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
        assert unsound == [], "\n".join(unsound)

    def test_the_rule_would_have_caught_the_reverted_skip(self) -> None:
        """Negative control: the four former targets are all glob-gated.

        Without this, the rule above passes vacuously today (there are no
        deferrals) and nobody can tell whether it discriminates.
        """
        former_targets = (
            "python-unreachable-statements",
            "path-normalization",
            "planning-artifacts",
            "python-lint-ratchet",
        )
        for name in former_targets:
            job = _job_named("pre-push", name)
            assert job is not None, f"{name!r} is missing from pre-push."
            assert job.get("glob") is not None, (
                f"{name!r} no longer carries a glob. If its glob was removed "
                "on purpose, a deferral to it would now be sound and this "
                "control needs a different example."
            )

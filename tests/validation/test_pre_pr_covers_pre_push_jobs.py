"""Bind pre_pr's gate list to every job the pre-push hook runs (issue #6426).

Ten closed issues record the same event: ``pre_pr.py`` printed "All validations
passed", the push ran, and a pre-push job rejected it up to ten minutes later.
Each fix wired one gap. This test closes the class. Both sides are derived:

- Hook side: every job under ``pre-push`` in ``lefthook.yml``, groups flattened.
- pre_pr side: ``pre_pr_sequence._SEQUENCE``.

Every job must appear in exactly one table below. ``GATED`` names the pre_pr
gate that answers the same question. ``EXEMPT`` states why no gate can or should
run the job inside pre_pr. A new pre-push job fails
``test_every_pre_push_job_is_classified`` until it lands in one of them.

Negative controls, each verified to fail before shipping:

- Add a pre-push job to ``lefthook.yml`` with no row:
  ``test_every_pre_push_job_is_classified`` fails and names the job.
- Delete a gate from ``_SEQUENCE``: ``test_gated_rows_name_a_real_gate`` fails.
- Delete a job from ``lefthook.yml`` and keep its row:
  ``test_every_pre_push_job_is_classified`` fails on the stale row.
- List a job in both tables: ``test_no_job_is_both_gated_and_exempt`` fails.
- Point a deferral at a job whose row names another gate:
  ``test_deferred_gates_match_their_gated_row`` fails.
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

# Same import discipline as the sibling pre_pr tests (issue #2223): bare-name
# import with ``scripts/validation`` on ``sys.path``, never restored.
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))
import pre_pr_sequence

_MIN_REASON_LENGTH = 40

# Pre-push job -> the pre_pr gate that runs the same check.
GATED: dict[str, str] = {
    "count-ratchets": "Count Ratchets",
    "python-unreachable-statements": "Unreachable Code Detection",
    "path-normalization": "Path Normalization",
    "planning-artifacts": "Planning Artifacts",
    "dash-prohibition": "Em/en-dash Prohibition",
    "review-axis-drift": "Review Axis Drift",
    "security-suppression-policy": "Security Suppressions Diff",
    "placeholder-identity": "Placeholder Identity",
    "python-type-check": "Mypy Changed Files (ratchet)",
    "workflow-local-run": "Workflow Local Run",
}

# Pre-push job -> why pre_pr runs nothing for it.
EXEMPT: dict[str, str] = {
    "repo-health": (
        "Probes the shared .git/config for corruption (issue #4698) before any hook "
        "job. It asks about repository state, not about the branch's content, and "
        "pre-commit runs it on every commit."
    ),
    "repair-packed-refs": (
        "Maintenance writer that removes blank records from packed-refs (issue "
        "#2903). It repairs repository state and validates nothing on the branch."
    ),
    "mutation-safety": (
        "Fails the push when a killed mutation run left its marker in the git "
        "directory. The marker is machine state, absent from a clean checkout."
    ),
    "push-ref-staleness": (
        "Compares each pushed ref with the remote through git ls-remote, from the "
        "ref payload git writes to the hook's stdin. No payload exists before a push."
    ),
    "push-ref-policy": (
        "Reads the ref payload for protected-branch, non-fast-forward, shallow "
        "history, and security review marker checks. The marker must sit on the "
        "pushed SHA, and /review commits it after pre_pr runs, so pre_pr cannot "
        "block on it. The Review Marker gate reports it as advisory and Plugin "
        "Version Bump runs the version check."
    ),
    "branch-context-policy": (
        "Compares the branch with today's session log and fails open on every "
        "ambiguous input. Session log creation is discontinued, and pre-commit "
        "runs the same check on every commit."
    ),
    "security-scan": (
        "Semgrep over each pushed head. The job owns a 15 minute cap and reads the "
        "ref payload, while pre-pr-validation runs under a 4 minute cap "
        "(PRE_PR_OUTER_CAP_SECONDS), so a semgrep run cannot fit inside pre_pr."
    ),
    "pre-pr-validation": (
        "This is the job that runs pre_pr.py. A gate cannot be its own parity row."
    ),
    "worktree-gc-report": (
        "Advisory report on registered worktrees, run through report_advisory_result. "
        "It reports machine state and does not block the push."
    ),
    "python-tests": (
        "Runs the pytest suite with testmon selection under a 15 minute cap. pre_pr "
        "deliberately skips the suite because CI's pytest legs run it. Structural "
        "tests such as test_rule_templates_lossless.py fail here after a green "
        "pre_pr, so run the tests that cover the files you changed before pushing."
    ),
    "zero-collection-tests": (
        "One pytest collection over testpaths, about 38 seconds measured. "
        "pre-pr-validation has a four minute timeout against a 192 second baseline."
    ),
    "python-lint-advisory": (
        "Advisory ruff report over pushed files. Findings do not block the push. "
        "pre-commit python-check runs ruff on staged files, and Count Ratchets "
        "runs the ruff ratchets."
    ),
    "branch-config-prune-report": (
        "Advisory report on stale branch sections in the shared .git/config, run "
        "through report_advisory_result. It reports machine state, never blocks "
        "the push, and checks nothing on the branch."
    ),
    "additions-advisory": (
        "Advisory size report on branch additions against origin/main. It "
        "warns and does not block the push."
    ),
    "hook-anchoring-e2e": (
        "Launches a real Claude or Copilot CLI over the network with credentials. "
        "The Hook Anchoring gate is the offline half and runs in pre_pr."
    ),
    "plugin-load-e2e": (
        "Launches a real Claude or Copilot CLI over the network with credentials "
        "to load the plugin. No offline equivalent exists."
    ),
    "bot-cascade-advisory": (
        "Advisory report that calls gh for the open pull request. It needs a "
        "pull request, which does not exist before the first push."
    ),
}


def _flatten(entry: dict[str, Any]) -> list[dict[str, Any]]:
    group = entry.get("group")
    if not isinstance(group, dict):
        return [entry]
    found: list[dict[str, Any]] = []
    for job in group.get("jobs", []):
        if isinstance(job, dict):
            found.extend(_flatten(job))
    return found


def pre_push_jobs(lefthook: Path = _LEFTHOOK) -> list[str]:
    """Names of every ``pre-push`` job, groups flattened, in file order."""
    config = yaml.safe_load(lefthook.read_text(encoding="utf-8"))
    entries = config["pre-push"]["jobs"]
    return [str(job["name"]) for entry in entries for job in _flatten(entry)]


def unclassified(jobs: list[str], gated: dict[str, str], exempt: dict[str, str]) -> set[str]:
    """Jobs with no row in either table."""
    return set(jobs) - set(gated) - set(exempt)


def stale_rows(jobs: list[str], gated: dict[str, str], exempt: dict[str, str]) -> set[str]:
    """Rows whose job no longer exists in the hook."""
    return (set(gated) | set(exempt)) - set(jobs)


def test_every_pre_push_job_is_classified() -> None:
    jobs = pre_push_jobs()
    missing = unclassified(jobs, GATED, EXEMPT)
    stale = stale_rows(jobs, GATED, EXEMPT)
    assert not missing, (
        f"pre-push jobs with no pre_pr gate and no exemption: {sorted(missing)}. Add a gate "
        "in scripts/validation/checks_ci_parity.py and a row in GATED, or add an EXEMPT "
        "row with the reason."
    )
    assert not stale, f"rows for jobs that left lefthook.yml: {sorted(stale)}"


def test_the_hook_scan_finds_the_known_jobs() -> None:
    """A scan that finds nothing would pass the test above for the wrong reason."""
    jobs = pre_push_jobs()
    assert len(jobs) > 20
    for known in ("python-tests", "security-scan", "pre-pr-validation", "count-ratchets"):
        assert known in jobs


def test_no_job_is_both_gated_and_exempt() -> None:
    assert not set(GATED) & set(EXEMPT)


def test_gated_rows_name_a_real_gate() -> None:
    gate_names = {gate.name for gate in pre_pr_sequence._SEQUENCE}
    missing = {job: gate for job, gate in GATED.items() if gate not in gate_names}
    assert not missing, f"GATED rows name gates that _SEQUENCE lacks: {missing}"


def test_deferred_gates_match_their_gated_row() -> None:
    """A gate that defers to a pre-push job must be the gate that job's row names."""
    for gate in pre_pr_sequence._SEQUENCE:
        if not gate.already_run_by:
            continue
        assert GATED.get(gate.already_run_by) == gate.name, (
            f"{gate.name} defers to {gate.already_run_by}, but GATED maps that job to "
            f"{GATED.get(gate.already_run_by)!r}"
        )


def test_every_exemption_states_a_reason() -> None:
    short = {job for job, reason in EXEMPT.items() if len(reason) < _MIN_REASON_LENGTH}
    assert not short, f"exemptions without a stated reason: {sorted(short)}"


class TestClassifierHelpers:
    """The helpers must fail on the gaps the real tables are meant to catch."""

    def test_unclassified_names_a_job_with_no_row(self) -> None:
        assert unclassified(["a", "b", "c"], {"a": "Gate"}, {"b": "reason"}) == {"c"}

    def test_stale_rows_names_a_row_with_no_job(self) -> None:
        assert stale_rows(["a"], {"a": "Gate"}, {"gone": "reason"}) == {"gone"}

    def test_a_fully_classified_hook_reports_no_gap(self) -> None:
        assert unclassified(["a", "b"], {"a": "Gate"}, {"b": "reason"}) == set()

    def test_pre_push_jobs_flattens_nested_groups(self, tmp_path: Path) -> None:
        config = tmp_path / "lefthook.yml"
        config.write_text(
            "pre-push:\n"
            "  jobs:\n"
            "    - name: top\n"
            "    - group:\n"
            "        jobs:\n"
            "          - name: inner\n"
            "          - group:\n"
            "              jobs:\n"
            "                - name: deepest\n",
            encoding="utf-8",
        )
        assert pre_push_jobs(config) == ["top", "inner", "deepest"]

    def test_pre_push_jobs_ignores_other_hooks(self, tmp_path: Path) -> None:
        config = tmp_path / "lefthook.yml"
        config.write_text(
            "pre-commit:\n  jobs:\n    - name: commit-only\n"
            "pre-push:\n  jobs:\n    - name: push-only\n",
            encoding="utf-8",
        )
        assert pre_push_jobs(config) == ["push-only"]


@pytest.mark.parametrize("job", sorted(GATED))
def test_each_gated_job_exists_in_the_hook(job: str) -> None:
    assert job in pre_push_jobs()

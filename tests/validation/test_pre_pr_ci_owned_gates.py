"""Pre-PR gates the pre-push hook defers to CI (ADR-104, amendment 2026-11-27).

``_Gate.ci_owned_by`` names the CI jobs that own a gate. When the hook sets
``AI_AGENTS_PRE_PR_FAST_STAGE_RAN=1`` the gate records a ``policy.ci_owned``
skip instead of running. ADR-104 rule 6 says a deferral is tested on what it
relies on, so this module checks the CI side of the claim:

- positive: each named job exists, has no job-level ``if:``, and feeds a
  required context; the staleness owner runs ``build_all.py --check``; the
  Count Ratchets owners are exactly the required jobs that run every
  ``checks_ratchet.RATCHETS`` script.
- negative: ``_owner_problems`` reports each failure mode on a fixture
  workflow, and a gate that sets both deferral fields is named.
- edge: a step-level ``if:`` does not count as an unconditional run.

The hook-side behavior (which gates skip, and that the skip prints) lives in
``test_pre_pr_sequence_registry.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

# Import the way production imports (issue #2223), as the registry tests do.
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))
import pre_pr_sequence

from tests.validation.test_pre_pr_sequence_registry import CI_OWNED_GATES


class TestCiOwnedGates:
    """``ci_owned_by`` names a real, unconditional CI job for every gate that sets it."""

    @staticmethod
    def _owned() -> list[pre_pr_sequence._Gate]:
        return [gate for gate in pre_pr_sequence._SEQUENCE if gate.ci_owned_by]

    def test_exactly_the_expected_gates_are_ci_owned(self) -> None:
        assert {gate.name for gate in self._owned()} == CI_OWNED_GATES

    @staticmethod
    def _gates_with_both(gates: tuple[pre_pr_sequence._Gate, ...]) -> list[str]:
        return [gate.name for gate in gates if gate.already_run_by and gate.ci_owned_by]

    def test_no_gate_sets_both_deferral_fields(self) -> None:
        assert self._gates_with_both(pre_pr_sequence._SEQUENCE) == []

    def test_the_both_fields_check_detects_a_violation(self) -> None:
        """Negative control: the same scan must name a gate that sets both fields."""
        bad = pre_pr_sequence._Gate(
            "Bad", lambda _r, _a: True, already_run_by="x", ci_owned_by="y.yml z"
        )
        good = pre_pr_sequence._Gate("Good", lambda _r, _a: True, ci_owned_by="y.yml z")
        assert self._gates_with_both((good, bad)) == ["Bad"]

    @pytest.mark.parametrize("gate_name", sorted(CI_OWNED_GATES))
    def test_every_ci_owned_by_entry_names_a_required_unconditional_job(
        self, gate_name: str
    ) -> None:
        gate = next(g for g in pre_pr_sequence._SEQUENCE if g.name == gate_name)
        entries = _ci_owned_entries(gate)
        assert entries
        for entry in entries:
            assert _owner_problems(entry, needle=None) == []

    def test_staleness_owner_runs_the_command_the_gate_runs(self) -> None:
        """ADR-104 rule 6: the deferral is tested on what it relies on.

        The gate shells out to ``build_all.py --check``; the CI job it defers to
        must run that same command in an unconditional step of a required job.
        """
        import check_generated_staleness

        gate_scripts = {"/".join(parts) for _label, parts in check_generated_staleness._CHECKS}
        assert gate_scripts == {"build/scripts/build_all.py"}
        gate = next(
            g for g in pre_pr_sequence._SEQUENCE if g.name == "Generated Artifact Staleness"
        )
        for entry in _ci_owned_entries(gate):
            assert _owner_problems(entry, needle="build/scripts/build_all.py --check") == []

    def test_count_ratchets_owners_are_exactly_the_jobs_that_run_the_registry(self) -> None:
        """Every RATCHETS script has a required, unconditional CI owner, and the
        ``ci_owned_by`` text names exactly that set of jobs."""
        from checks_ratchet import RATCHETS

        from tests.ci.ratchet_test_helpers import ci_owners_of

        owners: set[str] = set()
        for ratchet in RATCHETS:
            found = ci_owners_of(ratchet.script)
            assert found, f"{ratchet.script} has no required, unconditional CI job"
            owners.update(found)
        gate = next(g for g in pre_pr_sequence._SEQUENCE if g.name == "Count Ratchets")
        assert set(_ci_owned_entries(gate)) == owners


def _ci_owned_entries(gate: object) -> list[str]:
    return [
        part.strip() for part in str(getattr(gate, "ci_owned_by", "")).split(",") if part.strip()
    ]


def _owner_problems(entry: str, needle: str | None, workflows_dir: Path | None = None) -> list[str]:
    """Return why ``entry`` (``<workflow>.yml <job-id>``) is not a valid CI owner.

    Valid means: the workflow and job exist, the job has no job-level ``if:``,
    the job or a rollup that needs it is a required context, and, when
    ``needle`` is given, an unconditional step of the job runs it.
    """
    from tests.ci.ratchet_test_helpers import _is_required_job

    base = workflows_dir or REPO_ROOT / ".github" / "workflows"
    workflow, _, job_id = entry.partition(" ")
    if not workflow.endswith(".yml") or not job_id:
        return [f"{entry!r} is not '<workflow>.yml <job>'"]
    path = base / workflow
    if not path.is_file():
        return [f"{entry!r}: {path} does not exist"]
    jobs = yaml.safe_load(path.read_text(encoding="utf-8"))["jobs"]
    if job_id not in jobs:
        return [f"{entry!r}: job {job_id!r} not in {workflow}"]
    problems: list[str] = []
    if jobs[job_id].get("if") is not None:
        problems.append(f"{entry!r}: job carries an if:")
    if not _is_required_job(jobs, job_id):
        problems.append(f"{entry!r}: neither the job nor a rollup that needs it is required")
    if needle is not None and not any(
        needle in str(step.get("run", "")) and step.get("if") is None
        for step in jobs[job_id].get("steps", [])
    ):
        problems.append(f"{entry!r}: no unconditional step runs {needle!r}")
    return problems


class TestOwnerProblemsNegativeControls:
    """Each failure mode ``_owner_problems`` guards must be reported."""

    _WORKFLOW = (
        "jobs:\n"
        "  good:\n"
        "    name: Run Python Tests\n"
        "    steps:\n"
        "      - run: uv run python build/scripts/build_all.py --check\n"
        "  gated:\n"
        "    name: Run Python Tests\n"
        "    if: github.event_name == 'push'\n"
        "    steps:\n"
        "      - run: uv run python build/scripts/build_all.py --check\n"
        "  optional:\n"
        "    name: Not A Required Context\n"
        "    steps:\n"
        "      - run: uv run python build/scripts/build_all.py --check\n"
        "  stepgated:\n"
        "    name: Run Python Tests\n"
        "    steps:\n"
        "      - run: uv run python build/scripts/build_all.py --check\n"
        "        if: matrix.primary\n"
    )

    @pytest.fixture
    def workflows(self, tmp_path: Path) -> Path:
        (tmp_path / "w.yml").write_text(self._WORKFLOW, encoding="utf-8")
        return tmp_path

    def test_a_valid_owner_has_no_problem(self, workflows: Path) -> None:
        assert _owner_problems("w.yml good", "build_all.py --check", workflows) == []

    @pytest.mark.parametrize(
        ("entry", "needle", "fragment"),
        [
            ("w.yml missing", None, "not in w.yml"),
            ("absent.yml good", None, "does not exist"),
            ("w.yml", None, "is not '<workflow>.yml <job>'"),
            ("w.yml gated", None, "job carries an if:"),
            ("w.yml optional", None, "required"),
            ("w.yml stepgated", "build_all.py --check", "no unconditional step"),
            ("w.yml good", "some_other_script.py", "no unconditional step"),
        ],
    )
    def test_each_failure_mode_is_reported(
        self, workflows: Path, entry: str, needle: str | None, fragment: str
    ) -> None:
        problems = _owner_problems(entry, needle, workflows)
        assert any(fragment in problem for problem in problems), problems

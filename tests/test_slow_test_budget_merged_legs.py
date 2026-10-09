"""The slow-test budget gate judges merged leg reports, not one leg (issues #5382, #6239).

pytest-split cuts one file across CI legs, so a per-leg gate sees only a
fraction of a budgeted suite. These tests pin that the gate sums every leg's
junit report, and that the workflow runs it once, in the coverage job.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.testing import slow_test_budget as budget_gate

REPO_ROOT = Path(__file__).resolve().parents[1]


def _budget(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "budget.toml"
    path.write_text(body, encoding="utf-8")
    return path


class TestTheWorkflowWiring:
    def test_the_workflow_runs_the_gate_in_the_coverage_job_over_merged_junit(self) -> None:
        """The gate is wired, not merely available (ci-scripts.md items 11 and 13).

        pytest-split cuts one file across legs, so a per-leg gate could see only
        a fraction of a budgeted suite. The gate must run once, in the job that
        downloads every leg's report, and it must name the junit file of every
        matrix leg explicitly, so a leg whose report is missing fails closed
        (exit 3) instead of being undercounted by a glob.
        """
        import shlex

        import yaml

        workflow = yaml.safe_load(
            (REPO_ROOT / ".github/workflows/pytest.yml").read_text(encoding="utf-8")
        )
        jobs = workflow["jobs"]
        assert not [s for s in jobs["test"]["steps"] if "slow_test_budget.py" in str(s.get("run"))]
        steps = jobs["coverage"]["steps"]
        gate = [s for s in steps if "slow_test_budget.py" in str(s.get("run", ""))]
        assert len(gate) == 1, "the slow-test budget gate is not wired into the coverage job"
        assert "if" not in gate[0], "the gate must not be skippable"
        tokens = shlex.split(gate[0]["run"])
        assert tokens[tokens.index("--budget") + 1] == "pyproject.toml"
        inputs = [t for t in tokens if t.endswith(".xml")]
        assert not any(c in t for t in inputs for c in "*?["), "inputs must not be a glob"
        names = [s.get("name") for s in steps]
        assert names.index("Download partition artifacts") < steps.index(gate[0])
        legs = jobs["test"]["strategy"]["matrix"]["include"]
        expected = [leg["junit_file"] for leg in legs]
        assert len(expected) == 6
        assert sorted(inputs) == sorted(expected)


class TestASplitModuleCannotBeDiluted:
    """AC4: a budgeted file cut across legs is summed, not judged per leg."""

    @staticmethod
    def _leg(tmp_path: Path, name: str, seconds: float) -> Path:
        path = tmp_path / name
        path.write_text(
            '<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="pytest">'
            f'<testcase classname="tests.test_alpha" name="test_{name[:-4]}" time="{seconds}" />'
            "</testsuite></testsuites>",
            encoding="utf-8",
        )
        return path

    def test_each_leg_alone_passes_and_the_merge_fails(self, tmp_path: Path) -> None:
        toml = _budget(tmp_path, '[tool.slow-test-budget]\n"tests/test_alpha.py" = 10.0\n')
        first = self._leg(tmp_path, "one.xml", 6.0)
        second = self._leg(tmp_path, "two.xml", 6.0)
        assert budget_gate.main([str(first), "--budget", str(toml)]) == 0
        assert budget_gate.main([str(second), "--budget", str(toml)]) == 0
        assert budget_gate.main([str(first), str(second), "--budget", str(toml)]) == 1

    def test_the_merged_run_names_the_summed_seconds(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        toml = _budget(tmp_path, '[tool.slow-test-budget]\n"tests/test_alpha.py" = 10.0\n')
        legs = [self._leg(tmp_path, "one.xml", 6.0), self._leg(tmp_path, "two.xml", 6.0)]
        budget_gate.main([*map(str, legs), "--budget", str(toml)])
        assert "recorded 12.00s against 10.00s" in capsys.readouterr().err

    def test_a_missing_leg_report_exits_three(self, tmp_path: Path) -> None:
        toml = _budget(tmp_path, '[tool.slow-test-budget]\n"tests/test_alpha.py" = 10.0\n')
        present = self._leg(tmp_path, "one.xml", 1.0)
        missing = tmp_path / "absent.xml"
        assert budget_gate.main([str(present), str(missing), "--budget", str(toml)]) == 3

"""Tests for the validator-suite performance budget gate (issue #5382).

Coverage:
* Positive: a module under its budget exits 0.
* Negative: a module over its budget exits 1 and the message names the module,
  the seconds it recorded, and the limit it broke.
* Every overrun is reported, not only the first.
* Edge: a budgeted module the report does not contain is not a violation, which
  is what a partitioned or change-scoped CI run produces.
* Edge: a TOML file with no ``[tool.slow-test-budget]`` table budgets nothing.
* Config and external failure paths: malformed table, non-numeric seconds,
  unreadable budget file, unreadable input.
* The shipped budget in ``pyproject.toml`` names modules that exist, so a typo
  cannot make the gate pass by budgeting nothing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.testing import slow_test_budget as budget_gate
from scripts.testing.slow_test_report import ModuleGroup

REPO_ROOT = Path(__file__).resolve().parents[1]

_JUNIT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="2">
<testcase classname="tests.test_alpha" name="test_one" time="4.500" />
<testcase classname="tests.test_alpha.TestGroup" name="test_two" time="7.250" />
</testsuite></testsuites>
"""


def _junit(tmp_path: Path) -> Path:
    path = tmp_path / "junit.xml"
    path.write_text(_JUNIT, encoding="utf-8")
    return path


def _budget(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "budget.toml"
    path.write_text(body, encoding="utf-8")
    return path


class TestTheVerdict:
    def test_a_module_under_budget_exits_zero(self, tmp_path: Path) -> None:
        toml = _budget(tmp_path, '[tool.slow-test-budget]\n"tests/test_alpha.py" = 20.0\n')
        assert budget_gate.main([str(_junit(tmp_path)), "--budget", str(toml)]) == 0

    def test_a_module_over_budget_exits_one_and_names_it(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        toml = _budget(tmp_path, '[tool.slow-test-budget]\n"tests/test_alpha.py" = 5.0\n')
        assert budget_gate.main([str(_junit(tmp_path)), "--budget", str(toml)]) == 1
        err = capsys.readouterr().err
        assert "over budget: tests/test_alpha.py recorded 11.75s against 5.00s" in err

    def test_every_overrun_is_reported_not_only_the_first(self) -> None:
        """Batching does not stop at the first failure, and neither does this."""
        groups = [
            ModuleGroup("tests/test_a.py", seconds=9.0),
            ModuleGroup("tests/test_b.py", seconds=8.0),
            ModuleGroup("tests/test_c.py", seconds=1.0),
        ]
        limits = {"tests/test_a.py": 5.0, "tests/test_b.py": 5.0, "tests/test_c.py": 5.0}
        assert [m for m, _s, _b in budget_gate.overruns(groups, limits)] == [
            "tests/test_a.py",
            "tests/test_b.py",
        ]

    def test_a_budgeted_module_absent_from_the_report_is_not_a_violation(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Edge: a partitioned or change-scoped CI run executes only some suites."""
        toml = _budget(tmp_path, '[tool.slow-test-budget]\n"tests/test_absent.py" = 1.0\n')
        assert budget_gate.main([str(_junit(tmp_path)), "--budget", str(toml)]) == 0
        assert "budget: 0 over, 0 of 1 budgeted modules present" in capsys.readouterr().err

    def test_the_report_counts_are_printed_on_a_clean_run(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A run that examined nothing must not read the same as a clean run."""
        toml = _budget(tmp_path, '[tool.slow-test-budget]\n"tests/test_alpha.py" = 20.0\n')
        budget_gate.main([str(_junit(tmp_path)), "--budget", str(toml)])
        assert (
            "budget: 0 over, 1 of 1 budgeted modules present, 1 modules in this report"
            in capsys.readouterr().err
        )


class TestFailurePaths:
    def test_a_toml_without_the_table_budgets_nothing(self, tmp_path: Path) -> None:
        toml = _budget(tmp_path, '[project]\nname = "x"\n')
        assert budget_gate.load_budget(toml) == {}
        assert budget_gate.main([str(_junit(tmp_path)), "--budget", str(toml)]) == 0

    def test_a_table_that_is_not_a_table_exits_two(self, tmp_path: Path) -> None:
        toml = _budget(tmp_path, '[tool]\nslow-test-budget = "later"\n')
        assert budget_gate.main([str(_junit(tmp_path)), "--budget", str(toml)]) == 2

    def test_a_malformed_budget_exits_two(self, tmp_path: Path) -> None:
        toml = _budget(tmp_path, "[tool.slow-test-budget\n")
        assert budget_gate.main([str(_junit(tmp_path)), "--budget", str(toml)]) == 2

    def test_a_non_numeric_budget_exits_two(self, tmp_path: Path) -> None:
        """Edge: a seconds value that is not a number is a config error, not a pass."""
        toml = _budget(tmp_path, '[tool.slow-test-budget]\n"tests/test_alpha.py" = "soon"\n')
        assert budget_gate.main([str(_junit(tmp_path)), "--budget", str(toml)]) == 2

    def test_a_missing_budget_file_exits_three(self, tmp_path: Path) -> None:
        assert (
            budget_gate.main(
                [str(_junit(tmp_path)), "--budget", str(tmp_path / "absent.toml")]
            )
            == 3
        )

    def test_a_missing_input_exits_three(self, tmp_path: Path) -> None:
        toml = _budget(tmp_path, '[tool.slow-test-budget]\n"tests/test_alpha.py" = 20.0\n')
        assert (
            budget_gate.main([str(tmp_path / "absent.xml"), "--budget", str(toml)]) == 3
        )

    def test_an_empty_report_exits_one(self, tmp_path: Path) -> None:
        """No records means the run measured nothing, which is not a pass."""
        empty = tmp_path / "junit.xml"
        empty.write_text(
            '<?xml version="1.0"?><testsuites><testsuite name="pytest"/></testsuites>',
            encoding="utf-8",
        )
        toml = _budget(tmp_path, '[tool.slow-test-budget]\n"tests/test_alpha.py" = 20.0\n')
        assert budget_gate.main([str(empty), "--budget", str(toml)]) == 1


class TestTheShippedBudget:
    def test_it_names_modules_that_exist(self) -> None:
        """A typo'd key silently budgets nothing, which is the gate failing open."""
        budget = budget_gate.load_budget(REPO_ROOT / "pyproject.toml")
        assert budget, "pyproject.toml declares no [tool.slow-test-budget] entries"
        for module, seconds in budget.items():
            assert (REPO_ROOT / module).is_file(), module
            assert seconds > 0, module

    def test_the_workflow_runs_the_gate_in_the_coverage_job_over_merged_junit(self) -> None:
        """The gate is wired, not merely available (ci-scripts.md items 11 and 13).

        pytest-split cuts one file across legs, so a per-leg gate could see only
        a fraction of a budgeted suite. The gate must run once, in the job that
        downloads every leg's report, and its input pattern must match the
        junit file of every matrix leg.
        """
        import fnmatch
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
        pattern = next(t for t in tokens if t.endswith(".xml"))
        names = [s.get("name") for s in steps]
        assert names.index("Download partition artifacts") < steps.index(gate[0])
        for leg in jobs["test"]["strategy"]["matrix"]["include"]:
            assert fnmatch.fnmatch(leg["junit_file"], pattern), leg["partition"]


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

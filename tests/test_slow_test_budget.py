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

    def test_the_workflow_runs_the_gate_on_the_junit_it_writes(self) -> None:
        """The gate is wired, not merely available (ci-scripts.md items 11 and 13)."""
        import yaml

        workflow = yaml.safe_load(
            (REPO_ROOT / ".github/workflows/pytest.yml").read_text(encoding="utf-8")
        )
        steps = workflow["jobs"]["test"]["steps"]
        gate = [s for s in steps if "slow_test_budget.py" in str(s.get("run", ""))]
        assert len(gate) == 1, "the slow-test budget gate is not wired into pytest.yml"
        assert "--budget pyproject.toml" in gate[0]["run"]
        assert "${{ matrix.junit_file }}" in gate[0]["run"]

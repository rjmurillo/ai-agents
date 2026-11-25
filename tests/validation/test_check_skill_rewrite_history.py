"""Branch history rules of the ADR-127 evidence check: append-only results and scenarios."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.validation.skill_rewrite_helpers import (
    EVID,
    SCEN,
    SKILL,
    checker,
    commit,
    driver_change,
    git,
    repo,
    results,
    run,
    scenario_doc,
    skill_md,
    write,
)

__all__ = ["repo"]


class TestAppendOnly:
    def test_editing_a_results_file_blocks(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        driver_change(repo)
        write(repo, f"{EVID}/run-1.json", results(repo, {"S1": ("PPP", "FFF")}, verdict="FAIL"))
        commit(repo, "failed run")
        write(repo, f"{EVID}/run-1.json", results(repo))
        commit(repo, "overwrite")
        code, out = run(repo, capsys)
        assert code == 1
        assert "run-1.json is edited or deleted in" in out

    def test_deleting_a_results_file_blocks(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        driver_change(repo)
        write(repo, f"{EVID}/run-1.json", results(repo, {"S1": ("PPP", "FFF")}, verdict="FAIL"))
        commit(repo, "failed run")
        git(repo, "rm", "-q", f"{EVID}/run-1.json")
        write(repo, f"{EVID}/run-2.json", results(repo))
        commit(repo, "swap")
        code, out = run(repo, capsys)
        assert code == 1
        assert "run-1.json is edited or deleted in" in out

    def test_retired_file_may_change(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        driver_change(repo)
        write(repo, f"{EVID}/retired.json", json.dumps({"retired": []}))
        commit(repo, "retired")
        write(repo, f"{EVID}/retired.json", json.dumps({"retired": [], "note": "x"}))
        write(repo, f"{EVID}/run-1.json", results(repo))
        commit(repo, "evidence")
        code, out = run(repo, capsys)
        assert code == 0, out

    def test_merge_resolution_edit_blocks(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        driver_change(repo)
        write(repo, f"{EVID}/run-1.json", results(repo, {"S1": ("PPP", "FFF")}, verdict="FAIL"))
        commit(repo, "failed run")
        git(repo, "checkout", "-q", "-b", "side", "HEAD~1")
        write(repo, f"{EVID}/run-1.json", results(repo))
        commit(repo, "side run")
        git(repo, "checkout", "-q", "feature")
        subprocess.run(
            ["git", "-C", str(repo), "-c", "commit.gpgsign=false", "merge", "-q", "side"],
            capture_output=True,
            check=False,
            timeout=60,
        )
        write(repo, f"{EVID}/run-1.json", results(repo))
        commit(repo, "resolve")
        code, out = run(repo, capsys)
        assert code == 1
        assert "run-1.json is added again in" in out

    def test_runner_edit_in_a_gated_branch_blocks(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        driver_change(repo)
        write(repo, "scripts/eval/eval-prompt-change.py", "# lenient\n")
        write(repo, f"{EVID}/run-1.json", results(repo))
        commit(repo, "evidence and runner")
        code, out = run(repo, capsys)
        assert code == 1
        assert "a gated change may not also change ['scripts/eval/eval-prompt-change.py']" in out

    def test_runner_edit_alone_is_not_gated(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        write(repo, "scripts/eval/eval-prompt-change.py", "# change\n")
        commit(repo, "runner")
        assert run(repo, capsys)[0] == 0

    def test_label_flip_blocks(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        doc = json.loads(scenario_doc())
        doc["scenarios"][0]["expected_verdict"] = "STOP"
        write(repo, SCEN, json.dumps(doc))
        commit(repo, "scenario commit")
        driver_change(repo)
        write(repo, f"{EVID}/run-1.json", results(repo))
        commit(repo, "evidence")
        code, out = run(repo, capsys)
        assert code == 1
        assert "scenario S1 changes expected_verdict from 'GO' to 'STOP'" in out

    def test_head_ref_reads_the_named_commit(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        driver_change(repo)
        write(repo, f"{EVID}/run-1.json", results(repo))
        tip = commit(repo, "evidence")
        write(repo, SKILL, skill_md("driver", body="after the run"))
        commit(repo, "late edit")
        code = checker.main(["--repo-root", str(repo), "--base-ref", "main", "--head-ref", tip])
        assert code == 0, capsys.readouterr().out
        assert run(repo, capsys)[0] == 1


class TestScenarioFile:
    def test_missing_scenario_file(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        git(repo, "rm", "-q", SCEN)
        commit(repo, "drop scenarios")
        driver_change(repo)
        code, out = run(repo, capsys)
        assert code == 1
        assert f"{SCEN} does not exist" in out

    def test_invalid_scenario_json(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        write(repo, SCEN, "{")
        commit(repo, "break")
        driver_change(repo)
        code, out = run(repo, capsys)
        assert code == 1
        assert "is not valid scenario JSON" in out

    def test_scenario_without_expected_verdict(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        write(repo, SCEN, json.dumps({"scenarios": [{"id": "S1"}]}))
        commit(repo, "thin")
        driver_change(repo)
        code, out = run(repo, capsys)
        assert code == 1
        assert "has a scenario with no expected_verdict" in out

    def test_scenario_without_id(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        write(repo, SCEN, json.dumps({"scenarios": [{"expected_verdict": "GO"}]}))
        commit(repo, "no id")
        driver_change(repo)
        code, out = run(repo, capsys)
        assert code == 1
        assert "is not valid scenario JSON with an id on every scenario" in out

    def test_scenario_edit_after_surface_commit_blocks(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        driver_change(repo)
        doc = json.loads(scenario_doc())
        doc["scenarios"][0]["desc"] = "changed"
        write(repo, SCEN, json.dumps(doc))
        commit(repo, "late scenario edit")
        write(repo, f"{EVID}/run-1.json", results(repo))
        commit(repo, "evidence")
        code, out = run(repo, capsys)
        assert code == 1
        assert "changes in or after the first commit that touches the skill" in out

    def test_scenario_commit_before_surface_is_allowed(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        write(repo, SCEN, scenario_doc(9))
        commit(repo, "scenario commit")
        driver_change(repo)
        write(repo, f"{EVID}/run-1.json", results(repo))
        commit(repo, "evidence")
        code, out = run(repo, capsys)
        assert code == 0, out

    def test_dropped_scenario_without_retired_file(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self._base_with_nine(repo)
        write(repo, SCEN, scenario_doc(8))
        commit(repo, "drop S9")
        driver_change(repo)
        write(repo, f"{EVID}/run-1.json", results(repo))
        commit(repo, "evidence")
        code, out = run(repo, capsys)
        assert code == 1
        assert "scenarios ['S9'] were dropped" in out

    @pytest.mark.parametrize(
        ("retired", "message"),
        [
            ("[1]", "is not valid JSON with a 'retired' list"),
            ("{", "is not valid JSON with a 'retired' list"),
            (json.dumps({"retired": [{"scenario": "S9"}]}), "has no replacing test"),
            (
                json.dumps({"retired": [{"scenario": "S9", "test": "tests/nope.py::test_x"}]}),
                "does not exist at HEAD",
            ),
            (
                json.dumps(
                    {"retired": [{"scenario": "S9", "test": "tests/skills/demo/test_demo.py::t"}]}
                ),
                "does not exist at HEAD",
            ),
        ],
    )
    def test_retired_file_errors(
        self, repo: Path, capsys: pytest.CaptureFixture[str], retired: str, message: str
    ) -> None:
        self._base_with_nine(repo)
        write(repo, SCEN, scenario_doc(8))
        write(repo, f"{EVID}/retired.json", retired)
        commit(repo, "drop S9")
        driver_change(repo)
        write(repo, f"{EVID}/run-1.json", results(repo))
        commit(repo, "evidence")
        code, out = run(repo, capsys)
        assert code == 1
        assert message in out

    def test_retired_with_real_test_passes(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self._base_with_nine(repo)
        write(repo, SCEN, scenario_doc(8))
        test = "tests/skills/demo/test_demo.py::TestX::test_replaces"
        write(
            repo,
            f"{EVID}/retired.json",
            json.dumps({"retired": [{"scenario": "S9", "test": test}]}),
        )
        commit(repo, "drop S9")
        driver_change(repo)
        write(repo, f"{EVID}/run-1.json", results(repo))
        commit(repo, "evidence")
        code, out = run(repo, capsys)
        assert code == 0, out

    @pytest.mark.parametrize("broken", ["{", json.dumps({"scenarios": 3})])
    def test_unreadable_base_scenarios_fail_closed(
        self, repo: Path, capsys: pytest.CaptureFixture[str], broken: str
    ) -> None:
        git(repo, "checkout", "-q", "main")
        write(repo, SCEN, broken)
        commit(repo, "broken on main")
        git(repo, "checkout", "-q", "-B", "feature")
        write(repo, SCEN, scenario_doc())
        commit(repo, "scenario commit")
        driver_change(repo)
        write(repo, f"{EVID}/run-1.json", results(repo))
        commit(repo, "evidence")
        code, out = run(repo, capsys)
        assert code == 1
        assert "does not parse at the merge base" in out

    def test_scenario_file_new_on_branch(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        git(repo, "checkout", "-q", "main")
        git(repo, "rm", "-q", SCEN)
        commit(repo, "no scenarios on main")
        git(repo, "checkout", "-q", "-B", "feature")
        write(repo, SCEN, scenario_doc())
        commit(repo, "scenario commit")
        driver_change(repo)
        write(repo, f"{EVID}/run-1.json", results(repo))
        commit(repo, "evidence")
        code, out = run(repo, capsys)
        assert code == 0, out

    @staticmethod
    def _base_with_nine(repo: Path) -> None:
        git(repo, "checkout", "-q", "main")
        write(repo, SCEN, scenario_doc(9))
        commit(repo, "nine on main")
        git(repo, "checkout", "-q", "-B", "feature")

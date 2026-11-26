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
    commit_evidence,
    driver_change,
    git,
    on_main,
    repo,
    results,
    run,
    run_gated,
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
        commit_evidence(repo)
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

    def test_results_added_by_a_merge_commit_counts_as_added(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        driver_change(repo)
        git(repo, "checkout", "-q", "-b", "side")
        write(repo, "side.txt", "side\n")
        commit(repo, "side")
        git(repo, "checkout", "-q", "feature")
        write(repo, "feature.txt", "feature\n")
        commit(repo, "feature")
        git(repo, "-c", "commit.gpgsign=false", "merge", "-q", "--no-commit", "side")
        write(repo, f"{EVID}/run-1.json", results(repo))
        commit(repo, "merge side with evidence")
        code, out = run(repo, capsys)
        assert code == 0, out

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
        code, out = run_gated(repo, capsys)
        assert code == 1
        assert "scenario S1 changes expected_verdict from 'GO' to 'STOP'" in out

    def test_label_case_only_edit_is_not_a_flip(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        doc = json.loads(scenario_doc())
        doc["scenarios"][0]["expected_verdict"] = "go "
        write(repo, SCEN, json.dumps(doc))
        commit(repo, "scenario commit")
        code, out = run_gated(repo, capsys)
        assert code == 0, out
        assert "changes expected_verdict" not in out

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
        code, out = run_gated(repo, capsys, evidence=False)
        assert code == 1
        assert f"{SCEN} does not exist" in out

    def test_invalid_scenario_json(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        write(repo, SCEN, "{")
        commit(repo, "break")
        code, out = run_gated(repo, capsys, evidence=False)
        assert code == 1
        assert "is not valid scenario JSON" in out

    def test_top_level_array_corpus_is_accepted(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        write(repo, SCEN, json.dumps(json.loads(scenario_doc())["scenarios"]))
        commit(repo, "array corpus")
        code, out = run_gated(repo, capsys)
        assert code == 0, out

    def test_duplicate_ids_do_not_satisfy_the_floors(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rows = [{"id": "S1", "desc": "d", "input": "i", "expected_verdict": "GO"}] * 8
        on_main(repo, {SCEN: json.dumps({"scenarios": rows})}, "eight copies of one scenario")
        driver_change(repo)
        doc = json.loads(results(repo))
        doc["detail"] = {side: rows[:1] for side, rows in doc["detail"].items()}
        write(repo, f"{EVID}/run-1.json", json.dumps(doc))
        commit(repo, "one result row stands in for eight")
        code, out = run(repo, capsys)
        assert code == 1
        assert f"{SCEN} repeats scenario ids ['S1']" in out

    @staticmethod
    def _options_outside_label() -> bytes:
        doc = json.loads(scenario_doc())
        doc["scenarios"][0]["verdict_options"] = ["STOP", "HOLD"]
        return json.dumps(doc).encode()

    @pytest.mark.parametrize(
        ("corpus", "detail"),
        [
            ("options", "is not in verdict_options"),
            ("utf16", "codec can't decode"),
        ],
    )
    def test_a_corpus_the_runner_rejects_is_a_finding(
        self, repo: Path, capsys: pytest.CaptureFixture[str], corpus: str, detail: str
    ) -> None:
        """The gate runs the runner's own parse, and a decode error is a finding, not a crash."""
        data = (
            self._options_outside_label()
            if corpus == "options"
            else scenario_doc().encode("utf-16")
        )
        write(repo, SCEN, data)
        commit(repo, f"corpus the runner rejects: {corpus}")
        code, out = run_gated(repo, capsys, evidence=False)
        assert code == 1
        assert "fails the eval runner's scenario checks" in out
        assert detail in out

    def test_ids_that_differ_only_in_case_are_distinct(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rows = json.loads(scenario_doc())["scenarios"]
        rows[0]["id"], rows[1]["id"] = "S1", "s1"
        write(repo, SCEN, json.dumps({"scenarios": rows}))
        commit(repo, "case-distinct ids")
        code, out = run_gated(repo, capsys, evidence=False)
        assert "repeats scenario ids" not in out

    def test_ids_that_collide_after_str_are_duplicates(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rows = json.loads(scenario_doc())["scenarios"]
        rows[0]["id"], rows[1]["id"] = 1, "1"
        write(repo, SCEN, json.dumps({"scenarios": rows}))
        commit(repo, "int and string id")
        code, out = run_gated(repo, capsys, evidence=False)
        assert code == 1
        assert f"{SCEN} repeats scenario ids ['1']" in out

    def test_scenario_without_expected_verdict(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        write(repo, SCEN, json.dumps({"scenarios": [{"id": "S1"}]}))
        commit(repo, "thin")
        code, out = run_gated(repo, capsys, evidence=False)
        assert code == 1
        assert "has a scenario with no expected_verdict" in out

    def test_scenario_without_id(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        write(repo, SCEN, json.dumps({"scenarios": [{"expected_verdict": "GO"}]}))
        commit(repo, "no id")
        code, out = run_gated(repo, capsys, evidence=False)
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
        commit_evidence(repo)
        code, out = run(repo, capsys)
        assert code == 1
        assert "changes in or after the first commit that touches the skill" in out

    def test_template_lookalike_path_is_not_the_skill_surface(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A `.notes` sibling of the template shares its prefix and is not the template."""
        write(repo, SCEN, scenario_doc(9))
        write(repo, "templates/skills/demo.SKILL.md.tmpl.notes", "notes\n")
        commit(repo, "scenario edit beside a template lookalike")
        commit_evidence(repo)
        code, out = run(repo, capsys)
        assert code == 0, out

    def test_exact_template_path_is_the_skill_surface(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        write(repo, SCEN, scenario_doc(9))
        write(repo, "templates/skills/demo.SKILL.md.tmpl", "template\n")
        commit(repo, "scenario edit beside the template")
        commit_evidence(repo)
        code, out = run(repo, capsys)
        assert code == 1
        assert "changes in or after the first commit that touches the skill" in out

    def test_scenario_commit_before_surface_is_allowed(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        write(repo, SCEN, scenario_doc(9))
        commit(repo, "scenario commit")
        code, out = run_gated(repo, capsys)
        assert code == 0, out

    def test_dropped_scenario_without_retired_file(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self._base_with_nine(repo)
        write(repo, SCEN, scenario_doc(8))
        commit(repo, "drop S9")
        code, out = run_gated(repo, capsys)
        assert code == 1
        assert "scenarios ['S9'] were dropped" in out

    @pytest.mark.parametrize(
        ("retired", "message"),
        [
            ("[1]", "is not valid JSON with a 'retired' list"),
            ("{", "is not valid JSON with a 'retired' list"),
            (json.dumps({"retired": [{"scenario": "S9"}]}), "has no replacing test"),
            (
                json.dumps(
                    {
                        "retired": [
                            {"scenario": "S9", "test": "tests/skills/demo/test_nope.py::test_x"}
                        ]
                    }
                ),
                "does not exist at HEAD",
            ),
            (
                json.dumps(
                    {"retired": [{"scenario": "S9", "test": "tests/skills/demo/test_demo.py::t"}]}
                ),
                "does not exist at HEAD",
            ),
            (
                json.dumps(
                    {
                        "retired": [
                            {
                                "scenario": "S9",
                                "test": "tests/skills/demo/test_demo.py::TestNope::test_replaces",
                            }
                        ]
                    }
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
        code, out = run_gated(repo, capsys)
        assert code == 1
        assert message in out

    @pytest.mark.parametrize("scenario", [["S9"], {"id": "S9"}, 9, None])
    def test_retired_row_with_a_non_string_scenario_id_is_a_finding(
        self, repo: Path, capsys: pytest.CaptureFixture[str], scenario: object
    ) -> None:
        self._base_with_nine(repo)
        write(repo, SCEN, scenario_doc(8))
        test = "tests/skills/demo/test_demo.py::TestX::test_replaces"
        write(
            repo,
            f"{EVID}/retired.json",
            json.dumps({"retired": [{"scenario": scenario, "test": test}]}),
        )
        commit(repo, "drop S9")
        code, out = run_gated(repo, capsys)
        assert code == 1
        assert "is not a string" in out
        assert "dropped scenario S9 has no replacing test" in out

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
        code, out = run_gated(repo, capsys)
        assert code == 0, out

    def _retire_with(
        self, repo: Path, capsys: pytest.CaptureFixture[str], test: str
    ) -> tuple[int, str]:
        self._base_with_nine(repo)
        write(repo, SCEN, scenario_doc(8))
        retired = json.dumps({"retired": [{"scenario": "S9", "test": test}]})
        write(repo, f"{EVID}/retired.json", retired)
        commit(repo, "drop S9")
        return run_gated(repo, capsys)

    @pytest.mark.parametrize(
        "test",
        [
            "tests/skills/demo/test_demo.py::TestX::test_replaces[case-1]",
            "tests/skills/demo/test_demo.py::TestX::test_replaces[a::b]",
        ],
    )
    def test_retired_test_with_a_parameter_id_is_rejected(
        self, repo: Path, capsys: pytest.CaptureFixture[str], test: str
    ) -> None:
        code, out = self._retire_with(repo, capsys, test)
        assert code == 1
        assert "name the function without a parameter id" in out

    @pytest.mark.parametrize(
        "path",
        [
            "tests/skills/demo/helpers.py",
            "tests/skills/demo/demo_test.py",
            "scripts/test_demo.py",
        ],
    )
    def test_retired_test_in_a_file_pytest_skips_is_rejected(
        self, repo: Path, capsys: pytest.CaptureFixture[str], path: str
    ) -> None:
        write(repo, path, "class TestX:\n    def test_replaces(self):\n        pass\n")
        code, out = self._retire_with(repo, capsys, f"{path}::TestX::test_replaces")
        assert code == 1
        assert "is not collected by pytest" in out

    @pytest.mark.parametrize("test", ["Helper::test_replaces", "TestX::replaces"])
    def test_retired_test_pytest_would_not_name_is_rejected(
        self, repo: Path, capsys: pytest.CaptureFixture[str], test: str
    ) -> None:
        demo = "class Helper:\n    def test_replaces(self):\n        pass\n"
        demo += "class TestX:\n    def replaces(self):\n        pass\n"
        write(repo, "tests/skills/demo/test_demo.py", demo)
        code, out = self._retire_with(repo, capsys, f"tests/skills/demo/test_demo.py::{test}")
        assert code == 1
        assert "does not exist at HEAD" in out

    @pytest.mark.parametrize(
        "skipped_class",
        [
            "class TestX:\n    __test__ = False\n\n    def test_replaces(self):\n        pass\n",
            "class TestX:\n    def __init__(self):\n        pass\n\n"
            "    def test_replaces(self):\n        pass\n",
        ],
        ids=["test-false", "own-init"],
    )
    def test_retired_test_in_a_class_pytest_skips_is_rejected(
        self, repo: Path, capsys: pytest.CaptureFixture[str], skipped_class: str
    ) -> None:
        path = "tests/skills/demo/test_demo.py"
        write(repo, path, skipped_class)
        code, out = self._retire_with(repo, capsys, f"{path}::TestX::test_replaces")
        assert code == 1
        assert (
            f"dropped scenario S9: test {path}::TestX::test_replaces does not exist at HEAD" in out
        )

    @pytest.mark.parametrize("broken", ["{", json.dumps({"scenarios": 3})])
    def test_unreadable_base_scenarios_fail_closed(
        self, repo: Path, capsys: pytest.CaptureFixture[str], broken: str
    ) -> None:
        on_main(repo, {SCEN: broken}, "broken on main")
        write(repo, SCEN, scenario_doc())
        commit(repo, "scenario commit")
        code, out = run_gated(repo, capsys)
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
        code, out = run_gated(repo, capsys)
        assert code == 0, out

    @staticmethod
    def _base_with_nine(repo: Path) -> None:
        on_main(repo, {SCEN: scenario_doc(9)}, "nine on main")

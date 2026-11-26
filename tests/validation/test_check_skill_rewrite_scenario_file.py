"""Scenario-file rules of the ADR-127 evidence check: shape, freeze, drops, and retirement."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.validation.skill_rewrite_helpers import (
    EVID,
    SCEN,
    SKILL,
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

Capsys = pytest.CaptureFixture[str]


class TestScenarioFile:
    def test_missing_scenario_file(self, repo: Path, capsys: Capsys) -> None:
        git(repo, "rm", "-q", SCEN)
        commit(repo, "drop scenarios")
        code, out = run_gated(repo, capsys, evidence=False)
        assert code == 1
        assert f"{SCEN} does not exist" in out

    def test_invalid_scenario_json(self, repo: Path, capsys: Capsys) -> None:
        write(repo, SCEN, "{")
        commit(repo, "break")
        code, out = run_gated(repo, capsys, evidence=False)
        assert code == 1
        assert "is not valid scenario JSON" in out

    def test_top_level_array_corpus_is_accepted(self, repo: Path, capsys: Capsys) -> None:
        write(repo, SCEN, json.dumps(json.loads(scenario_doc())["scenarios"]))
        commit(repo, "array corpus")
        code, out = run_gated(repo, capsys)
        assert code == 0, out

    def test_duplicate_ids_do_not_satisfy_the_floors(self, repo: Path, capsys: Capsys) -> None:
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
        self, repo: Path, capsys: Capsys, corpus: str, detail: str
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

    def test_ids_that_differ_only_in_case_are_distinct(self, repo: Path, capsys: Capsys) -> None:
        rows = json.loads(scenario_doc())["scenarios"]
        rows.append({"id": "s1", "desc": "d", "input": "i", "expected_verdict": "GO"})
        assert {"S1", "s1"} <= {r["id"] for r in rows}
        write(repo, SCEN, json.dumps({"scenarios": rows}))
        commit(repo, "case-distinct ids")
        code, out = run_gated(repo, capsys)
        assert "repeats scenario ids" not in out
        assert code == 0, out

    def test_ids_that_collide_after_str_are_duplicates(self, repo: Path, capsys: Capsys) -> None:
        rows = json.loads(scenario_doc())["scenarios"]
        rows[0]["id"], rows[1]["id"] = 1, "1"
        write(repo, SCEN, json.dumps({"scenarios": rows}))
        commit(repo, "int and string id")
        code, out = run_gated(repo, capsys, evidence=False)
        assert code == 1
        assert f"{SCEN} repeats scenario ids ['1']" in out

    def test_scenario_without_expected_verdict(self, repo: Path, capsys: Capsys) -> None:
        write(repo, SCEN, json.dumps({"scenarios": [{"id": "S1"}]}))
        commit(repo, "thin")
        code, out = run_gated(repo, capsys, evidence=False)
        assert code == 1
        assert "has a scenario with no expected_verdict" in out

    def test_scenario_without_id(self, repo: Path, capsys: Capsys) -> None:
        write(repo, SCEN, json.dumps({"scenarios": [{"expected_verdict": "GO"}]}))
        commit(repo, "no id")
        code, out = run_gated(repo, capsys, evidence=False)
        assert code == 1
        assert "is not valid scenario JSON with an id on every scenario" in out

    def test_scenario_edit_after_surface_commit_blocks(self, repo: Path, capsys: Capsys) -> None:
        driver_change(repo)
        doc = json.loads(scenario_doc())
        doc["scenarios"][0]["desc"] = "changed"
        write(repo, SCEN, json.dumps(doc))
        commit(repo, "late scenario edit")
        commit_evidence(repo)
        code, out = run(repo, capsys)
        assert code == 1
        assert "differs at" in out
        assert "a commit that touches the skill" in out

    def test_scenario_and_skill_in_one_commit_blocks(self, repo: Path, capsys: Capsys) -> None:
        write(repo, SCEN, scenario_doc(9))
        write(repo, SKILL, skill_md("driver", body="Changed body."))
        commit(repo, "scenario and skill together")
        commit_evidence(repo)
        code, out = run(repo, capsys)
        assert code == 1
        assert "changes in the same commit as the skill" in out

    def test_scenario_added_after_the_skill_changed_blocks(
        self, repo: Path, capsys: Capsys
    ) -> None:
        git(repo, "checkout", "-q", "main")
        git(repo, "rm", "-q", SCEN)
        commit(repo, "no scenarios on main")
        git(repo, "checkout", "-q", "-B", "feature")
        driver_change(repo)
        write(repo, SCEN, scenario_doc())
        commit(repo, "scenario after the skill")
        commit_evidence(repo)
        code, out = run(repo, capsys)
        assert code == 1
        assert "differs at" in out

    def test_scenario_edit_reverted_after_the_skill_changed_blocks(
        self, repo: Path, capsys: Capsys
    ) -> None:
        driver_change(repo)
        write(repo, SCEN, scenario_doc(9))
        commit(repo, "late scenario edit")
        write(repo, SCEN, scenario_doc())
        commit(repo, "revert the late edit")
        commit_evidence(repo)
        code, out = run(repo, capsys)
        assert code == 1
        assert "after a commit that touches the skill" in out
        assert "differs at" not in out

    @staticmethod
    def _merge_side_branch(repo: Path) -> None:
        """Merge a branch cut from the base into the current branch, leaving the merge open."""
        git(repo, "checkout", "-q", "-b", "side", "main")
        write(repo, "docs/side.md", "side\n")
        commit(repo, "side work")
        git(repo, "checkout", "-q", "feature")
        git(repo, "merge", "-q", "--no-ff", "--no-commit", "side")

    def test_merge_restoring_an_older_corpus_after_the_skill_changed_blocks(
        self, repo: Path, capsys: Capsys
    ) -> None:
        write(repo, SCEN, scenario_doc(9))
        commit(repo, "scenario commit")
        driver_change(repo)
        self._merge_side_branch(repo)
        git(repo, "checkout", "main", "--", SCEN)
        commit(repo, "merge restores the base corpus")
        commit_evidence(repo)
        code, out = run(repo, capsys)
        assert code == 1
        assert "differs at" in out
        assert "a commit that touches the skill" in out

    def test_corpus_updated_before_the_skill_and_carried_through_a_merge_passes(
        self, repo: Path, capsys: Capsys
    ) -> None:
        write(repo, SCEN, scenario_doc(9))
        commit(repo, "scenario commit")
        self._merge_side_branch(repo)
        commit(repo, "merge side work")
        code, out = run_gated(repo, capsys)
        assert code == 0, out

    def test_template_lookalike_path_is_not_the_skill_surface(
        self, repo: Path, capsys: Capsys
    ) -> None:
        """A `.notes` sibling of the template shares its prefix and is not the template."""
        write(repo, SCEN, scenario_doc(9))
        write(repo, "templates/skills/demo.SKILL.md.tmpl.notes", "notes\n")
        commit(repo, "scenario edit beside a template lookalike")
        commit_evidence(repo)
        code, out = run(repo, capsys)
        assert code == 0, out

    def test_exact_template_path_is_the_skill_surface(self, repo: Path, capsys: Capsys) -> None:
        write(repo, SCEN, scenario_doc(9))
        write(repo, "templates/skills/demo.SKILL.md.tmpl", "template\n")
        commit(repo, "scenario edit beside the template")
        commit_evidence(repo)
        code, out = run(repo, capsys)
        assert code == 1
        assert "changes in the same commit as the skill" in out

    def test_scenario_commit_before_surface_is_allowed(self, repo: Path, capsys: Capsys) -> None:
        write(repo, SCEN, scenario_doc(9))
        commit(repo, "scenario commit")
        code, out = run_gated(repo, capsys)
        assert code == 0, out

    def test_dropped_scenario_without_retired_file(self, repo: Path, capsys: Capsys) -> None:
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
        self, repo: Path, capsys: Capsys, retired: str, message: str
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
        self, repo: Path, capsys: Capsys, scenario: object
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

    def test_retired_with_real_test_passes(self, repo: Path, capsys: Capsys) -> None:
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

    def _retire_with(self, repo: Path, capsys: Capsys, test: str) -> tuple[int, str]:
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
        self, repo: Path, capsys: Capsys, test: str
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
        self, repo: Path, capsys: Capsys, path: str
    ) -> None:
        write(repo, path, "class TestX:\n    def test_replaces(self):\n        pass\n")
        code, out = self._retire_with(repo, capsys, f"{path}::TestX::test_replaces")
        assert code == 1
        assert "is not collected by pytest" in out

    @pytest.mark.parametrize("test", ["Helper::test_replaces", "TestX::replaces"])
    def test_retired_test_pytest_would_not_name_is_rejected(
        self, repo: Path, capsys: Capsys, test: str
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
        self, repo: Path, capsys: Capsys, skipped_class: str
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
        self, repo: Path, capsys: Capsys, broken: str
    ) -> None:
        on_main(repo, {SCEN: broken}, "broken on main")
        write(repo, SCEN, scenario_doc())
        commit(repo, "scenario commit")
        code, out = run_gated(repo, capsys)
        assert code == 1
        assert "does not parse at the merge base" in out

    def test_scenario_file_new_on_branch(self, repo: Path, capsys: Capsys) -> None:
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

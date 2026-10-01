"""Tests for the post-integration regression extension (issue #5768).

The scenarios under `evals/durable-outcome-live/corpus/` carry a hidden
regression: an implementation that passes the local check and fails a check
that only exists after integration. These tests prove the loader, the
two-stage grader, and the control fixtures discriminate.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

from tests.eval._routing_integration_test_support import (
    EXTENSION_CORPUS,
    MERGE_SETTINGS,
    REAL_CORPUS,
    TASKS,
    TOP_SCORES,
    copy_extension,
    edit_scenario,
    grader,
    load_extension,
    read_scenario,
    scenario_mod,
)

RoutingCorpusError = scenario_mod.RoutingCorpusError
Verdict = grader.Verdict


@pytest.fixture
def extension(tmp_path: Path) -> Path:
    return copy_extension(tmp_path)


class TestLoading:
    def test_extension_corpus_holds_at_least_two_regression_scenarios(self) -> None:
        found = scenario_mod.load_extension_corpus(EXTENSION_CORPUS)

        assert {s.scenario_id for s in found} == set(TASKS)
        assert all(s.category is scenario_mod.Category.POST_INTEGRATION_REGRESSION for s in found)
        assert all(s.integration is not None for s in found)

    def test_the_routing_corpus_loader_refuses_an_extension_scenario(self, tmp_path: Path) -> None:
        mixed = tmp_path / "mixed"
        shutil.copytree(REAL_CORPUS, mixed)
        shutil.copytree(EXTENSION_CORPUS / TOP_SCORES, mixed / TOP_SCORES)

        with pytest.raises(RoutingCorpusError, match="extension corpus"):
            scenario_mod.load_corpus(mixed)

    def test_the_extension_loader_refuses_the_routing_corpus(self) -> None:
        with pytest.raises(RoutingCorpusError, match="only post_integration_regression"):
            scenario_mod.load_extension_corpus(REAL_CORPUS)

    def test_the_extension_loader_refuses_an_empty_corpus(self, tmp_path: Path) -> None:
        with pytest.raises(RoutingCorpusError, match="total: 0"):
            scenario_mod.load_extension_corpus(tmp_path)

    def test_the_extension_loader_refuses_a_missing_root(self, tmp_path: Path) -> None:
        with pytest.raises(RoutingCorpusError, match="not a directory"):
            scenario_mod.load_extension_corpus(tmp_path / "absent")

    def test_the_routing_corpus_has_no_integration_block(self) -> None:
        assert all(s.integration is None for s in scenario_mod.load_corpus(REAL_CORPUS))

    def test_integration_files_are_not_driver_visible(self) -> None:
        from _routing_hygiene import driver_visible_text

        for task in TASKS:
            text = "\n".join(body for _, body in driver_visible_text(load_extension(task)))
            assert "INTEGRATION_REGRESSION" not in text
            assert "verify_" not in text


class TestSchemaRefusals:
    def test_a_regression_scenario_without_an_integration_block_is_refused(
        self, extension: Path
    ) -> None:
        edit_scenario(extension, TOP_SCORES, integration=None)

        with pytest.raises(RoutingCorpusError, match="integration is required"):
            scenario_mod.load_extension_corpus(extension)

    def test_an_integration_block_on_another_category_is_refused(self, extension: Path) -> None:
        edit_scenario(extension, TOP_SCORES, category="scope_expansion")

        with pytest.raises(RoutingCorpusError, match="integration is required"):
            scenario_mod.load_extension_corpus(extension)

    @pytest.mark.parametrize("name", ["integration", "hidden_regression"])
    def test_a_missing_overlay_directory_is_refused(self, extension: Path, name: str) -> None:
        shutil.rmtree(extension / TOP_SCORES / name)

        with pytest.raises(RoutingCorpusError, match=f"{name}/ must hold files"):
            scenario_mod.load_extension_corpus(extension)

    @pytest.mark.parametrize(
        "change",
        [
            {"evidence_marker": ""},
            {"evidence_marker": None},
            {"commands": [["pytest"]]},
            {"commands": []},
            {"timeout_seconds": 0},
            {"timeout_seconds": "60"},
            {"extra": 1},
        ],
    )
    def test_a_malformed_integration_block_is_refused(
        self, extension: Path, change: dict[str, Any]
    ) -> None:
        block = dict(read_scenario(extension, TOP_SCORES)["integration"])
        for key, value in change.items():
            if value is None:
                block.pop(key, None)
            else:
                block[key] = value
        edit_scenario(extension, TOP_SCORES, integration=block)

        with pytest.raises(RoutingCorpusError):
            scenario_mod.load_extension_corpus(extension)


class TestControls:
    @pytest.mark.parametrize("task", TASKS)
    def test_every_control_check_holds(self, task: str) -> None:
        report = grader.verify_controls(load_extension(task))

        assert report.ok, [(c.name, c.detail) for c in report.checks if not c.ok]
        assert {c.name for c in report.checks} >= {
            "known_good_passes_integration",
            "hidden_regression_passes_local",
            "hidden_regression_fails_integration",
            "hidden_regression_evidence_matches",
        }

    @pytest.mark.parametrize("task", TASKS)
    def test_known_good_passes_both_stages(self, task: str) -> None:
        scenario = load_extension(task)

        assert grader.grade_overlay(scenario, "known_good").verdict is Verdict.PASS
        assert grader.grade_integration_overlay(scenario, "known_good").verdict is Verdict.PASS

    @pytest.mark.parametrize("task", TASKS)
    def test_known_bad_fails_the_local_check(self, task: str) -> None:
        assert grader.grade_overlay(load_extension(task), "known_bad").verdict is Verdict.FAIL

    @pytest.mark.parametrize("task", TASKS)
    def test_hidden_regression_passes_local_and_fails_integration(self, task: str) -> None:
        scenario = load_extension(task)

        local = grader.grade_overlay(scenario, "hidden_regression")
        integrated = grader.grade_integration_overlay(scenario, "hidden_regression")

        assert local.verdict is Verdict.PASS
        assert integrated.verdict is Verdict.FAIL
        assert scenario.integration is not None
        assert scenario.integration.evidence_marker in integrated.output

    @pytest.mark.parametrize("task", TASKS)
    def test_the_untouched_baseline_fails(self, task: str) -> None:
        assert grader.grade_overlay(load_extension(task)).verdict is Verdict.FAIL

    def test_a_hidden_regression_that_also_fails_locally_breaks_the_control(
        self, extension: Path
    ) -> None:
        overlay = extension / TOP_SCORES / "hidden_regression" / "tally" / "ranking.py.fixture"
        overlay.write_text("def top_scores(scores, n):\n    return []\n", encoding="utf-8")

        report = grader.verify_controls(
            next(
                s
                for s in scenario_mod.load_extension_corpus(extension)
                if s.scenario_id == TOP_SCORES
            )
        )

        failed = {c.name for c in report.checks if not c.ok}
        assert not report.ok and "hidden_regression_passes_local" in failed

    def test_a_known_good_that_breaks_integration_breaks_the_control(self, extension: Path) -> None:
        source = extension / TOP_SCORES
        shutil.copyfile(
            source / "hidden_regression" / "tally" / "ranking.py.fixture",
            source / "known_good" / "tally" / "ranking.py.fixture",
        )

        scenario = next(
            s
            for s in scenario_mod.load_extension_corpus(extension)
            if s.scenario_id == TOP_SCORES
        )
        report = grader.verify_controls(scenario)

        assert not report.ok
        assert "known_good_passes_integration" in {c.name for c in report.checks if not c.ok}


class TestGradeIntegration:
    def test_a_scenario_without_an_integration_block_is_refused(self, tmp_path: Path) -> None:
        plain = scenario_mod.load_corpus(REAL_CORPUS)[0]

        with pytest.raises(RoutingCorpusError, match="no integration check"):
            grader.grade_integration(plain, tmp_path, [])

    def test_a_deleted_path_is_deleted_from_the_integrated_tree(self, tmp_path: Path) -> None:
        scenario = load_extension(TOP_SCORES)
        work = tmp_path / "work"
        grader.materialize(scenario, work, "known_good")
        (work / "tally" / "timeline.py").unlink()
        changed = grader.changed_paths(scenario, work)

        result = grader.grade_integration(scenario, work, changed)

        assert "tally/timeline.py" in changed
        assert result.verdict is Verdict.FAIL

    def test_the_drivers_directory_is_left_untouched(self, tmp_path: Path) -> None:
        scenario = load_extension(MERGE_SETTINGS)
        work = tmp_path / "work"
        grader.materialize(scenario, work, "hidden_regression")
        before = grader.manifest(work)

        grader.grade_integration(scenario, work, grader.changed_paths(scenario, work))

        assert grader.manifest(work) == before

    def test_unknown_overlay_is_still_refused(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="unknown overlay"):
            grader.materialize(load_extension(TOP_SCORES), tmp_path / "w", "nope")

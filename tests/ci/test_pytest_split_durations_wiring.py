"""pytest.yml restores split timings on every split leg and saves them only from main.

Nobody maintains a durations file. The Actions cache carries the map, and the
trust boundary is who may write it: Actions scopes a cache to the ref that saved
it, so a pull request reads the base branch's cache but cannot plant timings.
That holds only while the one save step stays gated on a push to main.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.ci import run_pytest_partition as runner

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "pytest.yml"
KEY_PREFIX = "pytest-split-durations-"
_CACHE_USES = re.compile(r"^\s*(?:- )?uses:\s*(actions/cache/(?:restore|save))@(\S+)\s*(#.*)?$")
_SHA = re.compile(r"^[0-9a-f]{40}$")


@pytest.fixture(scope="module")
def jobs() -> dict[str, Any]:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]


def _steps(jobs: dict[str, Any], job: str, action: str) -> list[dict[str, Any]]:
    return [s for s in jobs[job]["steps"] if str(s.get("uses", "")).startswith(action + "@")]


def _all_cache_steps(jobs: dict[str, Any], action: str) -> list[tuple[str, dict[str, Any]]]:
    return [(job, step) for job in jobs for step in _steps(jobs, job, action)]


class TestRestoreOnEverySplitLeg:
    def test_the_test_job_restores_the_map_to_the_path_the_runner_reads(
        self, jobs: dict[str, Any]
    ) -> None:
        (step,) = _steps(jobs, "test", "actions/cache/restore")
        assert step["with"]["path"] == runner.DURATIONS_RESTORE_PATH

    def test_restore_keys_is_the_prefix_so_the_newest_cache_wins(self, jobs: dict[str, Any]) -> None:
        (step,) = _steps(jobs, "test", "actions/cache/restore")
        assert step["with"]["restore-keys"] == KEY_PREFIX
        assert step["with"]["key"].startswith(KEY_PREFIX)

    def test_the_restore_step_selects_the_split_legs_and_no_other(
        self, jobs: dict[str, Any]
    ) -> None:
        (step,) = _steps(jobs, "test", "actions/cache/restore")
        assert step["if"] == "startsWith(matrix.partition, 'split-')"
        partitions = [leg["partition"] for leg in jobs["test"]["strategy"]["matrix"]["include"]]
        split_legs = [p for p in partitions if p.startswith("split-")]
        assert split_legs == runner.split_names()
        assert all(p in runner._PARALLEL_PARTITIONS for p in split_legs)

    def test_the_restore_runs_before_pytest(self, jobs: dict[str, Any]) -> None:
        names = [s.get("name") for s in jobs["test"]["steps"]]
        assert names.index("Restore pytest-split durations") < names.index("Run pytest")


class TestSaveOnlyFromMain:
    def test_exactly_one_save_step_writes_the_durations_cache(self, jobs: dict[str, Any]) -> None:
        saves = [
            (job, step)
            for job, step in _all_cache_steps(jobs, "actions/cache/save")
            if step["with"]["key"].startswith(KEY_PREFIX)
        ]
        assert [job for job, _ in saves] == ["test-durations"]

    def test_no_split_leg_job_saves_any_cache(self, jobs: dict[str, Any]) -> None:
        assert _steps(jobs, "test", "actions/cache/save") == []

    def test_the_save_is_gated_on_a_push_to_main(self, jobs: dict[str, Any]) -> None:
        (step,) = [
            s
            for s in _steps(jobs, "test-durations", "actions/cache/save")
            if s["with"]["key"].startswith(KEY_PREFIX)
        ]
        condition = step["if"]
        assert "github.event_name == 'push'" in condition
        assert "github.ref == 'refs/heads/main'" in condition

    def test_the_save_condition_never_names_a_pull_request_or_merge_group(
        self, jobs: dict[str, Any]
    ) -> None:
        for job, step in _all_cache_steps(jobs, "actions/cache/save"):
            condition = str(step.get("if", ""))
            assert "pull_request" not in condition, job
            assert "merge_group" not in condition, job

    def test_a_workflow_comment_states_why_a_pull_request_cannot_write_it(self) -> None:
        comments = " ".join(
            line.strip().removeprefix("#").strip()
            for line in WORKFLOW.read_text(encoding="utf-8").splitlines()
            if line.strip().startswith("#")
        )
        assert "a pull request cannot plant timings" in comments
        assert "Never save from pull_request or merge_group" in comments


class TestMergeFeedsTheSave:
    def test_the_merge_reads_every_leg_file_the_runner_writes(self, jobs: dict[str, Any]) -> None:
        (merge,) = [s for s in jobs["test-durations"]["steps"] if s.get("id") == "merge-durations"]
        command = " ".join(str(merge["run"]).split())
        for name in runner.split_names():
            assert runner._leg_durations_path(name) in command

    def test_the_save_path_is_the_merge_output(self, jobs: dict[str, Any]) -> None:
        (merge,) = [s for s in jobs["test-durations"]["steps"] if s.get("id") == "merge-durations"]
        (save,) = [
            s
            for s in _steps(jobs, "test-durations", "actions/cache/save")
            if s["with"]["key"].startswith(KEY_PREFIX)
        ]
        assert f"--output {save['with']['path']}" in " ".join(str(merge["run"]).split())

    def test_each_leg_file_is_uploaded_with_its_artifacts(self, jobs: dict[str, Any]) -> None:
        uploads = [
            s
            for s in jobs["test"]["steps"]
            if str(s.get("uses", "")).startswith("actions/upload-artifact@")
            and str(s["with"]["name"]).startswith("pytest-results-")
        ]
        assert [s["with"]["path"] for s in uploads] == [f"{runner.LEG_DURATIONS_DIR}/"]

    def test_the_leg_files_have_unique_names(self) -> None:
        paths = [runner._leg_durations_path(n) for n in runner.split_names()]
        assert len(set(paths)) == len(runner.split_names())


class TestCacheActionsArePinned:
    def test_every_cache_action_pins_one_sha_with_a_version_comment(self) -> None:
        found = [
            m
            for line in WORKFLOW.read_text(encoding="utf-8").splitlines()
            if (m := _CACHE_USES.match(line))
        ]
        assert len(found) >= 3
        assert {m.group(2) for m in found} == {next(iter(found)).group(2)}
        assert _SHA.match(found[0].group(2))
        assert all(m.group(3) and m.group(3).startswith("# v") for m in found)

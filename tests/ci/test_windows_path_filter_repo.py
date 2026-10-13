"""Pins `windows_path_filter` against the real tree and the real workflow (issue #5380).

The unit tests live in `test_windows_path_filter.py`. These run the reach over
this repository, where under-selection would hide, and read the wiring in
`.github/workflows/pytest.yml`.
"""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

import pytest
import yaml

from scripts.ci import run_pytest_windows as rpw
from scripts.ci import windows_path_filter as wpf

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "pytest.yml"


def _matches(path: str, globs: list[str]) -> bool:
    """Whether any glob matches ``path``. Plain entries are compared as strings,
    because ``full_match`` over every tracked file is slow."""
    if path in globs:
        return True
    return any(PurePosixPath(path).full_match(glob) for glob in globs if "*" in glob)


@pytest.fixture(scope="module")
def patterns() -> dict[str, list[str]]:
    return wpf.filter_patterns(REPO_ROOT)


@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


class TestAgainstTheRepository:
    """Pins the reach against the real tree, where under-selection would hide."""

    def test_every_marked_module_has_a_key(self, patterns: dict[str, list[str]]) -> None:
        assert sorted(patterns) == rpw.marked_files(REPO_ROOT)

    def test_each_module_is_reached_by_its_own_edit(self, patterns: dict[str, list[str]]) -> None:
        for module, globs in patterns.items():
            assert _matches(module, globs), module

    @pytest.mark.parametrize(
        "changed",
        [
            "pyproject.toml",
            "uv.lock",
            ".python-version",
            ".github/workflows/pytest.yml",
            ".github/actions/setup-code-env/action.yml",
            "tests/conftest.py",
            "tests/ci/conftest.py",
            "scripts/ci/run_pytest_windows.py",
            "scripts/ci/windows_path_filter.py",
        ],
    )
    def test_job_wide_inputs_reach_every_module(
        self, patterns: dict[str, list[str]], changed: str
    ) -> None:
        for module, globs in patterns.items():
            assert _matches(changed, globs), f"{changed} does not reach {module}"

    @pytest.mark.parametrize(
        ("changed", "module"),
        [
            (
                "build/scripts/validate_path_normalization.py",
                "tests/test_validate_path_normalization.py",
            ),
            (
                "scripts/eval/optimize-artifact.py",
                "tests/eval/test_optimize_artifact_durability.py",
            ),
            ("scripts/ci/path_policy.py", "tests/workflows/test_pytest_head_guard_windows.py"),
            (
                "scripts/ci/run_pytest_partition.py",
                "tests/workflows/test_pytest_xdist_parallelism.py",
            ),
            ("lefthook.yml", "tests/test_lefthook_integration.py"),
        ],
    )
    def test_production_file_reaches_the_windows_test_that_exercises_it(
        self, patterns: dict[str, list[str]], changed: str, module: str
    ) -> None:
        assert (REPO_ROOT / changed).is_file(), changed
        assert _matches(changed, patterns[module]), f"{changed} does not reach {module}"

    @pytest.mark.parametrize(
        "trigger",
        [
            "lefthook.yml",
            ".config/wt.toml",
            "scripts/bootstrap-vm.sh",
            ".github/actions/setup-code-env/action.yml",
            ".github/actions/ai-review/action.yml",
        ],
    )
    def test_path_policy_triggers_named_for_windows_still_start_the_job(
        self, patterns: dict[str, list[str]], trigger: str
    ) -> None:
        assert any(_matches(trigger, globs) for globs in patterns.values()), trigger

    @pytest.mark.parametrize(
        "changed",
        [
            ".serena/memories/some-note.md",
            ".project-toolkit/sessions/2026-01-01-session-1.json",
            ".project-toolkit/retrospective/2026-01-01-note.md",
            "docs/some-page.md",
        ],
    )
    def test_notes_and_logs_start_no_windows_job(
        self, patterns: dict[str, list[str]], changed: str
    ) -> None:
        for module, globs in patterns.items():
            assert not _matches(changed, globs), f"{changed} reaches {module}"

    def test_the_reach_is_a_minority_of_the_tracked_tree(
        self, patterns: dict[str, list[str]]
    ) -> None:
        """A reach that grows to the whole repository narrows nothing."""
        tracked = wpf.tracked_files(REPO_ROOT)
        reached = {
            path for path in tracked if any(_matches(path, globs) for globs in patterns.values())
        }

        assert len(reached) < len(tracked) * 0.25, (
            f"{len(reached)} of {len(tracked)} tracked files reach a Windows module"
        )


class TestWorkflowWiring:
    def _steps(self, workflow: dict) -> list[dict]:
        return workflow["jobs"]["check-paths"]["steps"]

    def _by_id(self, workflow: dict, step_id: str) -> dict:
        matches = [s for s in self._steps(workflow) if s.get("id") == step_id]
        assert len(matches) == 1, step_id
        return matches[0]

    def test_check_paths_exposes_both_outputs_from_the_select_step(self, workflow: dict) -> None:
        outputs = workflow["jobs"]["check-paths"]["outputs"]

        assert outputs["windows-affected"] == "${{ steps.windows-select.outputs.windows-affected }}"
        assert outputs["windows-files"] == "${{ steps.windows-select.outputs.windows-files }}"

    def test_filter_step_reads_the_document_the_emit_step_writes(self, workflow: dict) -> None:
        emit = next(
            s for s in self._steps(workflow) if "windows_path_filter.py emit" in s.get("run", "")
        )
        document = emit["run"].split("--output", 1)[1].split()[0]
        windows_filter = self._by_id(workflow, "windows-filter")

        assert windows_filter["with"]["filters"] == document

    def test_filter_and_emit_are_skipped_for_events_that_run_everything(
        self, workflow: dict
    ) -> None:
        windows_filter = self._by_id(workflow, "windows-filter")
        emit = next(
            s for s in self._steps(workflow) if "windows_path_filter.py emit" in s.get("run", "")
        )

        for step in (windows_filter, emit):
            assert "workflow_dispatch" in step["if"]
            assert "merge_group" in step["if"]

    def test_filter_action_is_pinned_to_a_commit(self, workflow: dict) -> None:
        uses = self._by_id(workflow, "windows-filter")["uses"]

        assert len(uses.split("@")[1]) == 40

    def test_select_step_always_runs_and_reads_the_filter_outputs(self, workflow: dict) -> None:
        select = self._by_id(workflow, "windows-select")

        assert "if" not in select
        assert select["env"]["FILTER_OUTPUTS"] == "${{ toJson(steps.windows-filter.outputs) }}"
        assert select["run"] == "python3 scripts/ci/windows_path_filter.py select"

    def test_job_starts_only_when_the_change_is_affected(self, workflow: dict) -> None:
        condition = " ".join(workflow["jobs"]["test-windows-pwsh"]["if"].split())

        assert "needs.check-paths.outputs.python-changed == 'true'" in condition
        assert "needs.check-paths.outputs.windows-affected == 'true'" in condition

    def test_run_step_receives_the_selected_modules(self, workflow: dict) -> None:
        step = next(
            s
            for s in workflow["jobs"]["test-windows-pwsh"]["steps"]
            if s.get("name") == "Run Windows path-contract tests"
        )

        assert step["env"][rpw.ENV_SELECTED] == "${{ needs.check-paths.outputs.windows-files }}"

    def test_skipped_job_does_not_trip_the_main_failure_alert(self) -> None:
        from scripts.ci import main_pytest_failure_alert as alert

        needs = json.dumps(
            {"test-windows-pwsh": {"result": "skipped"}, "test": {"result": "success"}}
        )

        assert alert._failed_needs(needs) == []

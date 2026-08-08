"""Workflow target invalidation for changed local contracts."""

from pathlib import Path
from unittest.mock import patch

from scripts.validation.checks_tooling import _workflow_yaml_targets


def _write_workflow(root: Path, name: str, content: str) -> None:
    path = root / ".github" / "workflows" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_changed_action_metadata_invalidates_all_workflows(tmp_path: Path) -> None:
    _write_workflow(tmp_path, "ci.yml", "on: push\n")
    _write_workflow(tmp_path, "release.yaml", "on: push\n")
    action = tmp_path / ".github" / "actions" / "setup" / "action.yml"
    action.parent.mkdir(parents=True)
    action.write_text("name: setup\nruns:\n  using: composite\n  steps: []\n")

    with patch(
        "checks_workflow_targets._changed_paths_since_base",
        return_value=[".github/actions/setup/action.yml"],
    ):
        with patch("checks_workflow_targets._deleted_paths_since_base", return_value=[]):
            assert _workflow_yaml_targets(tmp_path) == [
                ".github/workflows/ci.yml",
                ".github/workflows/release.yaml",
            ]


def test_changed_reusable_workflow_includes_unchanged_callers(tmp_path: Path) -> None:
    _write_workflow(tmp_path, "called.yml", "on:\n  workflow_call:\n")
    _write_workflow(
        tmp_path,
        "caller.yml",
        "jobs:\n  call:\n    uses: ./.github/workflows/called.yml\n",
    )
    _write_workflow(tmp_path, "unrelated.yml", "on: push\n")

    with patch(
        "checks_workflow_targets._changed_paths_since_base",
        return_value=[".github/workflows/called.yml"],
    ):
        with patch("checks_workflow_targets._deleted_paths_since_base", return_value=[]):
            assert _workflow_yaml_targets(tmp_path) == [
                ".github/workflows/called.yml",
                ".github/workflows/caller.yml",
            ]


def test_deleted_action_metadata_invalidates_all_workflows(tmp_path: Path) -> None:
    _write_workflow(tmp_path, "ci.yml", "on: push\n")
    with patch("checks_workflow_targets._changed_paths_since_base", return_value=[]):
        with patch(
            "checks_workflow_targets._deleted_paths_since_base",
            return_value=[".github/actions/setup/action.yml"],
        ):
            assert _workflow_yaml_targets(tmp_path) == [".github/workflows/ci.yml"]


def test_reusable_workflow_rename_includes_old_path_consumers(tmp_path: Path) -> None:
    _write_workflow(tmp_path, "renamed.yml", "on:\n  workflow_call:\n")
    _write_workflow(
        tmp_path,
        "caller.yml",
        "jobs:\n  call:\n    uses: ./.github/workflows/old.yml\n",
    )
    with patch(
        "checks_workflow_targets._changed_paths_since_base",
        return_value=[".github/workflows/renamed.yml"],
    ):
        with patch(
            "checks_workflow_targets._deleted_paths_since_base",
            return_value=[".github/workflows/old.yml"],
        ):
            assert _workflow_yaml_targets(tmp_path) == [
                ".github/workflows/caller.yml",
                ".github/workflows/renamed.yml",
            ]

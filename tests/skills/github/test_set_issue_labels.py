"""Tests for set_issue_labels.py."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from test_helpers import make_completed_process

# Ensure importability
_project_root = Path(__file__).resolve().parents[3]
_lib_dir = _project_root / ".claude" / "lib"
_scripts_dir = _project_root / ".claude" / "skills" / "github" / "scripts"
for _p in (str(_lib_dir), str(_scripts_dir / "issue")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from github_core.api import RepoInfo  # noqa: E402


def _mock_repo():
    return RepoInfo(owner="o", repo="r")


@pytest.fixture
def _import_module():
    import importlib
    mod_name = "set_issue_labels"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


class TestSetIssueLabels:
    """Tests for set_issue_labels.main."""

    def test_apply_existing_labels(self, _import_module, capsys):
        mod = _import_module
        # For each label: _label_exists + _apply_label
        with (
            patch("set_issue_labels.assert_gh_authenticated"),
            patch("set_issue_labels.resolve_repo_params", return_value=_mock_repo()),
            patch("set_issue_labels._get_issue_labels", return_value=[]),
            patch("subprocess.run", side_effect=[
                make_completed_process(),  # _label_exists for "bug"
                make_completed_process(),  # _apply_label for "bug"
                make_completed_process(),  # _label_exists for "P1"
                make_completed_process(),  # _apply_label for "P1"
            ]),
        ):
            rc = mod.main(["--issue", "1", "--labels", "bug", "P1"])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["Success"] is True
        assert result["Data"]["applied"] == ["bug", "P1"]
        assert result["Data"]["total_applied"] == 2

    def test_create_missing_label(self, _import_module, capsys):
        mod = _import_module
        with (
            patch("set_issue_labels.assert_gh_authenticated"),
            patch("set_issue_labels.resolve_repo_params", return_value=_mock_repo()),
            patch("set_issue_labels._get_issue_labels", return_value=[]),
            patch("subprocess.run", side_effect=[
                make_completed_process(returncode=1),   # _label_exists fails
                make_completed_process(),                # _create_label succeeds
                make_completed_process(),                # _apply_label succeeds
            ]),
        ):
            rc = mod.main(["--issue", "1", "--labels", "new-label"])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["Data"]["created"] == ["new-label"]
        assert result["Data"]["applied"] == ["new-label"]

    def test_priority_label(self, _import_module, capsys):
        mod = _import_module
        with (
            patch("set_issue_labels.assert_gh_authenticated"),
            patch("set_issue_labels.resolve_repo_params", return_value=_mock_repo()),
            patch("set_issue_labels._get_issue_labels", return_value=[]),
            patch("subprocess.run", side_effect=[
                make_completed_process(),  # _label_exists
                make_completed_process(),  # _apply_label
            ]),
        ):
            rc = mod.main(["--issue", "1", "--priority", "P1"])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert "priority:P1" in result["Data"]["applied"]

    def test_empty_labels(self, _import_module):
        mod = _import_module
        with (
            patch("set_issue_labels.assert_gh_authenticated"),
            patch("set_issue_labels.resolve_repo_params", return_value=_mock_repo()),
        ):
            rc = mod.main(["--issue", "1"])
        assert rc == 0

    def test_skip_missing_when_no_create(self, _import_module, capsys):
        mod = _import_module
        with (
            patch("set_issue_labels.assert_gh_authenticated"),
            patch("set_issue_labels.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=make_completed_process(returncode=1)),
        ):
            rc = mod.main(["--issue", "1", "--labels", "nonexistent", "--no-create-missing"])
        assert rc == 0

    def test_create_failure_adds_to_failed(self, _import_module):
        mod = _import_module
        with (
            patch("set_issue_labels.assert_gh_authenticated"),
            patch("set_issue_labels.resolve_repo_params", return_value=_mock_repo()),
            patch("set_issue_labels._get_issue_labels", return_value=[]),
            patch("subprocess.run", side_effect=[
                make_completed_process(returncode=1),                     # _label_exists fails
                make_completed_process(returncode=1, stderr="err"),       # _create_label fails
            ]),
        ):
            with pytest.raises(SystemExit) as exc:
                mod.main(["--issue", "1", "--labels", "broken"])
        assert exc.value.code == 3

    def test_whitespace_labels_filtered(self, _import_module, capsys):
        mod = _import_module
        # Only "good" should be processed; "  " and "" are stripped and skipped
        with (
            patch("set_issue_labels.assert_gh_authenticated"),
            patch("set_issue_labels.resolve_repo_params", return_value=_mock_repo()),
            patch("set_issue_labels._get_issue_labels", return_value=[]),
            patch("subprocess.run", side_effect=[
                make_completed_process(),  # _label_exists for "good"
                make_completed_process(),  # _apply_label for "good"
            ]),
        ):
            rc = mod.main(["--issue", "1", "--labels", "good", "  ", ""])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["Data"]["applied"] == ["good"]


class TestComputePriorityRemovals:
    """Pure decision logic: which existing priority labels to remove (#2623)."""

    def test_removes_existing_priority_when_setting_different(self, _import_module):
        mod = _import_module
        removals = mod.compute_priority_removals(
            existing=["bug", "priority:P2", "automation"],
            incoming=["priority:P1"],
        )
        assert removals == ["priority:P2"]

    def test_keeps_existing_priority_when_setting_same(self, _import_module):
        mod = _import_module
        # Re-stamping the same priority must not remove then re-add it.
        removals = mod.compute_priority_removals(
            existing=["priority:P1"],
            incoming=["priority:P1"],
        )
        assert removals == []

    def test_no_removals_when_no_incoming_priority(self, _import_module):
        mod = _import_module
        removals = mod.compute_priority_removals(
            existing=["priority:P2"],
            incoming=["bug", "enhancement"],
        )
        assert removals == []

    def test_removes_all_stale_priorities_when_multiple_present(self, _import_module):
        mod = _import_module
        # Issue already in the contradictory state: two priority labels.
        removals = mod.compute_priority_removals(
            existing=["priority:P1", "priority:P3"],
            incoming=["priority:P2"],
        )
        assert removals == ["priority:P1", "priority:P3"]


class TestPriorityMutualExclusion:
    """End-to-end: setting a priority removes the conflicting one (#2623)."""

    def test_setting_priority_removes_conflicting_label(self, _import_module, capsys):
        mod = _import_module
        with (
            patch("set_issue_labels.assert_gh_authenticated"),
            patch("set_issue_labels.resolve_repo_params", return_value=_mock_repo()),
            patch(
                "set_issue_labels._get_issue_labels",
                return_value=["bug", "priority:P2"],
            ),
            patch("subprocess.run", side_effect=[
                make_completed_process(),  # _remove_label for "priority:P2"
                make_completed_process(),  # _label_exists for "priority:P1"
                make_completed_process(),  # _apply_label for "priority:P1"
            ]),
        ):
            rc = mod.main(["--issue", "1", "--priority", "P1"])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert "priority:P1" in result["Data"]["applied"]
        assert result["Data"]["removed"] == ["priority:P2"]

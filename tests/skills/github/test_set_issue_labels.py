"""Tests for set_issue_labels.py."""

import json
import subprocess
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

from github_core.api import RepoInfo


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
            patch(
                "subprocess.run",
                side_effect=[
                    make_completed_process(),  # _label_exists for "bug"
                    make_completed_process(),  # _apply_label for "bug"
                    make_completed_process(),  # _label_exists for "P1"
                    make_completed_process(),  # _apply_label for "P1"
                ],
            ),
        ):
            rc = mod.main(["--issue", "1", "--labels", "bug", "P1"])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["Success"] is True
        assert result["Data"]["applied"] == ["bug", "P1"]
        assert result["Data"]["total_applied"] == 2

    def test_apply_comma_separated_labels(self, _import_module, capsys):
        mod = _import_module
        # Documented comma form (#4967): one --labels arg, three names applied.
        with (
            patch("set_issue_labels.assert_gh_authenticated"),
            patch("set_issue_labels.resolve_repo_params", return_value=_mock_repo()),
            patch("set_issue_labels._get_issue_labels", return_value=[]),
            patch(
                "subprocess.run",
                side_effect=[
                    make_completed_process(),  # _label_exists "security"
                    make_completed_process(),  # _apply_label "security"
                    make_completed_process(),  # _label_exists "area-workflows"
                    make_completed_process(),  # _apply_label "area-workflows"
                    make_completed_process(),  # _label_exists "technical-debt"
                    make_completed_process(),  # _apply_label "technical-debt"
                ],
            ),
        ):
            rc = mod.main(
                ["--issue", "1", "--labels", "security,area-workflows,technical-debt"]
            )
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["Data"]["applied"] == [
            "security",
            "area-workflows",
            "technical-debt",
        ]
        assert result["Data"]["total_applied"] == 3

    def test_apply_comma_separated_with_priority_label(self, _import_module, capsys):
        mod = _import_module
        # Comma form carrying a priority label (#4967): the priority applies and
        # a stale conflicting priority is reconciled away (#2623).
        with (
            patch("set_issue_labels.assert_gh_authenticated"),
            patch("set_issue_labels.resolve_repo_params", return_value=_mock_repo()),
            patch("set_issue_labels._get_issue_labels", return_value=["priority:P3"]),
            patch(
                "subprocess.run",
                side_effect=[
                    make_completed_process(),  # _label_exists "security"
                    make_completed_process(),  # _apply_label "security"
                    make_completed_process(),  # _label_exists "priority:P2"
                    make_completed_process(),  # _apply_label "priority:P2"
                    make_completed_process(),  # _remove_label "priority:P3"
                ],
            ),
        ):
            rc = mod.main(["--issue", "1", "--labels", "security,priority:P2"])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["Data"]["applied"] == ["security", "priority:P2"]
        assert result["Data"]["removed"] == ["priority:P3"]

    def test_mutating_label_calls_include_timeout(self, _import_module):
        mod = _import_module
        with patch("subprocess.run", return_value=make_completed_process()) as run:
            assert mod._apply_label("o", "r", 1, "bug") is True
            assert mod._remove_label("o", "r", 1, "old") is True
        assert [call.kwargs["timeout"] for call in run.call_args_list] == [
            mod.GH_TIMEOUT_SECONDS,
            mod.GH_TIMEOUT_SECONDS,
        ]

    def test_create_missing_label(self, _import_module, capsys):
        mod = _import_module
        with (
            patch("set_issue_labels.assert_gh_authenticated"),
            patch("set_issue_labels.resolve_repo_params", return_value=_mock_repo()),
            patch("set_issue_labels._get_issue_labels", return_value=[]),
            patch(
                "subprocess.run",
                side_effect=[
                    make_completed_process(returncode=1),  # _label_exists fails
                    make_completed_process(),  # _create_label succeeds
                    make_completed_process(),  # _apply_label succeeds
                ],
            ),
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
            patch(
                "subprocess.run",
                side_effect=[
                    make_completed_process(),  # _label_exists
                    make_completed_process(),  # _apply_label
                ],
            ),
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
            patch(
                "subprocess.run",
                side_effect=[
                    make_completed_process(returncode=1),  # _label_exists fails
                    make_completed_process(returncode=1, stderr="err"),  # _create_label fails
                ],
            ),
        ):
            with pytest.raises(SystemExit) as exc:
                mod.main(["--issue", "1", "--labels", "broken"])
        assert exc.value.code == 3

    def test_gh_timeout_exits_3_with_timeout_error(self, _import_module, capsys):
        mod = _import_module
        with (
            patch("set_issue_labels.assert_gh_authenticated"),
            patch("set_issue_labels.resolve_repo_params", return_value=_mock_repo()),
            patch("set_issue_labels._get_issue_labels", return_value=[]),
            patch(
                "subprocess.run",
                side_effect=subprocess.TimeoutExpired(
                    cmd="gh",
                    timeout=mod.GH_TIMEOUT_SECONDS,
                ),
            ),
        ):
            with pytest.raises(SystemExit) as exc:
                mod.main(["--issue", "1", "--labels", "bug", "--output-format", "json"])

        assert exc.value.code == 3
        result = json.loads(capsys.readouterr().out)
        assert result["Error"]["Code"] == 3
        assert result["Error"]["Type"] == "Timeout"

    def test_whitespace_labels_filtered(self, _import_module, capsys):
        mod = _import_module
        # Only "good" should be processed; "  " and "" are stripped and skipped
        with (
            patch("set_issue_labels.assert_gh_authenticated"),
            patch("set_issue_labels.resolve_repo_params", return_value=_mock_repo()),
            patch("set_issue_labels._get_issue_labels", return_value=[]),
            patch(
                "subprocess.run",
                side_effect=[
                    make_completed_process(),  # _label_exists for "good"
                    make_completed_process(),  # _apply_label for "good"
                ],
            ),
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
            patch(
                "subprocess.run",
                side_effect=[
                    make_completed_process(),  # _label_exists for "priority:P1"
                    make_completed_process(),  # _apply_label for "priority:P1"
                    make_completed_process(),  # _remove_label for "priority:P2"
                ],
            ),
        ):
            rc = mod.main(["--issue", "1", "--priority", "P1"])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert "priority:P1" in result["Data"]["applied"]
        assert result["Data"]["removed"] == ["priority:P2"]

    def test_get_issue_labels_timeout_fails_soft(self, _import_module):
        mod = _import_module
        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="gh", timeout=mod.GH_TIMEOUT_SECONDS),
        ):
            labels = mod._get_issue_labels("o", "r", 1)
        assert labels == []


class TestExpandLabels:
    """Parser-level contract: comma and space label forms agree (#4967)."""

    def _names(self, mod, label_args):
        parser = mod.build_parser()
        args = parser.parse_args(["--issue", "1", *label_args])
        return mod.expand_labels(args.labels or [])

    def test_single_label(self, _import_module):
        assert self._names(_import_module, ["--labels", "bug"]) == ["bug"]

    def test_comma_separated(self, _import_module):
        assert self._names(
            _import_module, ["--labels", "security,area-workflows,priority:P2"]
        ) == ["security", "area-workflows", "priority:P2"]

    def test_space_separated(self, _import_module):
        assert self._names(
            _import_module, ["--labels", "security", "area-workflows", "priority:P2"]
        ) == ["security", "area-workflows", "priority:P2"]

    def test_comma_and_space_agree(self, _import_module):
        comma = self._names(_import_module, ["--labels", "a,b,c"])
        space = self._names(_import_module, ["--labels", "a", "b", "c"])
        assert comma == space == ["a", "b", "c"]

    def test_repeated_flag_accumulates(self, _import_module):
        assert self._names(
            _import_module, ["--labels", "bug", "--labels", "enhancement,priority:P1"]
        ) == ["bug", "enhancement", "priority:P1"]

    def test_label_with_space_preserved(self, _import_module):
        assert self._names(_import_module, ["--labels", "needs discussion"]) == [
            "needs discussion"
        ]

    def test_empty_value_dropped(self, _import_module):
        assert self._names(_import_module, ["--labels", ""]) == []

    def test_whitespace_only_dropped(self, _import_module):
        assert self._names(_import_module, ["--labels", "  ", "good"]) == ["good"]

    def test_no_labels_flag(self, _import_module):
        assert self._names(_import_module, []) == []


class TestLabelHelpTextMatchesBehavior:
    """The --labels help text must describe real parser behavior (#4967).

    A false help string is the same doc/parser contradiction the issue was
    filed for, so the documented spellings are asserted against actual
    expand_labels output. Nothing else validated the help text, which is how
    the earlier false 'bug enhancement equals bug,enhancement' claim shipped.
    """

    def _labels_help(self, mod) -> str:
        parser = mod.build_parser()
        for action in parser._actions:
            if action.dest == "labels":
                return action.help or ""
        raise AssertionError("no --labels action found")

    def _names(self, mod, label_args):
        parser = mod.build_parser()
        args = parser.parse_args(["--issue", "1", *label_args])
        return mod.expand_labels(args.labels or [])

    def test_help_shows_both_multi_label_spellings(self, _import_module):
        help_text = self._labels_help(_import_module)
        assert "--labels bug enhancement" in help_text
        assert '--labels "bug,enhancement"' in help_text

    def test_help_states_quoted_space_is_one_label(self, _import_module):
        help_text = self._labels_help(_import_module)
        assert '--labels "bug enhancement"' in help_text
        assert "one label" in help_text

    def test_documented_unquoted_space_form_yields_two_labels(self, _import_module):
        # --labels bug enhancement  (shell splits into two argv tokens)
        assert self._names(_import_module, ["--labels", "bug", "enhancement"]) == [
            "bug",
            "enhancement",
        ]

    def test_documented_quoted_comma_form_yields_two_labels(self, _import_module):
        # --labels "bug,enhancement"  (one argv token, comma splits it)
        assert self._names(_import_module, ["--labels", "bug,enhancement"]) == [
            "bug",
            "enhancement",
        ]

    def test_documented_quoted_space_form_yields_one_label(self, _import_module):
        # --labels "bug enhancement"  (one argv token, no comma, stays one)
        assert self._names(_import_module, ["--labels", "bug enhancement"]) == [
            "bug enhancement",
        ]

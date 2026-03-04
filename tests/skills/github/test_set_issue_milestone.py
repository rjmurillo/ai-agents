"""Tests for set_issue_milestone.py."""

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


def _extract_json(text: str) -> dict:
    """Extract the last JSON object from multi-line output."""
    idx = text.rfind("{")
    if idx == -1:
        raise ValueError(f"No JSON found in output: {text!r}")
    return json.loads(text[idx:])


@pytest.fixture
def _import_module():
    import importlib
    mod_name = "set_issue_milestone"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


class TestSetIssueMilestone:
    """Tests for set_issue_milestone.main."""

    def test_assign_milestone(self, _import_module, capsys):
        mod = _import_module
        with (
            patch("set_issue_milestone.assert_gh_authenticated"),
            patch("set_issue_milestone.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", side_effect=[
                make_completed_process(stdout="null"),          # _get_current_milestone
                make_completed_process(stdout="v1.0.0"),        # _get_milestone_titles
                make_completed_process(),                        # gh issue edit
            ]),
        ):
            rc = mod.main(["--issue", "1", "--milestone", "v1.0.0"])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["success"] is True
        assert result["action"] == "assigned"
        assert result["milestone"] == "v1.0.0"

    def test_already_has_same_milestone(self, _import_module, capsys):
        mod = _import_module
        with (
            patch("set_issue_milestone.assert_gh_authenticated"),
            patch("set_issue_milestone.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", side_effect=[
                make_completed_process(stdout="v1.0.0"),        # _get_current_milestone
                make_completed_process(stdout="v1.0.0"),        # _get_milestone_titles
            ]),
        ):
            rc = mod.main(["--issue", "1", "--milestone", "v1.0.0"])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["action"] == "no_change"

    def test_force_replace_milestone(self, _import_module, capsys):
        mod = _import_module
        with (
            patch("set_issue_milestone.assert_gh_authenticated"),
            patch("set_issue_milestone.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", side_effect=[
                make_completed_process(stdout="v0.9.0"),        # _get_current_milestone
                make_completed_process(stdout="v1.0.0"),        # _get_milestone_titles
                make_completed_process(),                        # gh issue edit
            ]),
        ):
            rc = mod.main(["--issue", "1", "--milestone", "v1.0.0", "--force"])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["action"] == "replaced"
        assert result["previous_milestone"] == "v0.9.0"

    def test_has_milestone_without_force_exits_5(self, _import_module):
        mod = _import_module
        with (
            patch("set_issue_milestone.assert_gh_authenticated"),
            patch("set_issue_milestone.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", side_effect=[
                make_completed_process(stdout="v0.9.0"),        # _get_current_milestone
                make_completed_process(stdout="v1.0.0"),        # _get_milestone_titles
            ]),
        ):
            with pytest.raises(SystemExit) as exc:
                mod.main(["--issue", "1", "--milestone", "v1.0.0"])
        assert exc.value.code == 5

    def test_milestone_not_found_exits_2(self, _import_module):
        mod = _import_module
        with (
            patch("set_issue_milestone.assert_gh_authenticated"),
            patch("set_issue_milestone.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", side_effect=[
                make_completed_process(stdout="null"),          # _get_current_milestone
                make_completed_process(stdout="v2.0.0"),        # _get_milestone_titles
            ]),
        ):
            with pytest.raises(SystemExit) as exc:
                mod.main(["--issue", "1", "--milestone", "v1.0.0"])
        assert exc.value.code == 2

    def test_clear_milestone(self, _import_module, capsys):
        mod = _import_module
        with (
            patch("set_issue_milestone.assert_gh_authenticated"),
            patch("set_issue_milestone.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", side_effect=[
                make_completed_process(stdout="v1.0.0"),        # _get_current_milestone
                make_completed_process(),                        # PATCH to clear
            ]),
        ):
            rc = mod.main(["--issue", "1", "--clear"])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["action"] == "cleared"

    def test_clear_no_milestone(self, _import_module, capsys):
        mod = _import_module
        with (
            patch("set_issue_milestone.assert_gh_authenticated"),
            patch("set_issue_milestone.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=make_completed_process(stdout="null")),
        ):
            rc = mod.main(["--issue", "1", "--clear"])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["action"] == "no_change"

"""Tests for add_comment_reaction.py."""

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
for _p in (str(_lib_dir), str(_scripts_dir / "reactions")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from github_core.api import RepoInfo  # noqa: E402


def _mock_repo():
    return RepoInfo(owner="o", repo="r")


@pytest.fixture
def _import_module():
    import importlib
    mod_name = "add_comment_reaction"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


class TestAddCommentReaction:
    """Tests for add_comment_reaction.main."""

    def test_single_success(self, _import_module, capsys):
        mod = _import_module
        with (
            patch("add_comment_reaction.assert_gh_authenticated"),
            patch("add_comment_reaction.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=make_completed_process(
                stdout=json.dumps({"id": 1})
            )),
        ):
            rc = mod.main(["--comment-id", "123", "--reaction", "eyes"])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["succeeded"] == 1
        assert result["failed"] == 0
        assert result["results"][0]["success"] is True

    def test_batch_success(self, _import_module, capsys):
        mod = _import_module
        with (
            patch("add_comment_reaction.assert_gh_authenticated"),
            patch("add_comment_reaction.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=make_completed_process()),
        ):
            rc = mod.main(["--comment-id", "1", "2", "3", "--reaction", "heart"])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["total_count"] == 3
        assert result["succeeded"] == 3
        assert result["failed"] == 0

    def test_partial_failure(self, _import_module, capsys):
        mod = _import_module
        call_count = [0]

        def side_effect(cmd, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:
                return make_completed_process(returncode=1, stderr="error")
            return make_completed_process()

        with (
            patch("add_comment_reaction.assert_gh_authenticated"),
            patch("add_comment_reaction.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", side_effect=side_effect),
        ):
            rc = mod.main(["--comment-id", "1", "2", "3", "--comment-type", "issue", "--reaction", "rocket"])
        assert rc == 3
        result = json.loads(capsys.readouterr().out)
        assert result["succeeded"] == 2
        assert result["failed"] == 1

    def test_duplicate_reaction_succeeds(self, _import_module, capsys):
        mod = _import_module
        with (
            patch("add_comment_reaction.assert_gh_authenticated"),
            patch("add_comment_reaction.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=make_completed_process(
                returncode=1, stdout="already reacted"
            )),
        ):
            rc = mod.main(["--comment-id", "1", "--reaction", "+1"])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["succeeded"] == 1

    def test_review_endpoint(self, _import_module):
        mod = _import_module
        captured = []

        def fake_run(cmd, **kwargs):
            captured.append(cmd)
            return make_completed_process()

        with (
            patch("add_comment_reaction.assert_gh_authenticated"),
            patch("add_comment_reaction.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", side_effect=fake_run),
        ):
            mod.main(["--comment-id", "99", "--reaction", "eyes"])
        api_calls = [c for c in captured if "pulls/comments" in str(c)]
        assert len(api_calls) >= 1

    def test_issue_endpoint(self, _import_module):
        mod = _import_module
        captured = []

        def fake_run(cmd, **kwargs):
            captured.append(cmd)
            return make_completed_process()

        with (
            patch("add_comment_reaction.assert_gh_authenticated"),
            patch("add_comment_reaction.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", side_effect=fake_run),
        ):
            mod.main(["--comment-id", "99", "--comment-type", "issue", "--reaction", "eyes"])
        api_calls = [c for c in captured if "issues/comments" in str(c)]
        assert len(api_calls) >= 1

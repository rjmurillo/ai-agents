"""Utility-level tests for add_comment_reaction.py."""

import importlib
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from test_helpers import make_completed_process as make_proc

_project_root = Path(__file__).resolve().parents[3]
_lib_dir = _project_root / ".claude" / "lib"
_reactions_dir = (
    _project_root / ".claude" / "skills" / "github" / "scripts" / "reactions"
)
for _path in (str(_lib_dir), str(_reactions_dir)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from github_core.api import RepoInfo


def _mock_repo() -> RepoInfo:
    return RepoInfo(owner="o", repo="r")


class TestAddCommentReaction:
    """Tests for add_comment_reaction.main."""

    def _import(self):
        import add_comment_reaction as mod

        importlib.reload(mod)
        return mod

    def test_happy_path_single_review_comment(self, capsys):
        mod = self._import()
        proc = make_proc(returncode=0, stdout='{"id":1}')
        with (
            patch("add_comment_reaction.assert_gh_authenticated"),
            patch(
                "add_comment_reaction.resolve_repo_params",
                return_value=_mock_repo(),
            ),
            patch(
                "add_comment_reaction.query_review_comment_thread_state",
                return_value={
                    "pull_request": 1,
                    "thread_id": "PRRT_abc",
                    "is_resolved": False,
                },
            ),
            patch("subprocess.run", return_value=proc),
        ):
            rc = mod.main(["--comment-id", "42", "--reaction", "eyes"])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["Data"]["succeeded"] == 1
        assert result["Data"]["failed"] == 0
        assert result["Data"]["results"][0]["success"] is True
        assert result["Data"]["results"][0]["comment_id"] == 42

    def test_happy_path_issue_comment(self, capsys):
        mod = self._import()
        proc = make_proc(returncode=0)
        with (
            patch("add_comment_reaction.assert_gh_authenticated"),
            patch(
                "add_comment_reaction.resolve_repo_params",
                return_value=_mock_repo(),
            ),
            patch("subprocess.run", return_value=proc),
        ):
            rc = mod.main([
                "--comment-id", "10",
                "--comment-type", "issue",
                "--reaction", "+1",
            ])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["Data"]["comment_type"] == "issue"

    def test_batch_all_succeed(self, capsys):
        mod = self._import()
        proc = make_proc(returncode=0)
        with (
            patch("add_comment_reaction.assert_gh_authenticated"),
            patch(
                "add_comment_reaction.resolve_repo_params",
                return_value=_mock_repo(),
            ),
            patch("subprocess.run", return_value=proc),
        ):
            rc = mod.main([
                "--comment-id", "1", "2", "3",
                "--comment-type", "issue",
                "--reaction", "heart",
            ])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["Data"]["total_count"] == 3
        assert result["Data"]["succeeded"] == 3
        assert result["Data"]["failed"] == 0

    def test_already_reacted_counts_as_success(self, capsys):
        mod = self._import()
        proc = make_proc(returncode=1, stdout="already reacted")
        with (
            patch("add_comment_reaction.assert_gh_authenticated"),
            patch(
                "add_comment_reaction.resolve_repo_params",
                return_value=_mock_repo(),
            ),
            patch("subprocess.run", return_value=proc),
        ):
            rc = mod.main([
                "--comment-id", "5",
                "--comment-type", "issue",
                "--reaction", "rocket",
            ])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["Data"]["succeeded"] == 1

    def test_api_failure_counted(self, capsys):
        mod = self._import()
        proc = make_proc(returncode=1, stderr="server error")
        with (
            patch("add_comment_reaction.assert_gh_authenticated"),
            patch(
                "add_comment_reaction.resolve_repo_params",
                return_value=_mock_repo(),
            ),
            patch("subprocess.run", return_value=proc),
        ):
            rc = mod.main([
                "--comment-id", "9",
                "--comment-type", "issue",
                "--reaction", "eyes",
            ])
        assert rc == 3
        result = json.loads(capsys.readouterr().out)
        assert result["Data"]["failed"] == 1
        assert result["Data"]["results"][0]["success"] is False

    def test_partial_batch_failure(self, capsys):
        mod = self._import()
        procs = [
            make_proc(returncode=0),
            make_proc(returncode=1, stderr="err"),
        ]
        with (
            patch("add_comment_reaction.assert_gh_authenticated"),
            patch(
                "add_comment_reaction.resolve_repo_params",
                return_value=_mock_repo(),
            ),
            patch("subprocess.run", side_effect=procs),
        ):
            rc = mod.main([
                "--comment-id", "1", "2",
                "--comment-type", "issue",
                "--reaction", "eyes",
            ])
        assert rc == 3
        result = json.loads(capsys.readouterr().out)
        assert result["Data"]["succeeded"] == 1
        assert result["Data"]["failed"] == 1

    def test_main_exits_3_on_failure(self):
        mod = self._import()
        proc = make_proc(returncode=1, stderr="error")
        with (
            patch("add_comment_reaction.assert_gh_authenticated"),
            patch(
                "add_comment_reaction.resolve_repo_params",
                return_value=_mock_repo(),
            ),
            patch("subprocess.run", return_value=proc),
        ):
            rc = mod.main([
                "--comment-id", "1",
                "--comment-type", "issue",
                "--reaction", "eyes",
            ])
        assert rc == 3

    def test_main_success(self, capsys):
        mod = self._import()
        proc = make_proc(returncode=0)
        with (
            patch("add_comment_reaction.assert_gh_authenticated"),
            patch(
                "add_comment_reaction.resolve_repo_params",
                return_value=_mock_repo(),
            ),
            patch("subprocess.run", return_value=proc),
        ):
            rc = mod.main([
                "--comment-id", "5",
                "--comment-type", "issue",
                "--reaction", "+1",
            ])
        assert rc == 0
        parsed = json.loads(capsys.readouterr().out)
        assert parsed["Data"]["succeeded"] == 1

    def test_help_does_not_crash(self):
        import add_comment_reaction as mod

        with pytest.raises(SystemExit) as exc:
            mod.main(["--help"])
        assert exc.value.code == 0

    def test_review_endpoint_used_for_review_type(self):
        mod = self._import()
        captured_commands = []

        def fake_run(command, **_kwargs):
            captured_commands.append(command)
            return make_proc(returncode=0)

        with (
            patch("add_comment_reaction.assert_gh_authenticated"),
            patch(
                "add_comment_reaction.resolve_repo_params",
                return_value=RepoInfo(owner="owner", repo="repo"),
            ),
            patch(
                "add_comment_reaction.query_review_comment_thread_state",
                return_value={
                    "pull_request": 1,
                    "thread_id": "PRRT_abc",
                    "is_resolved": False,
                },
            ),
            patch("subprocess.run", side_effect=fake_run),
        ):
            mod.main(["--comment-id", "100", "--reaction", "eyes"])

        api_commands = [
            command
            for command in captured_commands
            if "pulls/comments/100/reactions" in str(command)
        ]
        assert len(api_commands) == 1
        assert "-X" in api_commands[0]
        assert "POST" in api_commands[0]

    def test_issue_endpoint_used_for_issue_type(self):
        mod = self._import()
        captured_commands = []

        def fake_run(command, **_kwargs):
            captured_commands.append(command)
            return make_proc(returncode=0)

        with (
            patch("add_comment_reaction.assert_gh_authenticated"),
            patch(
                "add_comment_reaction.resolve_repo_params",
                return_value=RepoInfo(owner="owner", repo="repo"),
            ),
            patch("subprocess.run", side_effect=fake_run),
        ):
            mod.main([
                "--comment-id", "200",
                "--comment-type", "issue",
                "--reaction", "eyes",
            ])

        api_commands = [
            command
            for command in captured_commands
            if "issues/comments" in str(command)
        ]
        assert len(api_commands) == 1

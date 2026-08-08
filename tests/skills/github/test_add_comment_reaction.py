"""Tests for add_comment_reaction.py."""

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
for _p in (str(_lib_dir), str(_scripts_dir / "reactions")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from github_core.api import RepoInfo


def _mock_repo():
    return RepoInfo(owner="o", repo="r")


_UNRESOLVED_STATE = {
    "pull_request": 42,
    "thread_id": "PRRT_abc",
    "is_resolved": False,
}


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
            patch(
                "add_comment_reaction.query_review_comment_thread_state",
                return_value=_UNRESOLVED_STATE,
            ),
            patch("subprocess.run", return_value=make_completed_process(
                stdout=json.dumps({"id": 1})
            )) as run,
        ):
            rc = mod.main(["--comment-id", "123", "--reaction", "eyes"])
        assert rc == 0
        assert run.call_args.kwargs["timeout"] == mod.GH_TIMEOUT_SECONDS
        result = json.loads(capsys.readouterr().out)
        assert result["Data"]["succeeded"] == 1
        assert result["Data"]["failed"] == 0
        assert result["Data"]["results"][0]["success"] is True

    def test_batch_success(self, _import_module, capsys):
        mod = _import_module
        with (
            patch("add_comment_reaction.assert_gh_authenticated"),
            patch("add_comment_reaction.resolve_repo_params", return_value=_mock_repo()),
            patch(
                "add_comment_reaction.query_review_comment_thread_state",
                return_value=_UNRESOLVED_STATE,
            ),
            patch("subprocess.run", return_value=make_completed_process()),
        ):
            rc = mod.main(["--comment-id", "1", "2", "3", "--reaction", "heart"])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["Data"]["total_count"] == 3
        assert result["Data"]["succeeded"] == 3
        assert result["Data"]["failed"] == 0

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
            rc = mod.main([
                "--comment-id", "1", "2", "3",
                "--comment-type", "issue", "--reaction", "rocket",
            ])
        assert rc == 3
        result = json.loads(capsys.readouterr().out)
        assert result["Success"] is False
        assert result["Error"]["Code"] == 3
        assert result["Data"]["succeeded"] == 2
        assert result["Data"]["failed"] == 1

    def test_timeout_exits_3_with_timeout_error(self, _import_module, capsys):
        mod = _import_module
        with (
            patch("add_comment_reaction.assert_gh_authenticated"),
            patch("add_comment_reaction.resolve_repo_params", return_value=_mock_repo()),
            patch(
                "add_comment_reaction.query_review_comment_thread_state",
                return_value=_UNRESOLVED_STATE,
            ),
            patch(
                "subprocess.run",
                side_effect=subprocess.TimeoutExpired(
                    cmd="gh",
                    timeout=mod.GH_TIMEOUT_SECONDS,
                ),
            ),
        ):
            rc = mod.main(["--comment-id", "1", "--reaction", "eyes", "--output-format", "json"])

        assert rc == 3
        result = json.loads(capsys.readouterr().out)
        assert result["Error"]["Code"] == 3
        assert result["Error"]["Type"] == "Timeout"

    def test_mixed_timeout_and_api_failure_reports_api_error(self, _import_module, capsys):
        mod = _import_module
        with (
            patch("add_comment_reaction.assert_gh_authenticated"),
            patch("add_comment_reaction.resolve_repo_params", return_value=_mock_repo()),
            patch(
                "add_comment_reaction.query_review_comment_thread_state",
                return_value=_UNRESOLVED_STATE,
            ),
            patch(
                "subprocess.run",
                side_effect=[
                    subprocess.TimeoutExpired(
                        cmd="gh",
                        timeout=mod.GH_TIMEOUT_SECONDS,
                    ),
                    make_completed_process(returncode=1, stderr="server error"),
                ],
            ),
        ):
            rc = mod.main([
                "--comment-id", "1", "2",
                "--reaction", "eyes",
                "--output-format", "json",
            ])

        assert rc == 3
        result = json.loads(capsys.readouterr().out)
        assert result["Error"]["Code"] == 3
        assert result["Error"]["Type"] == "ApiError"

    def test_duplicate_reaction_succeeds(self, _import_module, capsys):
        mod = _import_module
        with (
            patch("add_comment_reaction.assert_gh_authenticated"),
            patch("add_comment_reaction.resolve_repo_params", return_value=_mock_repo()),
            patch(
                "add_comment_reaction.query_review_comment_thread_state",
                return_value=_UNRESOLVED_STATE,
            ),
            patch("subprocess.run", return_value=make_completed_process(
                returncode=1, stdout="already reacted"
            )),
        ):
            rc = mod.main(["--comment-id", "1", "--reaction", "+1"])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["Data"]["succeeded"] == 1

    def test_review_endpoint(self, _import_module):
        mod = _import_module
        captured = []

        def fake_run(cmd, **kwargs):
            captured.append(cmd)
            return make_completed_process()

        with (
            patch("add_comment_reaction.assert_gh_authenticated"),
            patch("add_comment_reaction.resolve_repo_params", return_value=_mock_repo()),
            patch(
                "add_comment_reaction.query_review_comment_thread_state",
                return_value=_UNRESOLVED_STATE,
            ),
            patch("subprocess.run", side_effect=fake_run),
        ):
            mod.main(["--comment-id", "99", "--reaction", "eyes"])
        api_calls = [c for c in captured if "pulls/comments" in str(c)]
        assert len(api_calls) >= 1

    def test_resolved_review_thread_skips_reaction(self, _import_module, capsys):
        mod = _import_module
        live_state = {
            "pull_request": 42,
            "thread_id": "PRRT_abc",
            "is_resolved": True,
        }
        with (
            patch("add_comment_reaction.assert_gh_authenticated"),
            patch("add_comment_reaction.resolve_repo_params", return_value=_mock_repo()),
            patch(
                "add_comment_reaction.query_review_comment_thread_state",
                return_value=live_state,
            ),
            patch("subprocess.run") as run,
        ):
            rc = mod.main([
                "--comment-id",
                "99",
                "--pull-request",
                "42",
                "--reaction",
                "eyes",
            ])
        assert rc == 0
        run.assert_not_called()
        result = json.loads(capsys.readouterr().out)
        assert result["Data"]["action"] == "SKIP"
        assert result["Data"]["results"][0]["reason"] == "thread_resolved"

    def test_wrong_pr_skips_reaction(self, _import_module, capsys):
        mod = _import_module
        with (
            patch("add_comment_reaction.assert_gh_authenticated"),
            patch("add_comment_reaction.resolve_repo_params", return_value=_mock_repo()),
            patch(
                "add_comment_reaction.query_review_comment_thread_state",
                return_value=_UNRESOLVED_STATE,
            ),
            patch("subprocess.run") as run,
        ):
            rc = mod.main([
                "--comment-id",
                "99",
                "--pull-request",
                "7",
                "--reaction",
                "eyes",
            ])
        assert rc == 0
        run.assert_not_called()
        result = json.loads(capsys.readouterr().out)
        assert result["Data"]["results"][0]["reason"] == "wrong_pull_request"

    def test_missing_review_comment_skips_reaction(self, _import_module, capsys):
        mod = _import_module
        with (
            patch("add_comment_reaction.assert_gh_authenticated"),
            patch("add_comment_reaction.resolve_repo_params", return_value=_mock_repo()),
            patch(
                "add_comment_reaction.query_review_comment_thread_state",
                return_value=None,
            ),
            patch("subprocess.run") as run,
        ):
            rc = mod.main([
                "--comment-id",
                "99",
                "--pull-request",
                "42",
                "--reaction",
                "eyes",
            ])
        assert rc == 0
        run.assert_not_called()
        result = json.loads(capsys.readouterr().out)
        assert result["Data"]["results"][0]["reason"] == "comment_not_found"

    def test_state_query_failure_exits_3_without_reaction(
        self,
        _import_module,
        capsys,
    ):
        mod = _import_module
        with (
            patch("add_comment_reaction.assert_gh_authenticated"),
            patch("add_comment_reaction.resolve_repo_params", return_value=_mock_repo()),
            patch(
                "add_comment_reaction.query_review_comment_thread_state",
                side_effect=RuntimeError("API unavailable"),
            ),
            patch("subprocess.run") as run,
        ):
            rc = mod.main([
                "--comment-id",
                "99",
                "--pull-request",
                "42",
                "--reaction",
                "eyes",
            ])
        assert rc == 3
        run.assert_not_called()
        result = json.loads(capsys.readouterr().out)
        assert result["Data"]["results"][0]["reason"] == "thread_state_query_failed"

    def test_external_resolution_after_triage_skips_reaction(
        self,
        _import_module,
        capsys,
    ):
        mod = _import_module
        cached_triage_state = {"is_resolved": False}
        live_state = {
            "pull_request": 42,
            "thread_id": "PRRT_abc",
            "is_resolved": True,
        }
        with (
            patch("add_comment_reaction.assert_gh_authenticated"),
            patch("add_comment_reaction.resolve_repo_params", return_value=_mock_repo()),
            patch(
                "add_comment_reaction.query_review_comment_thread_state",
                return_value=live_state,
            ) as query_state,
            patch("subprocess.run") as run,
        ):
            assert cached_triage_state["is_resolved"] is False
            rc = mod.main([
                "--comment-id",
                "99",
                "--pull-request",
                "42",
                "--reaction",
                "eyes",
            ])
        assert rc == 0
        query_state.assert_called_once_with("o", "r", 99, 42)
        run.assert_not_called()
        result = json.loads(capsys.readouterr().out)
        assert result["Data"]["results"][0]["reason"] == "thread_resolved"

    def test_query_state_maps_reply_to_root_thread(self, _import_module):
        mod = _import_module
        comment = {
            "pull_request_url": "https://api.github.com/repos/o/r/pulls/42",
            "in_reply_to_id": 100,
        }
        thread = {"id": "PRRT_abc", "isResolved": False}
        with (
            patch(
                "add_comment_reaction._query_review_comment",
                return_value=comment,
            ),
            patch(
                "add_comment_reaction._find_review_thread",
                return_value=thread,
            ) as find_thread,
        ):
            state = mod.query_review_comment_thread_state("o", "r", 101)
        find_thread.assert_called_once_with("o", "r", 42, 100)
        assert state == {
            "pull_request": 42,
            "thread_id": "PRRT_abc",
            "is_resolved": False,
        }

    def test_query_state_rejects_wrong_pr_before_thread_query(self, _import_module):
        mod = _import_module
        comment = {
            "pull_request_url": "https://api.github.com/repos/o/r/pulls/42",
            "in_reply_to_id": None,
        }
        with (
            patch(
                "add_comment_reaction._query_review_comment",
                return_value=comment,
            ),
            patch(
                "add_comment_reaction._find_review_thread",
            ) as find_thread,
        ):
            state = mod.query_review_comment_thread_state(
                "o",
                "r",
                101,
                expected_pull_request=7,
            )
        find_thread.assert_not_called()
        assert state == {
            "pull_request": 42,
            "thread_id": None,
            "is_resolved": None,
        }

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

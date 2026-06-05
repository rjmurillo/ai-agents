"""Tests for close_issue.py skill script (issue #2380)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.github_core.api import RepoInfo

# ---------------------------------------------------------------------------
# Import the script via importlib (not a package)
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1]
    / ".claude" / "skills" / "github" / "scripts" / "issue"
)


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("close_issue")
main = _mod.main
build_parser = _mod.build_parser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


def _state_open():
    return _completed(stdout=json.dumps({"state": "OPEN"}), rc=0)


def _state_closed():
    return _completed(stdout=json.dumps({"state": "CLOSED"}), rc=0)


def _envelope(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


# ---------------------------------------------------------------------------
# build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_issue_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([])

    def test_default_reason_is_completed(self):
        args = build_parser().parse_args(["--issue", "5"])
        assert args.reason == "completed"

    def test_reason_not_planned_accepted(self):
        args = build_parser().parse_args(["--issue", "5", "--reason", "not planned"])
        assert args.reason == "not planned"

    def test_invalid_reason_rejected(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--issue", "5", "--reason", "wontfix"])

    def test_comment_and_comment_file_mutually_exclusive(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(
                ["--issue", "5", "--comment", "x", "--comment-file", "f.txt"]
            )


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


class TestMain:
    def test_not_authenticated_exits_4(self):
        with patch(
            "close_issue.assert_gh_authenticated",
            side_effect=SystemExit(4),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--issue", "1"])
            assert exc.value.code == 4

    def test_close_success_no_comment(self, capsys):
        with patch(
            "close_issue.assert_gh_authenticated",
        ), patch(
            "close_issue.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            side_effect=[_state_open(), _completed(stdout="closed", rc=0)],
        ) as mock_run:
            rc = main(["--issue", "50"])
        assert rc == 0

        env = _envelope(capsys)
        assert env["Success"] is True
        assert env["Error"] is None
        assert env["Metadata"]["Script"] == "close_issue.py"
        data = env["Data"]
        assert data["issue"] == 50
        assert data["state"] == "closed"
        assert data["reason"] == "completed"
        assert data["commented"] is False

        # State check and close call ran (no comment POST).
        assert mock_run.call_count == 2
        close_args = mock_run.call_args_list[1].args[0]
        assert close_args[:3] == ["gh", "issue", "close"]
        assert "--reason" in close_args
        assert close_args[close_args.index("--reason") + 1] == "completed"

    def test_close_with_reason_not_planned(self, capsys):
        with patch(
            "close_issue.assert_gh_authenticated",
        ), patch(
            "close_issue.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            side_effect=[_state_open(), _completed(rc=0)],
        ) as mock_run:
            rc = main(["--issue", "7", "--reason", "not planned"])
        assert rc == 0
        data = _envelope(capsys)["Data"]
        assert data["reason"] == "not planned"
        close_args = mock_run.call_args_list[1].args[0]
        assert close_args[close_args.index("--reason") + 1] == "not planned"

    def test_close_with_comment_posts_then_closes(self, capsys):
        with patch(
            "close_issue.assert_gh_authenticated",
        ), patch(
            "close_issue.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            side_effect=[
                _state_open(),
                _completed(stdout="{}", rc=0),
                _completed(stdout="closed", rc=0),
            ],
        ) as mock_run:
            rc = main(["--issue", "9", "--comment", "Fixed in PR #10"])
        assert rc == 0
        data = _envelope(capsys)["Data"]
        assert data["commented"] is True

        # First call posts the comment, second closes.
        assert mock_run.call_count == 3
        post_args = mock_run.call_args_list[1].args[0]
        assert post_args[:2] == ["gh", "api"]
        assert "comments" in post_args[2]
        # The comment body is passed as JSON on stdin.
        post_input = mock_run.call_args_list[1].kwargs["input"]
        assert json.loads(post_input)["body"] == "Fixed in PR #10"
        close_args = mock_run.call_args_list[2].args[0]
        assert close_args[:3] == ["gh", "issue", "close"]

    def test_comment_from_file(self, tmp_path, capsys, monkeypatch):
        comment_path = tmp_path / "body.md"
        comment_path.write_text("Closing per triage.", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        with patch(
            "close_issue.assert_gh_authenticated",
        ), patch(
            "close_issue.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            side_effect=[
                _state_open(),
                _completed(stdout="{}", rc=0),
                _completed(stdout="closed", rc=0),
            ],
        ) as mock_run:
            rc = main(["--issue", "11", "--comment-file", comment_path.name])
        assert rc == 0
        assert _envelope(capsys)["Data"]["commented"] is True
        post_input = mock_run.call_args_list[1].kwargs["input"]
        assert json.loads(post_input)["body"] == "Closing per triage."

    def test_missing_comment_file_exits_2(self, capsys):
        with patch(
            "close_issue.assert_gh_authenticated",
        ), patch(
            "close_issue.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_state_open(),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--issue", "12", "--comment-file", "missing.md"])
            assert exc.value.code == 2
        env = _envelope(capsys)
        assert env["Success"] is False
        assert env["Error"]["Code"] == 2

    def test_comment_file_path_traversal_exits_2(self, tmp_path, capsys, monkeypatch):
        work = tmp_path / "work"
        work.mkdir()
        outside = tmp_path / "outside.md"
        outside.write_text("secret", encoding="utf-8")
        monkeypatch.chdir(work)
        with patch(
            "close_issue.assert_gh_authenticated",
        ), patch(
            "close_issue.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_state_open(),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--issue", "12", "--comment-file", "../outside.md"])
            assert exc.value.code == 2
        env = _envelope(capsys)
        assert env["Success"] is False
        assert env["Error"]["Type"] == "InvalidParams"

    def test_close_api_failure_exits_3(self, capsys):
        with patch(
            "close_issue.assert_gh_authenticated",
        ), patch(
            "close_issue.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            side_effect=[_state_open(), _completed(stderr="HTTP 404", rc=1)],
        ):
            rc = main(["--issue", "13"])
        assert rc == 3
        env = _envelope(capsys)
        assert env["Success"] is False
        assert env["Error"]["Code"] == 3
        assert env["Error"]["Type"] == "ApiError"

    def test_comment_post_failure_exits_3_before_close(self, capsys):
        """A failed comment POST aborts with code 3; the issue is not closed."""
        with patch(
            "close_issue.assert_gh_authenticated",
        ), patch(
            "close_issue.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            side_effect=[_state_open(), _completed(stderr="HTTP 403", rc=1)],
        ) as mock_run:
            with pytest.raises(SystemExit) as exc:
                main(["--issue", "14", "--comment", "note"])
            assert exc.value.code == 3
        # State check and comment POST ran; the close call was never reached.
        assert mock_run.call_count == 2
        env = _envelope(capsys)
        assert env["Success"] is False
        assert env["Error"]["Code"] == 3

    def test_whitespace_only_comment_is_not_posted(self, capsys):
        with patch(
            "close_issue.assert_gh_authenticated",
        ), patch(
            "close_issue.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            side_effect=[_state_open(), _completed(rc=0)],
        ) as mock_run:
            rc = main(["--issue", "15", "--comment", "   "])
        assert rc == 0
        # No comment POST; only state check and close call.
        assert mock_run.call_count == 2
        assert _envelope(capsys)["Data"]["commented"] is False

    def test_already_closed_skips_comment_and_close(self, capsys):
        with patch(
            "close_issue.assert_gh_authenticated",
        ), patch(
            "close_issue.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_state_closed(),
        ) as mock_run:
            rc = main(["--issue", "16", "--comment", "do not duplicate"])
        assert rc == 0
        data = _envelope(capsys)["Data"]
        assert data["state"] == "closed"
        assert data["action"] == "already_closed"
        assert data["commented"] is False
        assert mock_run.call_count == 1

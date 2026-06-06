"""Tests for reopen_issue.py skill script (issue #2475)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.github_core.api import RepoInfo

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


_mod = _import_script("reopen_issue")
main = _mod.main
build_parser = _mod.build_parser


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


def _state_open():
    return _completed(stdout=json.dumps({"state": "OPEN"}), rc=0)


def _state_closed():
    return _completed(stdout=json.dumps({"state": "CLOSED"}), rc=0)


def _paginated_comments(*pages: list[str]):
    return _completed(
        stdout=json.dumps([[{"body": body} for body in page] for page in pages]),
        rc=0,
    )


def _envelope(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


class TestBuildParser:
    def test_issue_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([])

    def test_comment_and_comment_file_mutually_exclusive(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(
                ["--issue", "5", "--comment", "x", "--comment-file", "f.txt"]
            )


class TestMain:
    def test_not_authenticated_exits_4(self):
        with patch("reopen_issue.assert_gh_authenticated", side_effect=SystemExit(4)):
            with pytest.raises(SystemExit) as exc:
                main(["--issue", "1"])
            assert exc.value.code == 4

    def test_reopen_success_no_comment(self, capsys):
        with patch("reopen_issue.assert_gh_authenticated"), patch(
            "reopen_issue.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            side_effect=[_state_closed(), _completed(stdout="reopened", rc=0)],
        ) as mock_run:
            rc = main(["--issue", "50"])
        assert rc == 0
        env = _envelope(capsys)
        assert env["Success"] is True
        assert env["Error"] is None
        assert env["Metadata"]["Script"] == "reopen_issue.py"
        data = env["Data"]
        assert data["issue"] == 50
        assert data["state"] == "open"
        assert data["action"] == "reopened"
        assert data["commented"] is False
        assert mock_run.call_count == 2
        reopen_args = mock_run.call_args_list[1].args[0]
        assert reopen_args[:3] == ["gh", "issue", "reopen"]

    def test_already_open_is_noop(self, capsys):
        with patch("reopen_issue.assert_gh_authenticated"), patch(
            "reopen_issue.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch("subprocess.run", side_effect=[_state_open()]) as mock_run:
            rc = main(["--issue", "7"])
        assert rc == 0
        data = _envelope(capsys)["Data"]
        assert data["action"] == "already_open"
        assert data["state"] == "open"
        # Only the state check ran; no reopen call.
        assert mock_run.call_count == 1

    def test_reopen_with_comment_reopens_then_comments(self, capsys):
        with patch("reopen_issue.assert_gh_authenticated"), patch(
            "reopen_issue.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            side_effect=[
                _state_closed(),
                _completed(stdout="reopened", rc=0),
                _completed(stdout="{}", rc=0),
            ],
        ) as mock_run:
            rc = main(["--issue", "9", "--comment", "Reopened: maintainer kept open"])
        assert rc == 0
        data = _envelope(capsys)["Data"]
        assert data["commented"] is True
        assert mock_run.call_count == 3

    def test_already_open_posts_missing_comment(self, capsys):
        with patch("reopen_issue.assert_gh_authenticated"), patch(
            "reopen_issue.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            side_effect=[
                _state_open(),
                _paginated_comments(["unrelated"]),
                _completed(stdout="{}", rc=0),
            ],
        ) as mock_run:
            rc = main(["--issue", "9", "--comment", "new note"])
        assert rc == 0
        data = _envelope(capsys)["Data"]
        assert data["action"] == "already_open"
        assert data["commented"] is True
        assert mock_run.call_count == 3

    def test_already_open_skips_duplicate_comment(self, capsys):
        with patch("reopen_issue.assert_gh_authenticated"), patch(
            "reopen_issue.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            side_effect=[_state_open(), _paginated_comments(["dup"])],
        ) as mock_run:
            rc = main(["--issue", "9", "--comment", "dup"])
        assert rc == 0
        data = _envelope(capsys)["Data"]
        assert data["commented"] is False
        assert data["commentAlreadyPresent"] is True
        # State check + comment list, no POST.
        assert mock_run.call_count == 2

    def test_reopen_api_failure_returns_3(self, capsys):
        with patch("reopen_issue.assert_gh_authenticated"), patch(
            "reopen_issue.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            side_effect=[_state_closed(), _completed(stderr="server error", rc=1)],
        ):
            rc = main(["--issue", "9"])
        assert rc == 3
        env = _envelope(capsys)
        assert env["Success"] is False

    def test_not_found_returns_2(self, capsys):
        with patch("reopen_issue.assert_gh_authenticated"), patch(
            "reopen_issue.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            side_effect=[_completed(stderr="Could not resolve to an Issue", rc=1)],
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--issue", "999"])
            assert exc.value.code == 2


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

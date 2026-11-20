"""Tests for close_pr.py skill script."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

import pytest

from scripts.github_core.api import RepoInfo
from tests.skills.claude_skills_import import import_skill_script

# Import the script via importlib (not a package)
_mod = import_skill_script(".claude/skills/github/scripts/pr/close_pr.py")
main = _mod.main

pytestmark = pytest.mark.usefixtures("stub_git_probes", "tmp_path_is_temp_root")
build_parser = _mod.build_parser


# Helpers


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


def _close_open_pr_with_comment(comment_args: list[str]) -> tuple[int, int]:
    """Close an OPEN PR that has no earlier comment; return (exit code, gh calls).

    The gh calls answer in order: PR state, the comment lookup page, then
    success for posting the comment and closing the PR.
    """
    state_json = json.dumps({"state": "OPEN"})
    call_count = 0

    def _side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _completed(stdout=state_json, rc=0)
        if call_count == 2:
            return _completed(stdout="[[]]", rc=0)
        return _completed(rc=0)

    with (
        patch(
            "close_pr.assert_gh_authenticated",
        ),
        patch(
            "close_pr.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ),
        patch(
            "subprocess.run",
            side_effect=_side_effect,
        ),
    ):
        rc = main(["--pull-request", "50", *comment_args])
    return rc, call_count


# Tests: build_parser


class TestBuildParser:
    def test_pull_request_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([])

    def test_valid_args(self):
        args = build_parser().parse_args(["--pull-request", "50"])
        assert args.pull_request == 50


# Tests: main


class TestMain:
    def test_not_authenticated_exits_4(self):
        with patch(
            "close_pr.assert_gh_authenticated",
            side_effect=SystemExit(4),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "1"])
            assert exc.value.code == 4

    def test_pr_not_found_exits_2(self):
        with (
            patch(
                "close_pr.assert_gh_authenticated",
            ),
            patch(
                "close_pr.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch(
                "subprocess.run",
                return_value=_completed(rc=1, stderr="not found"),
            ),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "999"])
            assert exc.value.code == 2

    @pytest.mark.parametrize(
        ("stderr", "expected"),
        [
            ("GraphQL: Could not resolve to a PullRequest with the number of 999.", 2),
            ("gh: Not Found (HTTP 404)", 2),
            ("Could not resolve host: api.github.com", 3),
            ("internal server error", 3),
        ],
    )
    def test_lookup_failure_exit_codes(self, stderr, expected):
        with (
            patch("close_pr.assert_gh_authenticated"),
            patch(
                "close_pr.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch(
                "subprocess.run",
                return_value=_completed(rc=1, stderr=stderr),
            ),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "999"])
            assert exc.value.code == expected

    def test_already_closed_returns_0(self, capsys):
        state_json = json.dumps({"state": "CLOSED"})
        with (
            patch(
                "close_pr.assert_gh_authenticated",
            ),
            patch(
                "close_pr.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch(
                "subprocess.run",
                return_value=_completed(stdout=state_json, rc=0),
            ),
        ):
            rc = main(["--pull-request", "50"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["action"] == "none"
        assert output["state"] == "CLOSED"

    def test_already_merged_returns_0(self, capsys):
        state_json = json.dumps({"state": "MERGED"})
        with (
            patch(
                "close_pr.assert_gh_authenticated",
            ),
            patch(
                "close_pr.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch(
                "subprocess.run",
                return_value=_completed(stdout=state_json, rc=0),
            ),
        ):
            rc = main(["--pull-request", "50"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["state"] == "MERGED"

    def test_close_success(self, capsys):
        state_json = json.dumps({"state": "OPEN"})
        call_count = 0

        def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _completed(stdout=state_json, rc=0)
            return _completed(rc=0)

        with (
            patch(
                "close_pr.assert_gh_authenticated",
            ),
            patch(
                "close_pr.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch(
                "subprocess.run",
                side_effect=_side_effect,
            ),
        ):
            rc = main(["--pull-request", "50"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["action"] == "closed"

    def test_close_with_comment(self, capsys):
        rc, call_count = _close_open_pr_with_comment(["--comment", "Superseded by #51"])
        assert rc == 0
        assert call_count == 4
        output = json.loads(capsys.readouterr().out)
        assert output["commentPosted"] is True
        assert output["commentSkipped"] is False

    def test_close_failure_exits_3(self):
        state_json = json.dumps({"state": "OPEN"})
        call_count = 0

        def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _completed(stdout=state_json, rc=0)
            return _completed(rc=1, stderr="permission denied")

        with (
            patch(
                "close_pr.assert_gh_authenticated",
            ),
            patch(
                "close_pr.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch(
                "subprocess.run",
                side_effect=_side_effect,
            ),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "50"])
            assert exc.value.code == 3

    def test_comment_file_used(self, tmp_path, capsys):
        comment_file = tmp_path / "reason.md"
        comment_file.write_text("Closing because superseded")
        rc, call_count = _close_open_pr_with_comment(["--comment-file", str(comment_file)])
        assert rc == 0
        assert call_count == 4

    def test_comment_file_not_found_exits_2(self):
        with (
            patch(
                "close_pr.assert_gh_authenticated",
            ),
            patch(
                "close_pr.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
        ):
            with pytest.raises(SystemExit) as exc:
                main(
                    [
                        "--pull-request",
                        "50",
                        "--comment-file",
                        "/nonexistent/file.md",
                    ]
                )
            assert exc.value.code == 2

    def test_scratchpad_comment_file_under_temp_dir_closes(self, tmp_path, monkeypatch):
        """Issue #6667: a /tmp/claude-<uid>/ scratchpad file is accepted."""
        scratch = tmp_path / "claude-1000" / "scratchpad"
        scratch.mkdir(parents=True)
        # The real layout: every level below the temp root is mode 700.
        for directory in (scratch.parent, scratch):
            directory.chmod(0o700)
        body = scratch / "close.md"
        body.write_text("Closing from scratchpad.", encoding="utf-8")
        monkeypatch.setenv("TMPDIR", str(tmp_path))
        results = [
            _completed(stdout=json.dumps({"state": "OPEN"})),
            _completed(stdout="[[]]"),
            _completed(),
            _completed(),
        ]
        with (
            patch("close_pr.assert_gh_authenticated"),
            patch("close_pr.resolve_repo_params", return_value=RepoInfo(owner="o", repo="r")),
            patch("subprocess.run", side_effect=results) as mock_run,
        ):
            rc = main(["--pull-request", "50", "--comment-file", str(body)])
        assert rc == 0
        comment_call = mock_run.call_args_list[2].args[0]
        assert "Closing from scratchpad." in comment_call

    def test_comment_file_outside_every_root_exits_2(
        self, external_tmp_path, monkeypatch, stub_temp_roots, capsys
    ):
        outside = external_tmp_path / "outside.md"
        outside.write_text("secret", encoding="utf-8")
        stub_temp_roots()
        with (
            patch("close_pr.assert_gh_authenticated"),
            patch("close_pr.resolve_repo_params", return_value=RepoInfo(owner="o", repo="r")),
            patch("subprocess.run") as mock_run,
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "50", "--comment-file", str(outside)])
            assert exc.value.code == 2
        mock_run.assert_not_called()
        assert "path traversal not allowed" in capsys.readouterr().err

    def test_symlink_in_temp_dir_pointing_outside_exits_2(
        self, tmp_path, external_tmp_path, monkeypatch, stub_temp_roots, capsys
    ):
        target = external_tmp_path / "secret.md"
        target.write_text("secret", encoding="utf-8")
        link = tmp_path / "link.md"
        try:
            link.symlink_to(target)
        except OSError:
            pytest.skip("symlinks unavailable")
        stub_temp_roots(tmp_path)
        with (
            patch("close_pr.assert_gh_authenticated"),
            patch("close_pr.resolve_repo_params", return_value=RepoInfo(owner="o", repo="r")),
            patch("subprocess.run") as mock_run,
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "50", "--comment-file", str(link)])
            assert exc.value.code == 2
        mock_run.assert_not_called()
        assert "path traversal not allowed" in capsys.readouterr().err

    def test_pr_view_non_not_found_error_exits_3(self):
        with (
            patch(
                "close_pr.assert_gh_authenticated",
            ),
            patch(
                "close_pr.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch(
                "subprocess.run",
                return_value=_completed(rc=1, stderr="internal server error"),
            ),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "50"])
            assert exc.value.code == 3

"""Tests for post_pr_comment_reply.py skill script."""

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
    Path(__file__).resolve().parents[1] / ".claude" / "skills" / "github" / "scripts" / "pr"
)


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("post_pr_comment_reply")
main = _mod.main
build_parser = _mod.build_parser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


# ---------------------------------------------------------------------------
# Tests: build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_pull_request_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--body", "test"])

    def test_body_and_body_file_mutually_exclusive(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(
                [
                    "--pull-request",
                    "1",
                    "--body",
                    "text",
                    "--body-file",
                    "f.md",
                ]
            )

    def test_valid_inline_body(self):
        args = build_parser().parse_args(
            [
                "--pull-request",
                "50",
                "--comment-id",
                "123",
                "--body",
                "Fixed.",
            ]
        )
        assert args.pull_request == 50
        assert args.comment_id == 123
        assert args.body == "Fixed."


# ---------------------------------------------------------------------------
# Tests: main
# ---------------------------------------------------------------------------


class TestMain:
    def test_not_authenticated_exits_4(self):
        with patch(
            "post_pr_comment_reply.assert_gh_authenticated",
            side_effect=SystemExit(4),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "1", "--body", "test"])
            assert exc.value.code == 4

    def test_empty_body_exits_1(self):
        with (
            patch(
                "post_pr_comment_reply.assert_gh_authenticated",
            ),
            patch(
                "post_pr_comment_reply.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "1", "--body", ""])
            assert exc.value.code == 2

    def test_body_file_not_found_exits_2(self):
        with (
            patch(
                "post_pr_comment_reply.assert_gh_authenticated",
            ),
            patch(
                "post_pr_comment_reply.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "1", "--body-file", "/nonexistent/file.md"])
            assert exc.value.code == 2

    def test_body_file_path_traversal_exits_2(self):
        """CWE-22: Path traversal in body-file is rejected."""
        with (
            patch(
                "post_pr_comment_reply.assert_gh_authenticated",
            ),
            patch(
                "post_pr_comment_reply.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "1", "--body-file", "../../etc/passwd"])
            assert exc.value.code == 2

    def test_review_comment_reply_success(self, capsys):
        response = json.dumps(
            {
                "id": 999,
                "html_url": "https://example.com",
                "created_at": "now",
            }
        )
        with (
            patch(
                "post_pr_comment_reply.assert_gh_authenticated",
            ),
            patch(
                "post_pr_comment_reply.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch(
                "subprocess.run",
                return_value=_completed(stdout=response, rc=0),
            ),
        ):
            rc = main(
                [
                    "--pull-request",
                    "50",
                    "--comment-id",
                    "123",
                    "--body",
                    "Fixed.",
                ]
            )
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["success"] is True
        assert output["in_reply_to"] == 123

    def test_top_level_comment_success(self, capsys):
        response = json.dumps(
            {
                "id": 888,
                "html_url": "https://example.com",
                "created_at": "now",
            }
        )
        with (
            patch(
                "post_pr_comment_reply.assert_gh_authenticated",
            ),
            patch(
                "post_pr_comment_reply.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch(
                "subprocess.run",
                return_value=_completed(stdout=response, rc=0),
            ),
        ):
            rc = main(["--pull-request", "50", "--body", "All addressed."])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["success"] is True
        assert output["in_reply_to"] is None

    def test_api_error_exits_3(self):
        with (
            patch(
                "post_pr_comment_reply.assert_gh_authenticated",
            ),
            patch(
                "post_pr_comment_reply.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch(
                "subprocess.run",
                return_value=_completed(rc=1, stderr="API error"),
            ),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "1", "--body", "test"])
            assert exc.value.code == 3

    def test_body_from_file(self, stub_git_probes, tmp_path_is_temp_root, capsys):
        # The strict reader needs a temp root; CI puts basetemp outside /tmp.
        tmp_path = tmp_path_is_temp_root
        body_file = tmp_path / "body.md"
        body_file.write_text("hello from file")
        response = json.dumps(
            {
                "id": 777,
                "html_url": "https://example.com",
                "created_at": "now",
            }
        )
        with (
            patch(
                "post_pr_comment_reply.assert_gh_authenticated",
            ),
            patch(
                "post_pr_comment_reply.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch(
                "subprocess.run",
                return_value=_completed(stdout=response, rc=0),
            ),
            patch(
                "github_core.validation.assert_valid_body_file",
            ),
        ):
            rc = main(
                [
                    "--pull-request",
                    "1",
                    "--body-file",
                    str(body_file),
                ]
            )
        assert rc == 0


class TestNotFound:
    """A 404 from the replies endpoint exits 2 with a one-line message (D29)."""

    _GH_BODY = (
        '{"message":"Not Found","documentation_url":"https://docs.github.com","status":"404"}'
    )

    def _run(self, argv, stdout="", stderr=""):
        with (
            patch("post_pr_comment_reply.assert_gh_authenticated"),
            patch(
                "post_pr_comment_reply.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch(
                "subprocess.run",
                return_value=_completed(stdout=stdout, stderr=stderr, rc=1),
            ),
        ):
            with pytest.raises(SystemExit) as exc:
                main(argv)
        return exc.value.code

    def test_missing_review_comment_exits_2_with_one_line(self, capsys):
        code = self._run(
            ["--pull-request", "50", "--comment-id", "123", "--body", "x"],
            stdout=self._GH_BODY,
            stderr="gh: Not Found (HTTP 404)",
        )
        assert code == 2
        err = capsys.readouterr().err
        assert err.strip() == "Comment 123 not found on o/r#50"
        assert "}" not in err

    def test_missing_pull_request_exits_2(self, capsys):
        code = self._run(
            ["--pull-request", "50", "--body", "x"],
            stderr="gh: Not Found (HTTP 404)",
        )
        assert code == 2
        assert capsys.readouterr().err.strip() == "Pull request o/r#50 not found"

    def test_404_detected_from_json_body_alone(self, capsys):
        code = self._run(
            ["--pull-request", "50", "--comment-id", "9", "--body", "x"],
            stdout=self._GH_BODY,
        )
        assert code == 2
        assert "Comment 9 not found" in capsys.readouterr().err

    def test_non_404_failure_still_exits_3(self, capsys):
        code = self._run(
            ["--pull-request", "50", "--comment-id", "9", "--body", "x"],
            stderr="gh: Server Error (HTTP 500)",
        )
        assert code == 3
        assert "Failed to post comment" in capsys.readouterr().err

    def test_forbidden_is_not_reported_as_not_found(self):
        code = self._run(
            ["--pull-request", "50", "--comment-id", "9", "--body", "x"],
            stderr="gh: Forbidden (HTTP 403)",
        )
        assert code == 3

"""Tests for new_pr_review_comment.py skill script."""

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


_mod = _import_script("new_pr_review_comment")
main = _mod.main
build_parser = _mod.build_parser

HEAD_SHA = "a" * 40
BASE_ARGS = [
    "--pull-request",
    "123",
    "--path",
    "src/app.py",
    "--line",
    "47",
    "--body",
    "Please rename this.",
]


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


def _created(comment_id: int = 99) -> subprocess.CompletedProcess[str]:
    return _completed(
        stdout=json.dumps(
            {
                "id": comment_id,
                "html_url": f"https://github.com/o/r/pull/123#discussion_r{comment_id}",
                "created_at": "2026-10-13T00:00:00Z",
            }
        )
    )


@pytest.fixture
def repo_ready():
    with (
        patch("new_pr_review_comment.assert_gh_authenticated") as auth,
        patch(
            "new_pr_review_comment.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ),
    ):
        yield auth


class TestBuildParser:
    def test_defaults_side_to_right(self):
        args = build_parser().parse_args(BASE_ARGS)
        assert args.side == "RIGHT"
        assert args.line == 47
        assert args.path == "src/app.py"

    def test_line_help_names_file_line_not_diff_position(self):
        help_text = build_parser().format_help()
        assert "File line number on the chosen side" in " ".join(help_text.split())

    def test_accepts_left_side(self):
        args = build_parser().parse_args([*BASE_ARGS, "--side", "LEFT"])
        assert args.side == "LEFT"

    def test_rejects_unknown_side(self):
        with pytest.raises(SystemExit) as exc:
            build_parser().parse_args([*BASE_ARGS, "--side", "MIDDLE"])
        assert exc.value.code == 2

    @pytest.mark.parametrize("missing", ["--pull-request", "--path", "--line"])
    def test_required_arguments(self, missing: str):
        argv = list(BASE_ARGS)
        index = argv.index(missing)
        del argv[index : index + 2]
        with pytest.raises(SystemExit) as exc:
            build_parser().parse_args(argv)
        assert exc.value.code == 2

    @pytest.mark.parametrize("bad_line", ["0", "-3", "abc"])
    def test_rejects_non_positive_line(self, bad_line: str):
        argv = list(BASE_ARGS)
        argv[argv.index("--line") + 1] = bad_line
        with pytest.raises(SystemExit) as exc:
            build_parser().parse_args(argv)
        assert exc.value.code == 2

    def test_body_and_body_file_mutually_exclusive(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([*BASE_ARGS, "--body-file", "f.md"])

    def test_body_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(BASE_ARGS[:-2])


class TestMainSuccess:
    def test_posts_review_comment_with_head_sha(self, repo_ready, capsys):
        with patch(
            "new_pr_review_comment.subprocess.run",
            side_effect=[_completed(stdout=f"{HEAD_SHA}\n"), _created()],
        ) as run:
            assert main(BASE_ARGS) == 0

        head_call, post_call = run.call_args_list
        assert head_call.args[0][:3] == ["gh", "api", "repos/o/r/pulls/123"]
        post_args = post_call.args[0]
        assert post_args[:5] == ["gh", "api", "repos/o/r/pulls/123/comments", "-X", "POST"]
        assert "commit_id=" + HEAD_SHA in post_args
        assert "path=src/app.py" in post_args
        assert "side=RIGHT" in post_args
        assert "body=Please rename this." in post_args
        line_index = post_args.index("line=47")
        assert post_args[line_index - 1] == "-F"

        out = json.loads(capsys.readouterr().out)
        assert out == {
            "success": True,
            "comment_id": 99,
            "html_url": "https://github.com/o/r/pull/123#discussion_r99",
            "pull_request": 123,
            "path": "src/app.py",
            "line": 47,
            "side": "RIGHT",
            "commit_id": HEAD_SHA,
            "created_at": "2026-10-13T00:00:00Z",
        }

    def test_gh_output_is_decoded_as_utf8(self, repo_ready):
        with patch(
            "new_pr_review_comment.subprocess.run",
            side_effect=[_completed(stdout=HEAD_SHA), _created()],
        ) as run:
            assert main(BASE_ARGS) == 0

        for call in run.call_args_list:
            assert call.kwargs["encoding"] == "utf-8"
            assert call.kwargs["errors"] == "replace"

    def test_left_side_is_sent(self, repo_ready, capsys):
        with patch(
            "new_pr_review_comment.subprocess.run",
            side_effect=[_completed(stdout=HEAD_SHA), _created()],
        ) as run:
            assert main([*BASE_ARGS, "--side", "LEFT"]) == 0
        assert "side=LEFT" in run.call_args_list[1].args[0]
        assert json.loads(capsys.readouterr().out)["side"] == "LEFT"

    def test_requests_rest_only_auth(self, repo_ready):
        with patch(
            "new_pr_review_comment.subprocess.run",
            side_effect=[_completed(stdout=HEAD_SHA), _created()],
        ):
            main(BASE_ARGS)
        repo_ready.assert_called_once_with(rest_only=True)

    def test_body_file_is_read(self, repo_ready, tmp_path, capsys):
        body_file = tmp_path / "body.md"
        body_file.write_text("From a file\nsecond line", encoding="utf-8")
        argv = [a for a in BASE_ARGS[:-2]] + ["--body-file", str(body_file)]
        with (
            patch("new_pr_review_comment.assert_valid_body_file") as validate,
            patch(
                "new_pr_review_comment.subprocess.run",
                side_effect=[_completed(stdout=HEAD_SHA), _created()],
            ) as run,
        ):
            assert main(argv) == 0
        validate.assert_called_once_with(str(body_file))
        assert "body=From a file\nsecond line" in run.call_args_list[1].args[0]
        capsys.readouterr()

    def test_body_starting_with_at_sign_is_literal(self, repo_ready):
        argv = BASE_ARGS[:-1] + ["@secret"]
        with patch(
            "new_pr_review_comment.subprocess.run",
            side_effect=[_completed(stdout=HEAD_SHA), _created()],
        ) as run:
            main(argv)
        post_args = run.call_args_list[1].args[0]
        assert "body=@secret" in post_args
        assert post_args[post_args.index("body=@secret") - 1] == "-f"


class TestMainUsageErrors:
    def test_not_authenticated_exits_4(self):
        with patch(
            "new_pr_review_comment.assert_gh_authenticated",
            side_effect=SystemExit(4),
        ):
            with pytest.raises(SystemExit) as exc:
                main(BASE_ARGS)
        assert exc.value.code == 4

    @pytest.mark.parametrize("body", ["", "   ", "line one\\nline two"])
    def test_invalid_inline_body_exits_2(self, repo_ready, body: str):
        argv = BASE_ARGS[:-1] + [body]
        with patch("new_pr_review_comment.subprocess.run") as run:
            with pytest.raises(SystemExit) as exc:
                main(argv)
        assert exc.value.code == 2
        run.assert_not_called()

    def test_missing_body_file_exits_2(self, repo_ready):
        argv = BASE_ARGS[:-2] + ["--body-file", "/nonexistent/body.md"]
        with patch("new_pr_review_comment.subprocess.run") as run:
            with pytest.raises(SystemExit) as exc:
                main(argv)
        assert exc.value.code == 2
        run.assert_not_called()


class TestHeadShaFailures:
    def test_pull_request_not_found_exits_2(self, repo_ready, capsys):
        with patch(
            "new_pr_review_comment.subprocess.run",
            return_value=_completed(stderr="gh: Not Found (HTTP 404)", rc=1),
        ):
            with pytest.raises(SystemExit) as exc:
                main(BASE_ARGS)
        assert exc.value.code == 2
        assert "o/r#123 not found" in capsys.readouterr().err

    def test_malformed_head_sha_exits_3(self, repo_ready):
        with patch(
            "new_pr_review_comment.subprocess.run",
            return_value=_completed(stdout="not-a-sha"),
        ):
            with pytest.raises(SystemExit) as exc:
                main(BASE_ARGS)
        assert exc.value.code == 3

    def test_head_lookup_server_error_exits_3(self, repo_ready):
        with patch(
            "new_pr_review_comment.subprocess.run",
            return_value=_completed(stderr="gh: Bad Gateway (HTTP 502)", rc=1),
        ):
            with pytest.raises(SystemExit) as exc:
                main(BASE_ARGS)
        assert exc.value.code == 3


class TestPostFailures:
    def _run(self, post_result: subprocess.CompletedProcess[str]) -> int:
        with patch(
            "new_pr_review_comment.subprocess.run",
            side_effect=[_completed(stdout=HEAD_SHA), post_result],
        ):
            with pytest.raises(SystemExit) as exc:
                main(BASE_ARGS)
        code = exc.value.code
        assert isinstance(code, int)
        return code

    def test_not_found_exits_2(self, repo_ready):
        assert self._run(_completed(stderr="gh: Not Found (HTTP 404)", rc=1)) == 2

    def test_unprocessable_line_exits_2_with_reason(self, repo_ready, capsys):
        stderr = (
            "gh: Unprocessable Entity: "
            '"pull_request_review_thread.line must be part of the diff" (HTTP 422)'
        )
        assert self._run(_completed(stderr=stderr, rc=1)) == 2
        err = capsys.readouterr().err
        assert "src/app.py:47" in err
        assert "must be part of the diff" in err

    def test_unauthorized_exits_4(self, repo_ready):
        assert self._run(_completed(stderr="gh: Bad credentials (HTTP 401)", rc=1)) == 4

    def test_forbidden_exits_4(self, repo_ready):
        stderr = "gh: Resource not accessible by integration (HTTP 403)"
        assert self._run(_completed(stderr=stderr, rc=1)) == 4

    def test_rate_limited_forbidden_exits_3(self, repo_ready):
        stderr = "gh: API rate limit exceeded for user (HTTP 403)"
        assert self._run(_completed(stderr=stderr, rc=1)) == 3

    def test_server_error_exits_3(self, repo_ready):
        assert self._run(_completed(stderr="gh: Server Error (HTTP 500)", rc=1)) == 3

    def test_failure_without_http_status_exits_3(self, repo_ready):
        assert self._run(_completed(stderr="connection reset by peer", rc=1)) == 3

    def test_json_body_status_422_exits_2(self, repo_ready):
        body = '{"message": "Validation Failed", "status": "422"}'
        assert self._run(_completed(stdout=body, rc=1)) == 2

    def test_error_text_is_sanitized(self, repo_ready, capsys):
        stderr = "gh: boom token ghp_" + "a" * 36 + " (HTTP 500)"
        assert self._run(_completed(stderr=stderr, rc=1)) == 3
        assert "ghp_" not in capsys.readouterr().err

    def test_invalid_json_response_exits_3(self, repo_ready):
        assert self._run(_completed(stdout="<html>")) == 3

    def test_timeout_exits_3(self, repo_ready):
        with patch(
            "new_pr_review_comment.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="gh", timeout=30),
        ):
            with pytest.raises(SystemExit) as exc:
                main(BASE_ARGS)
        assert exc.value.code == 3

    @pytest.mark.parametrize("payload", ["[]", '["a"]', "null", '"text"', "42"])
    def test_non_object_json_response_exits_3(self, repo_ready, payload: str):
        assert self._run(_completed(stdout=payload)) == 3

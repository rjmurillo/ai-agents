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
    "--output-format",
    "json",
    "--pull-request",
    "123",
    "--path",
    "src/app.py",
    "--line",
    "47",
    "--body",
    "Please rename this.",
]


def _envelope(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


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

        out = _envelope(capsys)
        assert out["Success"] is True
        assert out["Error"] is None
        assert out["Metadata"]["Script"] == "new_pr_review_comment.py"
        assert out["Data"] == {
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
        assert _envelope(capsys)["Data"]["side"] == "LEFT"

    def test_human_format_prints_summary(self, repo_ready, capsys):
        argv = [*BASE_ARGS[2:], "--output-format", "human"]
        with patch(
            "new_pr_review_comment.subprocess.run",
            side_effect=[_completed(stdout=HEAD_SHA), _created()],
        ):
            assert main(argv) == 0
        out = capsys.readouterr().out
        assert "[PASS] Created review comment on #123 at src/app.py:47" in out

    def test_requests_rest_only_auth(self, repo_ready):
        with patch(
            "new_pr_review_comment.subprocess.run",
            side_effect=[_completed(stdout=HEAD_SHA), _created()],
        ):
            main(BASE_ARGS)
        repo_ready.assert_called_once_with(rest_only=True)

    def test_body_file_is_read(self, repo_ready, stub_git_probes, tmp_path_is_temp_root, capsys):
        body_file = tmp_path_is_temp_root / "body.md"
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

    def test_body_file_not_utf8_exits_2(
        self, repo_ready, stub_git_probes, tmp_path_is_temp_root, capsys
    ):
        body_file = tmp_path_is_temp_root / "body.md"
        body_file.write_bytes(b"caf\xe9 in cp1252\n")
        argv = BASE_ARGS[:-2] + ["--body-file", str(body_file)]
        with (
            patch("new_pr_review_comment.assert_valid_body_file"),
            patch("new_pr_review_comment.subprocess.run") as run,
        ):
            with pytest.raises(SystemExit) as exc:
                main(argv)
        assert exc.value.code == 2
        run.assert_not_called()
        assert f"Failed to read body file {body_file}" in capsys.readouterr().err

    def test_body_file_os_error_exits_2(
        self, repo_ready, stub_git_probes, tmp_path_is_temp_root, capsys
    ):
        argv = BASE_ARGS[:-2] + ["--body-file", str(tmp_path_is_temp_root)]
        with (
            patch("new_pr_review_comment.assert_valid_body_file"),
            patch("new_pr_review_comment.subprocess.run") as run,
        ):
            with pytest.raises(SystemExit) as exc:
                main(argv)
        assert exc.value.code == 2
        run.assert_not_called()
        assert f"Failed to read body file {tmp_path_is_temp_root}" in capsys.readouterr().err

    @pytest.mark.parametrize("content", ["", "  \n\t\n"])
    def test_empty_body_file_exits_2(
        self, repo_ready, stub_git_probes, tmp_path_is_temp_root, content: str
    ):
        body_file = tmp_path_is_temp_root / "body.md"
        body_file.write_text(content, encoding="utf-8")
        argv = BASE_ARGS[:-2] + ["--body-file", str(body_file)]
        with (
            patch("new_pr_review_comment.assert_valid_body_file"),
            patch("new_pr_review_comment.subprocess.run") as run,
        ):
            with pytest.raises(SystemExit) as exc:
                main(argv)
        assert exc.value.code == 2
        run.assert_not_called()

    def test_one_line_body_file_naming_backslash_n_is_posted(
        self, repo_ready, stub_git_probes, tmp_path_is_temp_root, capsys
    ):
        body_file = tmp_path_is_temp_root / "body.md"
        body_file.write_text("Split on the literal \\n here.\n", encoding="utf-8")
        argv = BASE_ARGS[:-2] + ["--body-file", str(body_file)]
        with (
            patch("new_pr_review_comment.assert_valid_body_file"),
            patch(
                "new_pr_review_comment.subprocess.run",
                side_effect=[_completed(stdout=HEAD_SHA), _created()],
            ) as run,
        ):
            assert main(argv) == 0
        assert "body=Split on the literal \\n here.\n" in run.call_args_list[1].args[0]
        capsys.readouterr()


class TestHeadShaFailures:
    def _run(self, result: subprocess.CompletedProcess[str], capsys) -> tuple[int, dict]:
        with patch("new_pr_review_comment.subprocess.run", return_value=result) as run:
            code = main(BASE_ARGS)
        assert run.call_count == 1
        return code, _envelope(capsys)

    def test_pull_request_not_found_exits_2(self, repo_ready, capsys):
        code, out = self._run(_completed(stderr="gh: Not Found (HTTP 404)", rc=1), capsys)
        assert code == 2
        assert out["Success"] is False
        assert out["Error"]["Code"] == 2
        assert out["Error"]["Type"] == "NotFound"
        assert "o/r#123 not found" in out["Error"]["Message"]

    def test_malformed_head_sha_exits_3(self, repo_ready, capsys):
        code, out = self._run(_completed(stdout="not-a-sha"), capsys)
        assert code == 3
        assert out["Error"]["Type"] == "ApiError"

    def test_head_lookup_server_error_exits_3(self, repo_ready, capsys):
        code, out = self._run(_completed(stderr="gh: Bad Gateway (HTTP 502)", rc=1), capsys)
        assert code == 3
        assert out["Error"] == {
            "Message": out["Error"]["Message"],
            "Code": 3,
            "Type": "ApiError",
        }
        assert out["Data"] == {
            "pull_request": 123,
            "path": "src/app.py",
            "line": 47,
            "side": "RIGHT",
        }


class TestPostFailures:
    def _run(self, post_result: subprocess.CompletedProcess[str], capsys) -> tuple[int, dict]:
        with patch(
            "new_pr_review_comment.subprocess.run",
            side_effect=[_completed(stdout=HEAD_SHA), post_result],
        ):
            code = main(BASE_ARGS)
        out = _envelope(capsys)
        assert out["Success"] is False
        assert out["Error"]["Code"] == code
        return code, out

    def test_not_found_exits_2(self, repo_ready, capsys):
        code, out = self._run(_completed(stderr="gh: Not Found (HTTP 404)", rc=1), capsys)
        assert (code, out["Error"]["Type"]) == (2, "NotFound")

    def test_unprocessable_line_exits_2_with_reason(self, repo_ready, capsys):
        stderr = (
            "gh: Unprocessable Entity: "
            '"pull_request_review_thread.line must be part of the diff" (HTTP 422)'
        )
        code, out = self._run(_completed(stderr=stderr, rc=1), capsys)
        assert (code, out["Error"]["Type"]) == (2, "InvalidParams")
        assert "src/app.py:47" in out["Error"]["Message"]
        assert "must be part of the diff" in out["Error"]["Message"]

    def test_bad_request_exits_2(self, repo_ready, capsys):
        code, out = self._run(_completed(stderr="gh: Bad Request (HTTP 400)", rc=1), capsys)
        assert (code, out["Error"]["Type"]) == (2, "InvalidParams")

    def test_unauthorized_exits_4(self, repo_ready, capsys):
        code, out = self._run(_completed(stderr="gh: Bad credentials (HTTP 401)", rc=1), capsys)
        assert (code, out["Error"]["Type"]) == (4, "AuthError")

    def test_forbidden_exits_4(self, repo_ready, capsys):
        stderr = "gh: Resource not accessible by integration (HTTP 403)"
        code, out = self._run(_completed(stderr=stderr, rc=1), capsys)
        assert (code, out["Error"]["Type"]) == (4, "AuthError")

    def test_rate_limited_forbidden_exits_3(self, repo_ready, capsys):
        stderr = "gh: API rate limit exceeded for user (HTTP 403)"
        code, out = self._run(_completed(stderr=stderr, rc=1), capsys)
        assert (code, out["Error"]["Type"]) == (3, "RateLimitError")

    def test_transport_blocked_forbidden_exits_2(self, repo_ready, capsys):
        text = "gh: Forbidden (HTTP 403)"
        with patch(
            "new_pr_review_comment.classify_gh_failure_text",
            return_value=_mod.GhAuthStatus.TRANSPORT_BLOCKED,
        ):
            code, out = self._run(_completed(stderr=text, rc=1), capsys)
        assert (code, out["Error"]["Type"]) == (2, "General")

    def test_transient_forbidden_exits_3(self, repo_ready, capsys):
        text = "gh: Forbidden (HTTP 403)"
        with patch(
            "new_pr_review_comment.classify_gh_failure_text",
            return_value=_mod.GhAuthStatus.TRANSIENT_ERROR,
        ):
            code, out = self._run(_completed(stderr=text, rc=1), capsys)
        assert (code, out["Error"]["Type"]) == (3, "ApiError")

    def test_server_error_exits_3(self, repo_ready, capsys):
        code, out = self._run(_completed(stderr="gh: Server Error (HTTP 500)", rc=1), capsys)
        assert (code, out["Error"]["Type"]) == (3, "ApiError")

    def test_failure_without_http_status_exits_3(self, repo_ready, capsys):
        code, _ = self._run(_completed(stderr="connection reset by peer", rc=1), capsys)
        assert code == 3

    def test_failure_with_no_output_has_message(self, repo_ready, capsys):
        code, out = self._run(_completed(rc=1), capsys)
        assert code == 3
        assert "no output from gh" in out["Error"]["Message"]

    def test_json_body_status_422_exits_2(self, repo_ready, capsys):
        body = '{"message": "Validation Failed", "status": "422"}'
        code, _ = self._run(_completed(stdout=body, rc=1), capsys)
        assert code == 2

    def test_error_text_is_sanitized(self, repo_ready, capsys):
        stderr = "gh: boom token ghp_" + "a" * 36 + " (HTTP 500)"
        code, out = self._run(_completed(stderr=stderr, rc=1), capsys)
        assert code == 3
        assert "ghp_" not in out["Error"]["Message"]

    def test_invalid_json_response_exits_3(self, repo_ready, capsys):
        code, _ = self._run(_completed(stdout="<html>"), capsys)
        assert code == 3

    def test_timeout_exits_3(self, repo_ready, capsys):
        with patch(
            "new_pr_review_comment.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="gh", timeout=30),
        ):
            code = main(BASE_ARGS)
        out = _envelope(capsys)
        assert code == 3
        assert out["Error"]["Type"] == "Timeout"
        assert "Timed out after 30s" in out["Error"]["Message"]

    @pytest.mark.parametrize("payload", ["[]", '["a"]', "null", '"text"', "42"])
    def test_non_object_json_response_exits_3(self, repo_ready, capsys, payload: str):
        code, _ = self._run(_completed(stdout=payload), capsys)
        assert code == 3

"""Tests for get_issue_comments.py skill script (issue #2475)."""

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
    Path(__file__).resolve().parents[1] / ".claude" / "skills" / "github" / "scripts" / "issue"
)


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("get_issue_comments")
main = _mod.main
build_parser = _mod.build_parser


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


def _api_comment(login: str, body: str, at: str = "2026-06-06T00:00:00Z"):
    return {
        "user": {"login": login},
        "created_at": at,
        "updated_at": at,
        "body": body,
        "html_url": f"https://github.com/o/r/issues/1#c-{login}",
    }


def _slurped(*pages: list[dict]):
    # gh api --slurp wraps each page's array in an outer list.
    return _completed(stdout=json.dumps(list(pages)), rc=0)


def _envelope(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


class TestBuildParser:
    def test_issue_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([])

    def test_limit_defaults_to_zero(self):
        args = build_parser().parse_args(["--issue", "5"])
        assert args.limit == 0


class TestMain:
    def test_not_authenticated_exits_4(self):
        with patch("get_issue_comments.assert_gh_authenticated", side_effect=SystemExit(4)):
            with pytest.raises(SystemExit) as exc:
                main(["--issue", "1"])
            assert exc.value.code == 4

    def test_returns_normalized_comments(self, capsys):
        page = [
            _api_comment("coderabbitai[bot]", "auto plan"),
            _api_comment("rjmurillo", "keep open P3"),
        ]
        with (
            patch("get_issue_comments.assert_gh_authenticated"),
            patch(
                "get_issue_comments.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch("subprocess.run", side_effect=[_slurped(page)]),
        ):
            rc = main(["--issue", "2099"])
        assert rc == 0
        env = _envelope(capsys)
        assert env["Success"] is True
        assert env["Metadata"]["Script"] == "get_issue_comments.py"
        data = env["Data"]
        assert data["issue"] == 2099
        assert data["count"] == 2
        assert data["comments"][0]["author"] == "coderabbitai[bot]"
        assert data["comments"][1]["author"] == "rjmurillo"
        assert data["comments"][1]["body"] == "keep open P3"
        assert "createdAt" in data["comments"][0]

    def test_subprocess_reads_utf8(self, capsys):
        with (
            patch("get_issue_comments.assert_gh_authenticated"),
            patch(
                "get_issue_comments.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch("subprocess.run", side_effect=[_slurped([])]) as mock_run,
        ):
            rc = main(["--issue", "1"])

        assert rc == 0
        _envelope(capsys)
        assert mock_run.call_args.kwargs["encoding"] == "utf-8"

    def test_flattens_multiple_pages(self, capsys):
        with (
            patch("get_issue_comments.assert_gh_authenticated"),
            patch(
                "get_issue_comments.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch(
                "subprocess.run",
                side_effect=[
                    _slurped(
                        [_api_comment("a", "1"), _api_comment("b", "2")],
                        [_api_comment("c", "3")],
                    )
                ],
            ),
        ):
            rc = main(["--issue", "1"])
        assert rc == 0
        data = _envelope(capsys)["Data"]
        assert data["count"] == 3

    def test_manual_pagination_paces_between_full_pages(self, capsys):
        first_page = [_api_comment(f"user-{index}", str(index)) for index in range(100)]
        second_page = [_api_comment("last", "done")]
        sleeps: list[float] = []
        calls: list[list[str]] = []

        def fake_run(command: list[str], **kwargs):
            del kwargs
            calls.append(command)
            payload = first_page if len(calls) == 1 else second_page
            return _completed(stdout=json.dumps(payload), rc=0)

        with (
            patch("get_issue_comments.assert_gh_authenticated"),
            patch(
                "get_issue_comments.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch("subprocess.run", side_effect=fake_run),
            patch("get_issue_comments.time.sleep", sleeps.append),
        ):
            rc = main(["--issue", "1"])

        assert rc == 0
        data = _envelope(capsys)["Data"]
        assert data["count"] == 101
        assert sleeps == [_mod.ISSUE_COMMENT_PAGE_PACE_SECONDS]
        assert all("--paginate" not in call for call in calls)
        assert "page=1" in calls[0][2]
        assert "page=2" in calls[1][2]

    def test_rate_limit_refusal_retries_issue_comment_page(self, capsys):
        sleeps: list[float] = []
        calls: list[list[str]] = []

        def fake_run(command: list[str], **kwargs):
            del kwargs
            calls.append(command)
            if len(calls) == 1:
                return _completed(
                    stderr="HTTP 403: API rate limit exceeded for user ID 6811113",
                    rc=1,
                )
            return _completed(stdout=json.dumps([_api_comment("alice", "ok")]), rc=0)

        with (
            patch("get_issue_comments.assert_gh_authenticated"),
            patch(
                "get_issue_comments.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch("subprocess.run", side_effect=fake_run),
            patch("get_issue_comments.time.sleep", sleeps.append),
        ):
            rc = main(["--issue", "1"])

        assert rc == 0
        data = _envelope(capsys)["Data"]
        assert data["count"] == 1
        assert len(calls) == 2
        assert sleeps == [_mod.ISSUE_COMMENT_REFUSAL_BACKOFF_SECONDS[0]]

    def test_limit_keeps_most_recent(self, capsys):
        with (
            patch("get_issue_comments.assert_gh_authenticated"),
            patch(
                "get_issue_comments.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch(
                "subprocess.run",
                side_effect=[
                    _slurped(
                        [
                            _api_comment("a", "old"),
                            _api_comment("b", "mid"),
                            _api_comment("c", "new"),
                        ]
                    )
                ],
            ),
        ):
            rc = main(["--issue", "1", "--limit", "1"])
        assert rc == 0
        data = _envelope(capsys)["Data"]
        assert data["count"] == 1
        assert data["comments"][0]["body"] == "new"

    def test_negative_limit_returns_invalid_params(self, capsys):
        with patch("subprocess.run") as mock_run:
            rc = main(["--issue", "1", "--limit", "-1"])

        assert rc == 1
        env = _envelope(capsys)
        assert env["Success"] is False
        assert env["Error"]["Type"] == "InvalidParams"
        assert env["Data"] == {"issue": 1, "limit": -1}
        mock_run.assert_not_called()

    def test_empty_thread(self, capsys):
        with (
            patch("get_issue_comments.assert_gh_authenticated"),
            patch(
                "get_issue_comments.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch("subprocess.run", side_effect=[_completed(stdout="[]", rc=0)]),
        ):
            rc = main(["--issue", "1"])
        assert rc == 0
        data = _envelope(capsys)["Data"]
        assert data["count"] == 0
        assert data["comments"] == []

    def test_api_failure_exits_3(self, capsys):
        with (
            patch("get_issue_comments.assert_gh_authenticated"),
            patch(
                "get_issue_comments.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch("subprocess.run", side_effect=[_completed(stderr="server 500", rc=1)]),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--issue", "1"])
            assert exc.value.code == 3
        env = _envelope(capsys)
        assert env["Success"] is False

    def test_timeout_exits_3(self, capsys):
        with (
            patch("get_issue_comments.assert_gh_authenticated"),
            patch(
                "get_issue_comments.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch(
                "subprocess.run",
                side_effect=subprocess.TimeoutExpired("gh", 60),
            ),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--issue", "1"])

        assert exc.value.code == 3
        assert _envelope(capsys)["Error"]["Type"] == "ApiError"

    def test_api_failure_without_output_uses_return_code_fallback(self, capsys):
        with (
            patch("get_issue_comments.assert_gh_authenticated"),
            patch(
                "get_issue_comments.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch("subprocess.run", side_effect=[_completed(rc=17)]),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--issue", "1"])
            assert exc.value.code == 3
        env = _envelope(capsys)
        assert env["Error"]["Message"] == (
            "Failed to fetch comments for issue #1: "
            "gh api exited with return code 17 while fetching issue comment page 1 "
            "and no error output"
        )

    def test_api_failure_respects_human_output_format(self, capsys):
        with (
            patch("get_issue_comments.assert_gh_authenticated"),
            patch(
                "get_issue_comments.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch("subprocess.run", side_effect=[_completed(stderr="server 500", rc=1)]),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--issue", "1", "--output-format", "human"])
            assert exc.value.code == 3

        assert "[FAIL] Failed to fetch comments for issue #1: server 500" in (
            capsys.readouterr().out
        )

    def test_not_found_exits_2(self, capsys):
        with (
            patch("get_issue_comments.assert_gh_authenticated"),
            patch(
                "get_issue_comments.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch(
                "subprocess.run",
                side_effect=[_completed(stderr="Could not resolve to a Repository", rc=1)],
            ),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--issue", "1"])
            assert exc.value.code == 2

    def test_missing_user_login_is_none(self, capsys):
        bad = {"created_at": "2026-06-06T00:00:00Z", "body": "ghost"}
        with (
            patch("get_issue_comments.assert_gh_authenticated"),
            patch(
                "get_issue_comments.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch("subprocess.run", side_effect=[_slurped([bad])]),
        ):
            rc = main(["--issue", "1"])
        assert rc == 0
        data = _envelope(capsys)["Data"]
        assert data["comments"][0]["author"] is None
        assert data["comments"][0]["body"] == "ghost"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))


class TestNormalizePreservesIds:
    """Issue #4378: id and node_id must be preserved in normalized output."""

    def test_id_and_node_id_preserved(self, capsys):
        page = [{
            "user": {"login": "alice"},
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "body": "hello",
            "html_url": "https://github.com/o/r/issues/1#c1",
            "id": 123456789,
            "node_id": "IC_abc123",
        }]
        with patch("get_issue_comments.assert_gh_authenticated"), \
             patch("get_issue_comments.resolve_repo_params",
                   return_value=type("R", (), {"owner": "o", "repo": "r"})()) , \
             patch("subprocess.run",
                   return_value=_completed(stdout=json.dumps([page]), rc=0)):
            rc = main(["--issue", "1"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        comment = out["Data"]["comments"][0]
        assert comment["id"] == 123456789
        assert comment["node_id"] == "IC_abc123"

    def test_missing_id_yields_none(self, capsys):
        page = [{
            "user": {"login": "alice"},
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "body": "hello",
            "html_url": "https://github.com/o/r/issues/1#c1",
        }]
        with patch("get_issue_comments.assert_gh_authenticated"), \
             patch("get_issue_comments.resolve_repo_params",
                   return_value=type("R", (), {"owner": "o", "repo": "r"})()) , \
             patch("subprocess.run",
                   return_value=_completed(stdout=json.dumps([page]), rc=0)):
            rc = main(["--issue", "1"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        comment = out["Data"]["comments"][0]
        assert comment["id"] is None
        assert comment["node_id"] is None

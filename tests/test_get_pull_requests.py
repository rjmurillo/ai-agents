"""Tests for get_pull_requests.py skill script."""

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
    / ".claude" / "skills" / "github" / "scripts" / "pr"
)


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("get_pull_requests")
main = _mod.main
build_parser = _mod.build_parser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


def _prs_json(prs=None):
    if prs is None:
        prs = []
    return json.dumps(prs)


def _pr(number=1, title="PR", head="feature", base="main", state="OPEN"):
    return {
        "number": number,
        "title": title,
        "headRefName": head,
        "baseRefName": base,
        "state": state,
    }


# ---------------------------------------------------------------------------
# Tests: build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_defaults(self):
        args = build_parser().parse_args([])
        assert args.state == "open"
        assert args.limit == 30

    def test_all_filters(self):
        args = build_parser().parse_args([
            "--state", "merged", "--label", "bug,P1",
            "--author", "alice", "--base", "main", "--head", "feature",
            "--limit", "100",
        ])
        assert args.state == "merged"
        assert args.label == "bug,P1"
        assert args.author == "alice"
        assert args.limit == 100


# ---------------------------------------------------------------------------
# Tests: main
# ---------------------------------------------------------------------------


class TestMain:
    def test_not_authenticated_exits_4(self, capsys):
        with patch(
            "get_pull_requests.assert_gh_authenticated",
            side_effect=SystemExit(4),
        ):
            with pytest.raises(SystemExit) as exc:
                main([])
            assert exc.value.code == 4
        payload = json.loads(capsys.readouterr().out)
        assert payload["Success"] is False
        assert payload["Error"]["Code"] == 4
        assert payload["Error"]["Type"] == "AuthError"

    def test_success_open_prs(self, capsys):
        prs = [_pr(1, "First"), _pr(2, "Second")]
        with patch(
            "get_pull_requests.assert_gh_authenticated",
        ), patch(
            "get_pull_requests.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_completed(stdout=_prs_json(prs), rc=0),
        ):
            rc = main([])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)["Data"]["pull_requests"]
        assert len(output) == 2
        assert output[0]["number"] == 1

    def test_merged_filter(self, capsys):
        prs = [
            _pr(1, "Merged", state="MERGED"),
            _pr(2, "Closed", state="CLOSED"),
        ]
        with patch(
            "get_pull_requests.assert_gh_authenticated",
        ), patch(
            "get_pull_requests.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_completed(stdout=_prs_json(prs), rc=0),
        ):
            rc = main(["--state", "merged"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)["Data"]["pull_requests"]
        assert len(output) == 1
        assert output[0]["state"] == "MERGED"

    def test_api_error_exits_3(self, capsys):
        with patch(
            "get_pull_requests.assert_gh_authenticated",
        ), patch(
            "get_pull_requests.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_completed(rc=1, stderr="API error"),
        ):
            with pytest.raises(SystemExit) as exc:
                main([])
            assert exc.value.code == 3
        payload = json.loads(capsys.readouterr().out)
        assert payload["Success"] is False
        assert payload["Error"]["Type"] == "ApiError"

    def test_empty_results(self, capsys):
        with patch(
            "get_pull_requests.assert_gh_authenticated",
        ), patch(
            "get_pull_requests.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_completed(stdout="[]", rc=0),
        ):
            rc = main([])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)["Data"]["pull_requests"]
        assert output == []

    def test_search_filter(self, capsys):
        prs = [_pr(5, "Fix auth bug")]
        with patch(
            "get_pull_requests.assert_gh_authenticated",
        ), patch(
            "get_pull_requests.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_completed(stdout=_prs_json(prs), rc=0),
        ) as mock_run:
            rc = main(["--search", "fix auth"])
        assert rc == 0
        cmd = mock_run.call_args[0][0]
        assert "--search" in cmd
        assert "fix auth" in cmd
        # --search makes gh ignore other filter flags, so we must not pass them
        assert "--state" not in cmd
        assert "--label" not in cmd
        assert "--author" not in cmd
        output = json.loads(capsys.readouterr().out)["Data"]["pull_requests"]
        assert len(output) == 1

    def test_invalid_limit_exits_2(self, capsys):
        with patch(
            "get_pull_requests.assert_gh_authenticated",
        ), patch(
            "get_pull_requests.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--limit", "0"])
            assert exc.value.code == 2
        payload = json.loads(capsys.readouterr().out)
        assert payload["Success"] is False
        assert payload["Error"]["Type"] == "InvalidParams"

    def test_timeout_exits_3(self, capsys):
        with patch(
            "get_pull_requests.assert_gh_authenticated",
        ), patch(
            "get_pull_requests.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="gh", timeout=30),
        ):
            with pytest.raises(SystemExit) as exc:
                main([])
            assert exc.value.code == 3
        payload = json.loads(capsys.readouterr().out)
        assert payload["Success"] is False
        assert payload["Error"]["Type"] == "Timeout"

    def test_gh_missing_exits_3(self, capsys):
        with patch(
            "get_pull_requests.assert_gh_authenticated",
        ), patch(
            "get_pull_requests.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            side_effect=FileNotFoundError("gh"),
        ):
            with pytest.raises(SystemExit) as exc:
                main([])
            assert exc.value.code == 3
        payload = json.loads(capsys.readouterr().out)
        assert payload["Success"] is False
        assert payload["Error"]["Type"] == "ApiError"

    def test_malformed_json_exits_3(self, capsys):
        with patch(
            "get_pull_requests.assert_gh_authenticated",
        ), patch(
            "get_pull_requests.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_completed(stdout="not json", rc=0),
        ):
            with pytest.raises(SystemExit) as exc:
                main([])
            assert exc.value.code == 3
        payload = json.loads(capsys.readouterr().out)
        assert payload["Success"] is False
        assert payload["Error"]["Type"] == "ApiError"

    @pytest.mark.parametrize("payload", ["null", "{}", "42", '"text"'])
    def test_non_list_root_exits_3(self, payload, capsys):
        with patch(
            "get_pull_requests.assert_gh_authenticated",
        ), patch(
            "get_pull_requests.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_completed(stdout=payload, rc=0),
        ):
            with pytest.raises(SystemExit) as exc:
                main([])
            assert exc.value.code == 3
        error = json.loads(capsys.readouterr().out)["Error"]
        assert error["Code"] == 3
        assert error["Type"] == "ApiError"

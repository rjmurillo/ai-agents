"""Tests for get_pull_requests.py skill script."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

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


def _parse_envelope(captured_out: str) -> dict:
    """Parse the JSON envelope from captured stdout."""
    # write_skill_output may print an empty-line tail; take the last JSON line.
    line = captured_out.strip().splitlines()[-1]
    return json.loads(line)


def _assert_envelope_shape(envelope: dict, *, success: bool) -> None:
    """Assert the ADR-056 envelope shape."""
    assert set(envelope.keys()) == {"Success", "Data", "Error", "Metadata"}, (
        f"envelope keys mismatch: {sorted(envelope.keys())}"
    )
    assert envelope["Success"] is success
    assert isinstance(envelope["Metadata"], dict)
    assert envelope["Metadata"].get("Script") == "get_pull_requests.py"
    assert "Version" in envelope["Metadata"]
    assert "Timestamp" in envelope["Metadata"]


# ---------------------------------------------------------------------------
# Tests: build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_defaults(self):
        args = build_parser().parse_args([])
        assert args.state == "open"
        assert args.limit == 30
        # ADR-056: every skill script exposes --output-format
        assert args.output_format == "auto"

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

    def test_output_format_json(self):
        args = build_parser().parse_args(["--output-format", "json"])
        assert args.output_format == "json"


# ---------------------------------------------------------------------------
# Tests: main
# ---------------------------------------------------------------------------


class TestMain:
    def test_not_authenticated_returns_envelope_with_auth_error(self, capsys):
        with patch(
            "get_pull_requests.is_gh_authenticated",
            return_value=False,
        ):
            rc = main(["--output-format", "json"])
        assert rc == 4
        envelope = _parse_envelope(capsys.readouterr().out)
        _assert_envelope_shape(envelope, success=False)
        assert envelope["Error"]["Code"] == 4
        assert envelope["Error"]["Type"] == "AuthError"
        assert "gh auth login" in envelope["Error"]["Message"]

    def test_success_open_prs(self, capsys):
        prs = [_pr(1, "First"), _pr(2, "Second")]
        with patch(
            "get_pull_requests.is_gh_authenticated",
            return_value=True,
        ), patch(
            "get_pull_requests.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_completed(stdout=_prs_json(prs), rc=0),
        ):
            rc = main(["--output-format", "json"])
        assert rc == 0
        envelope = _parse_envelope(capsys.readouterr().out)
        _assert_envelope_shape(envelope, success=True)
        assert envelope["Error"] is None
        pull_requests = envelope["Data"]["PullRequests"]
        assert len(pull_requests) == 2
        assert pull_requests[0]["number"] == 1
        # Schema preserved inside envelope
        assert set(pull_requests[0].keys()) == {"number", "title", "head", "base", "state"}

    def test_merged_filter(self, capsys):
        prs = [
            _pr(1, "Merged", state="MERGED"),
            _pr(2, "Closed", state="CLOSED"),
        ]
        with patch(
            "get_pull_requests.is_gh_authenticated",
            return_value=True,
        ), patch(
            "get_pull_requests.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_completed(stdout=_prs_json(prs), rc=0),
        ):
            rc = main(["--state", "merged", "--output-format", "json"])
        assert rc == 0
        envelope = _parse_envelope(capsys.readouterr().out)
        _assert_envelope_shape(envelope, success=True)
        pull_requests = envelope["Data"]["PullRequests"]
        assert len(pull_requests) == 1
        assert pull_requests[0]["state"] == "MERGED"

    def test_api_error_returns_envelope_with_error(self, capsys):
        with patch(
            "get_pull_requests.is_gh_authenticated",
            return_value=True,
        ), patch(
            "get_pull_requests.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_completed(rc=1, stderr="API error"),
        ):
            rc = main(["--output-format", "json"])
        assert rc == 3
        envelope = _parse_envelope(capsys.readouterr().out)
        _assert_envelope_shape(envelope, success=False)
        assert envelope["Error"]["Code"] == 3
        assert envelope["Error"]["Type"] == "ApiError"
        assert "API error" in envelope["Error"]["Message"]

    def test_empty_results(self, capsys):
        with patch(
            "get_pull_requests.is_gh_authenticated",
            return_value=True,
        ), patch(
            "get_pull_requests.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_completed(stdout="[]", rc=0),
        ):
            rc = main(["--output-format", "json"])
        assert rc == 0
        envelope = _parse_envelope(capsys.readouterr().out)
        _assert_envelope_shape(envelope, success=True)
        assert envelope["Data"]["PullRequests"] == []

    def test_search_filter(self, capsys):
        prs = [_pr(5, "Fix auth bug")]
        with patch(
            "get_pull_requests.is_gh_authenticated",
            return_value=True,
        ), patch(
            "get_pull_requests.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_completed(stdout=_prs_json(prs), rc=0),
        ) as mock_run:
            rc = main(["--search", "fix auth", "--output-format", "json"])
        assert rc == 0
        cmd = mock_run.call_args[0][0]
        assert "--search" in cmd
        assert "fix auth" in cmd
        # --search makes gh ignore other filter flags, so we must not pass them
        assert "--state" not in cmd
        assert "--label" not in cmd
        assert "--author" not in cmd
        envelope = _parse_envelope(capsys.readouterr().out)
        _assert_envelope_shape(envelope, success=True)
        assert len(envelope["Data"]["PullRequests"]) == 1

    def test_invalid_limit_returns_envelope_with_error(self, capsys):
        with patch(
            "get_pull_requests.is_gh_authenticated",
            return_value=True,
        ), patch(
            "get_pull_requests.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ):
            rc = main(["--limit", "0", "--output-format", "json"])
        assert rc == 2
        envelope = _parse_envelope(capsys.readouterr().out)
        _assert_envelope_shape(envelope, success=False)
        assert envelope["Error"]["Code"] == 2
        assert envelope["Error"]["Type"] == "InvalidParams"
        assert "Limit must be between 1 and 1000" in envelope["Error"]["Message"]

    # Regression: issue #2312. Stdout was a bare JSON list, not the
    # documented ADR-056 envelope. Lock in the envelope shape.
    def test_issue_2312_output_is_envelope_not_bare_list(self, capsys):
        prs = [_pr(2305, "PR A"), _pr(2274, "PR B")]
        with patch(
            "get_pull_requests.is_gh_authenticated",
            return_value=True,
        ), patch(
            "get_pull_requests.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_completed(stdout=_prs_json(prs), rc=0),
        ):
            rc = main(["--state", "open", "--limit", "5", "--output-format", "json"])
        assert rc == 0
        parsed = _parse_envelope(capsys.readouterr().out)
        # The regression was: parsed used to be a list. Assert it is now a dict
        # with the documented envelope keys.
        assert isinstance(parsed, dict), (
            "issue #2312 regression: stdout must be the ADR-056 envelope, not a bare list"
        )
        _assert_envelope_shape(parsed, success=True)
        assert "PullRequests" in parsed["Data"]

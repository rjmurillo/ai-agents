"""Tests for reopen_pr.py skill script (issue #6529).

Each test drives main(argv) and asserts the exit code. gh is mocked at the
subprocess boundary: a fake dispatches on the argument vector and raises a
named AssertionError for any command it has no response for.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.github_core.api import RepoInfo

_REPO_ROOT = Path(__file__).resolve().parents[1]
_GITHUB_SKILL = _REPO_ROOT / ".claude" / "skills" / "github"
_SCRIPTS_DIR = _GITHUB_SKILL / "scripts" / "pr"


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


script = _import_script("reopen_pr")
main = script.main
build_parser = script.build_parser
# Use the auth types from the library copy the script imported, so enum
# identity checks inside describe_gh_auth_failure hold.
_api = sys.modules["github_core.api"]
GhAuthResult = _api.GhAuthResult
GhAuthStatus = _api.GhAuthStatus

_GH_MISSING_PR = (
    "GraphQL: Could not resolve to a PullRequest with the number of 999999. "
    "(repository.pullRequest)\n"
)
_GH_MISSING_REPO = "GraphQL: Could not resolve to a Repository with the name 'o/r'. (repository)"


def completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


def state_json(state: str) -> str:
    return json.dumps({"state": state})


class FakeGh:
    """Dispatch gh calls on argv. Records every call for later assertions."""

    def __init__(
        self,
        *,
        view: subprocess.CompletedProcess[str] | None = None,
        reopen: subprocess.CompletedProcess[str] | None = None,
    ) -> None:
        self.view = view if view is not None else completed(stdout=state_json("CLOSED"))
        self.reopen = reopen if reopen is not None else completed()
        self.calls: list[list[str]] = []

    def __call__(self, cmd, **kwargs):
        cmd = list(cmd)
        self.calls.append(cmd)
        if cmd[:3] == ["gh", "pr", "view"]:
            return self.view
        if cmd[:3] == ["gh", "pr", "reopen"]:
            return self.reopen
        raise AssertionError(f"unexpected subprocess.run command: {cmd!r}")

    def reopen_calls(self) -> list[list[str]]:
        return [c for c in self.calls if c[:3] == ["gh", "pr", "reopen"]]


def run_main(argv: list[str], fake, *, auth=None, fmt: str = "json"):
    """Run main with gh mocked; return the exit code."""
    auth = auth or GhAuthResult(GhAuthStatus.AUTHENTICATED)
    with (
        patch.object(script, "check_gh_auth", return_value=auth),
        patch.object(
            script,
            "resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ),
        patch("subprocess.run", side_effect=fake),
    ):
        try:
            return main([*argv, "--output-format", fmt])
        except SystemExit as exc:
            return exc.code


def envelope(capsys) -> dict:
    out = capsys.readouterr().out.strip().splitlines()
    assert out, "no envelope on stdout"
    return json.loads(out[-1])


class TestBuildParser:
    def test_pull_request_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([])

    def test_valid_args(self):
        args = build_parser().parse_args(["--pull-request", "50", "--comment", "again"])
        assert args.pull_request == 50
        assert args.comment == "again"

    def test_comment_defaults_empty(self):
        assert build_parser().parse_args(["--pull-request", "50"]).comment == ""


class TestReopen:
    def test_closed_pr_is_reopened(self, capsys):
        fake = FakeGh()
        rc = run_main(["--pull-request", "50"], fake)
        env = envelope(capsys)
        assert rc == 0
        assert env["Data"]["action"] == "reopened"
        assert env["Data"]["state"] == "OPEN"
        assert env["Data"]["pull_request"] == 50
        assert fake.reopen_calls() == [["gh", "pr", "reopen", "50", "--repo", "o/r"]]

    def test_comment_is_passed_to_gh(self, capsys):
        fake = FakeGh()
        rc = run_main(["--pull-request", "50", "--comment", "Re-fire workflows"], fake)
        assert rc == 0
        assert fake.reopen_calls() == [
            ["gh", "pr", "reopen", "50", "--repo", "o/r", "--comment", "Re-fire workflows"]
        ]

    def test_no_comment_flag_without_comment(self):
        fake = FakeGh()
        run_main(["--pull-request", "50"], fake)
        assert "--comment" not in fake.reopen_calls()[0]

    def test_human_output_format(self, capsys):
        rc = run_main(["--pull-request", "50"], FakeGh(), fmt="human")
        assert rc == 0
        assert "Reopened PR #50" in capsys.readouterr().out


class TestIdempotencyAndRefusal:
    def test_open_pr_is_success_without_reopen(self, capsys):
        fake = FakeGh(view=completed(stdout=state_json("OPEN")))
        rc = run_main(["--pull-request", "50"], fake)
        env = envelope(capsys)
        assert rc == 0
        assert env["Data"]["action"] == "none"
        assert env["Data"]["state"] == "OPEN"
        assert fake.reopen_calls() == []

    def test_merged_pr_exits_1_without_reopen(self, capsys):
        fake = FakeGh(view=completed(stdout=state_json("MERGED")))
        rc = run_main(["--pull-request", "50"], fake)
        env = envelope(capsys)
        assert rc == 1
        assert env["Error"]["Type"] == "InvalidParams"
        assert "merged" in env["Error"]["Message"]
        assert fake.reopen_calls() == []

    @pytest.mark.parametrize("body", [json.dumps({}), json.dumps({"state": None})])
    def test_unknown_state_exits_1_without_reopen(self, capsys, body):
        fake = FakeGh(view=completed(stdout=body))
        rc = run_main(["--pull-request", "50"], fake)
        assert rc == 1
        assert "unknown state" in envelope(capsys)["Error"]["Message"]
        assert fake.reopen_calls() == []


class TestAuth:
    def test_auth_preflight_failure_exits_4(self, capsys):
        fake = FakeGh()
        rc = run_main(
            ["--pull-request", "50"],
            fake,
            auth=GhAuthResult(GhAuthStatus.INVALID_CREDENTIALS, "bad token"),
        )
        assert rc == 4
        assert envelope(capsys)["Error"]["Type"] == "AuthError"
        assert fake.calls == []

    def test_reopen_auth_failure_exits_4(self, capsys):
        fake = FakeGh(reopen=completed(stderr="gh: Bad credentials (HTTP 401)", rc=1))
        rc = run_main(["--pull-request", "50"], fake)
        assert rc == 4
        assert envelope(capsys)["Error"]["Type"] == "AuthError"


class TestLookupFailures:
    @pytest.mark.parametrize(
        ("stdout", "stderr", "code"),
        [
            pytest.param("", _GH_MISSING_PR, 2, id="gh-missing-pr"),
            pytest.param(_GH_MISSING_PR, "", 2, id="marker-on-stdout-fallback"),
            pytest.param("", "gh: Not Found (HTTP 404)", 2, id="legacy-any-case"),
            pytest.param("", "HTTP 403: Resource not accessible by integration", 4, id="auth"),
            pytest.param("", "HTTP 502: Bad Gateway", 3, id="external-error"),
            pytest.param("", _GH_MISSING_REPO, 3, id="missing-repo"),
            pytest.param(
                "", "Post https://api.github.com: Could not resolve host", 3, id="transport-fault"
            ),
        ],
    )
    def test_failed_pr_view_exit_code(self, stdout, stderr, code):
        """A failed PR lookup maps to the ADR-035 code and never reopens the PR."""
        fake = FakeGh(view=completed(rc=1, stdout=stdout, stderr=stderr))
        rc = run_main(["--pull-request", "999999"], fake)
        assert rc == code
        assert fake.reopen_calls() == []

    @pytest.mark.parametrize("body", ["not json", "[1, 2]"])
    def test_unparseable_pr_state_exits_3(self, capsys, body):
        fake = FakeGh(view=completed(stdout=body))
        rc = run_main(["--pull-request", "50"], fake)
        assert rc == 3
        assert envelope(capsys)["Error"]["Type"] == "ApiError"
        assert fake.reopen_calls() == []


class TestReopenFailures:
    def test_reopen_failure_exits_3(self, capsys):
        fake = FakeGh(reopen=completed(stderr="head branch was deleted", rc=1))
        rc = run_main(["--pull-request", "50"], fake)
        env = envelope(capsys)
        assert rc == 3
        assert env["Error"]["Type"] == "ApiError"
        assert "head branch was deleted" in env["Error"]["Message"]

    def test_reopen_not_found_exits_2(self, capsys):
        fake = FakeGh(reopen=completed(stderr=_GH_MISSING_PR, rc=1))
        rc = run_main(["--pull-request", "50"], fake)
        assert rc == 2
        assert envelope(capsys)["Error"]["Type"] == "NotFound"

    @pytest.mark.parametrize("hung", ["view", "reopen"])
    def test_gh_timeout_exits_3(self, capsys, hung):
        """A hung gh call becomes an exit-3 Timeout envelope."""
        fake = FakeGh()

        def _hangs(cmd, **kwargs):
            if cmd[2] == hung:
                raise subprocess.TimeoutExpired(cmd, 30)
            return fake(cmd, **kwargs)

        rc = run_main(["--pull-request", "50"], _hangs)
        assert rc == 3
        assert envelope(capsys)["Error"]["Type"] == "Timeout"


class TestDocs:
    def test_skill_md_documents_the_script(self):
        text = (_GITHUB_SKILL / "SKILL.md").read_text(encoding="utf-8")
        row = next(line for line in text.splitlines() if "`reopen_pr.py`" in line)
        assert "--pull-request" in row
        assert "--comment" in row
        assert "exit 1" in row

    def test_fix_ci_recovery_uses_the_script(self):
        text = (_GITHUB_SKILL / "fix-ci.md").read_text(encoding="utf-8")
        assert "pr/reopen_pr.py" in text
        assert "no PR reopen script" not in text
        assert "from the GitHub UI" not in text

"""Tests for update_pr_branch.py skill script.

Each test drives main(argv) and asserts the exit code. HTTP is mocked at the
subprocess boundary: a fake dispatches on the gh argument vector and raises a
named AssertionError for any command it has no response for. AC numbers refer
to the acceptance criteria in the PR body.
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

_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1]
    / ".claude" / "skills" / "github" / "scripts" / "pr"
)
_SKILL_MD = Path(__file__).resolve().parents[1] / ".claude" / "skills" / "github" / "SKILL.md"


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("update_pr_branch")
main = _mod.main
# Use the auth types from the library copy the script imported, so enum
# identity checks inside describe_gh_auth_failure hold.
_api = sys.modules["github_core.api"]
GhAuthResult = _api.GhAuthResult
GhAuthStatus = _api.GhAuthStatus

_OLD_HEAD = "a" * 40
_NEW_HEAD = "b" * 40
_OTHER_HEAD = "c" * 40
_PUT_ENDPOINT = "repos/o/r/pulls/50/update-branch"
_ACCEPTED_BODY = json.dumps({
    "message": "Updating pull request branch.",
    "url": "https://github.com/o/r/pull/50",
})
_HEAD_MOVED_BODY = json.dumps({
    "message": "expected head sha didn't match current head ref.",
    "documentation_url": "https://docs.github.com/rest",
    "status": "422",
})


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


def _pr_json(state: str = "OPEN", head: str = _OLD_HEAD) -> str:
    return json.dumps({"state": state, "headRefOid": head, "baseRefName": "main"})


class _FakeGh:
    """Dispatch gh calls on argv. Records every call for later assertions."""

    def __init__(
        self,
        *,
        pr_views: list[str] | None = None,
        behind: list[str] | None = None,
        put: subprocess.CompletedProcess[str] | None = None,
    ) -> None:
        self.pr_views = list(pr_views or [_pr_json()])
        self.behind = list(behind or ["3"])
        self.put = put if put is not None else _completed(stdout=_ACCEPTED_BODY)
        self.calls: list[list[str]] = []

    def _next(self, queue: list):
        return queue.pop(0) if len(queue) > 1 else queue[0]

    def __call__(self, cmd, **kwargs):
        cmd = list(cmd)
        self.calls.append(cmd)
        if cmd[:3] == ["gh", "pr", "view"]:
            return _completed(stdout=self._next(self.pr_views))
        if cmd[:2] == ["gh", "api"] and "/compare/" in cmd[2]:
            return _completed(stdout=self._next(self.behind))
        if cmd[:4] == ["gh", "api", "-X", "PUT"]:
            assert cmd[4] == _PUT_ENDPOINT, cmd
            return self.put
        raise AssertionError(f"unexpected subprocess.run command: {cmd!r}")

    def put_calls(self) -> list[list[str]]:
        return [c for c in self.calls if c[:4] == ["gh", "api", "-X", "PUT"]]


def _run(argv: list[str], fake: _FakeGh, *, auth: GhAuthResult | None = None):
    """Run main with gh mocked; return (exit code, parsed envelope)."""
    auth = auth or GhAuthResult(GhAuthStatus.AUTHENTICATED)
    with patch.object(_mod, "check_gh_auth", return_value=auth), patch.object(
        _mod, "resolve_repo_params", return_value=RepoInfo(owner="o", repo="r"),
    ), patch("subprocess.run", side_effect=fake):
        try:
            rc = main([*argv, "--output-format", "json"])
        except SystemExit as exc:
            rc = exc.code
    return rc


def _envelope(capsys) -> dict:
    out = capsys.readouterr().out.strip().splitlines()
    assert out, "no envelope on stdout"
    return json.loads(out[-1])


def _assert_expected_sha_forwarded(put_calls: list[list[str]], sha: str) -> None:
    assert len(put_calls) == 1, put_calls
    assert f"expected_head_sha={sha}" in put_calls[0], put_calls[0]


class _FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class TestUpdateRequested:
    def test_update_without_wait_returns_old_head_and_message(self, capsys):
        """AC1: 202 returns exit 0 with old head and API message."""
        fake = _FakeGh()
        rc = _run(["--pull-request", "50"], fake)
        env = _envelope(capsys)
        assert rc == 0
        assert env["Success"] is True
        data = env["Data"]
        assert data["action"] == "update_requested"
        assert data["already_up_to_date"] is False
        assert data["old_head_sha"] == _OLD_HEAD
        assert data["new_head_sha"] is None
        assert data["message"] == "Updating pull request branch."
        assert data["behind_by"] == 3
        assert len(fake.put_calls()) == 1

    def test_expected_head_sha_is_forwarded(self, capsys):
        """AC2: --expected-head-sha reaches the PUT body."""
        fake = _FakeGh()
        rc = _run(["--pull-request", "50", "--expected-head-sha", _OLD_HEAD], fake)
        assert rc == 0
        _assert_expected_sha_forwarded(fake.put_calls(), _OLD_HEAD)
        assert _envelope(capsys)["Data"]["expected_head_sha"] == _OLD_HEAD

    def test_negative_control_unforwarded_sha_fails_the_forwarding_check(self, capsys):
        """AC2 negative control: drop the SHA from the PUT and the check goes red."""
        original = _mod._build_update_args

        def _drops_sha(pr, repo_flag, expected_head_sha):
            return original(pr, repo_flag, "")

        fake = _FakeGh()
        with patch.object(_mod, "_build_update_args", side_effect=_drops_sha):
            rc = _run(["--pull-request", "50", "--expected-head-sha", _OLD_HEAD], fake)
        assert rc == 0
        assert fake.put_calls(), "PUT never ran, so the control proves nothing"
        with pytest.raises(AssertionError):
            _assert_expected_sha_forwarded(fake.put_calls(), _OLD_HEAD)

    def test_no_expected_sha_sends_no_body_field(self, capsys):
        """AC2: without the flag, no expected_head_sha field is sent."""
        fake = _FakeGh()
        assert _run(["--pull-request", "50"], fake) == 0
        assert not any("expected_head_sha" in arg for arg in fake.put_calls()[0])


class TestHeadMoved:
    def test_422_head_moved_exits_1_typed(self, capsys):
        """AC3: GitHub 422 on a moved head maps to exit 1 VerificationFailed."""
        fake = _FakeGh(put=_completed(
            stdout=_HEAD_MOVED_BODY,
            stderr="gh: expected head sha didn't match current head ref. (HTTP 422)",
            rc=1,
        ))
        rc = _run(["--pull-request", "50", "--expected-head-sha", _OTHER_HEAD], fake)
        env = _envelope(capsys)
        assert rc == 1
        assert env["Success"] is False
        assert env["Error"]["Type"] == "VerificationFailed"
        assert env["Data"]["reason"] == "head_moved"
        assert env["Data"]["expected_head_sha"] == _OTHER_HEAD
        assert env["Data"]["current_head_sha"] == _OLD_HEAD

    def test_other_422_exits_3(self, capsys):
        """AC9: a 422 that is neither head-moved nor up-to-date is external."""
        fake = _FakeGh(put=_completed(
            stdout=json.dumps({"message": "merge conflict between base and head"}),
            stderr="gh: merge conflict between base and head (HTTP 422)",
            rc=1,
        ))
        rc = _run(["--pull-request", "50"], fake)
        env = _envelope(capsys)
        assert rc == 3
        assert env["Error"]["Type"] == "ApiError"
        assert "merge conflict" in env["Error"]["Message"]


class TestRefusedStates:
    @pytest.mark.parametrize("state", ["CLOSED", "MERGED"])
    def test_closed_or_merged_pr_exits_1_without_put(self, capsys, state):
        """AC4: closed and merged PRs are refused before any mutation."""
        fake = _FakeGh(pr_views=[_pr_json(state=state)])
        rc = _run(["--pull-request", "50"], fake)
        env = _envelope(capsys)
        assert rc == 1
        assert env["Error"]["Type"] == "InvalidParams"
        assert state.lower() in env["Error"]["Message"]
        assert fake.put_calls() == []

    def test_invalid_sha_exits_1_before_any_call(self, capsys):
        """AC10: a malformed SHA fails before auth or API work."""
        fake = _FakeGh()
        rc = _run(["--pull-request", "50", "--expected-head-sha", "abc"], fake)
        assert rc == 1
        assert _envelope(capsys)["Error"]["Type"] == "InvalidParams"
        assert fake.calls == []

    def test_timeout_without_wait_exits_1(self, capsys):
        """--timeout-seconds only means something with --wait."""
        fake = _FakeGh()
        rc = _run(["--pull-request", "50", "--timeout-seconds", "10"], fake)
        assert rc == 1
        assert fake.calls == []

    def test_pr_not_found_exits_2(self, capsys):
        """AC9: GraphQL's could-not-resolve text maps to not found."""
        def _missing(cmd, **kwargs):
            return _completed(
                stderr="GraphQL: Could not resolve to a PullRequest with the number of 50.",
                rc=1,
            )

        rc = _run(["--pull-request", "50"], _missing)
        assert rc == 2
        assert _envelope(capsys)["Error"]["Type"] == "NotFound"


class TestAlreadyUpToDate:
    def test_behind_by_zero_is_success_without_put(self, capsys):
        """AC5: compare reports 0 behind, so no PUT and a clear field."""
        fake = _FakeGh(behind=["0"])
        rc = _run(["--pull-request", "50"], fake)
        env = _envelope(capsys)
        assert rc == 0
        assert env["Data"]["already_up_to_date"] is True
        assert env["Data"]["action"] == "none"
        assert env["Data"]["new_head_sha"] == _OLD_HEAD
        assert fake.put_calls() == []

    def test_422_no_new_commits_race_is_success(self, capsys):
        """AC5: the base caught up between compare and PUT."""
        fake = _FakeGh(put=_completed(
            stdout=json.dumps({"message": "There are no new commits on the base branch."}),
            stderr="gh: There are no new commits on the base branch. (HTTP 422)",
            rc=1,
        ))
        rc = _run(["--pull-request", "50"], fake)
        env = _envelope(capsys)
        assert rc == 0
        assert env["Data"]["already_up_to_date"] is True

    def test_compare_failure_still_attempts_update_and_says_so(self, capsys):
        """A compare failure is reported in precheck, and GitHub adjudicates."""
        fake = _FakeGh(behind=["not-a-number"])
        rc = _run(["--pull-request", "50"], fake)
        env = _envelope(capsys)
        assert rc == 0
        assert env["Data"]["behind_by"] is None
        assert env["Data"]["precheck"].startswith("unavailable")
        assert len(fake.put_calls()) == 1


class TestAuth:
    def test_auth_preflight_failure_exits_4(self, capsys):
        """AC6: invalid credentials exit 4 with an AuthError envelope."""
        fake = _FakeGh()
        rc = _run(
            ["--pull-request", "50"],
            fake,
            auth=GhAuthResult(GhAuthStatus.INVALID_CREDENTIALS, "bad token"),
        )
        assert rc == 4
        assert _envelope(capsys)["Error"]["Type"] == "AuthError"
        assert fake.calls == []

    def test_put_auth_failure_exits_4(self, capsys):
        """AC6: a 401 on the PUT itself exits 4."""
        fake = _FakeGh(put=_completed(stderr="gh: Bad credentials (HTTP 401)", rc=1))
        rc = _run(["--pull-request", "50"], fake)
        assert rc == 4
        assert _envelope(capsys)["Error"]["Type"] == "AuthError"


class TestWait:
    def test_wait_reports_new_head(self, capsys):
        """AC7: poll until the head changes, then report it."""
        clock = _FakeClock()
        fake = _FakeGh(
            pr_views=[_pr_json(), _pr_json(), _pr_json(head=_NEW_HEAD)],
            behind=["2"],
        )
        with patch.object(_mod, "_monotonic", clock.monotonic), patch.object(
            _mod, "_sleep", clock.sleep,
        ):
            rc = _run(["--pull-request", "50", "--wait", "--timeout-seconds", "60"], fake)
        env = _envelope(capsys)
        assert rc == 0
        assert env["Data"]["action"] == "updated"
        assert env["Data"]["old_head_sha"] == _OLD_HEAD
        assert env["Data"]["new_head_sha"] == _NEW_HEAD
        assert clock.sleeps, "expected at least one poll interval"

    def test_wait_stops_when_no_longer_behind(self, capsys):
        """AC7: compare reaching 0 also ends the wait."""
        clock = _FakeClock()
        fake = _FakeGh(behind=["2", "2", "0"])
        with patch.object(_mod, "_monotonic", clock.monotonic), patch.object(
            _mod, "_sleep", clock.sleep,
        ):
            rc = _run(["--pull-request", "50", "--wait", "--timeout-seconds", "60"], fake)
        env = _envelope(capsys)
        assert rc == 0
        assert env["Data"]["wait_result"] == "not_behind"

    def test_wait_timeout_exits_3(self, capsys):
        """AC8: the head never moves, so the bounded wait exits 3 Timeout."""
        clock = _FakeClock()
        fake = _FakeGh(behind=["2"])
        with patch.object(_mod, "_monotonic", clock.monotonic), patch.object(
            _mod, "_sleep", clock.sleep,
        ):
            rc = _run(["--pull-request", "50", "--wait", "--timeout-seconds", "12"], fake)
        env = _envelope(capsys)
        assert rc == 3
        assert env["Error"]["Type"] == "Timeout"
        assert env["Data"]["old_head_sha"] == _OLD_HEAD
        assert env["Data"]["update_requested"] is True
        assert clock.now <= 12


class TestSkillDoc:
    def test_skill_md_documents_the_script(self):
        """The github SKILL.md names the script and its exit codes."""
        text = _SKILL_MD.read_text(encoding="utf-8")
        row = next(line for line in text.splitlines() if "`update_pr_branch.py`" in line)
        assert "--expected-head-sha" in row
        assert "--wait" in row
        for code in ("Exit 0", "exit 1", "exit 3", "exit 4"):
            assert code in row, code


class TestErrorPaths:
    def test_gh_timeout_exits_3(self, capsys):
        """AC9: a hung gh call becomes an exit-3 Timeout envelope."""
        def _hangs(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd, 30)

        rc = _run(["--pull-request", "50"], _hangs)
        assert rc == 3
        assert _envelope(capsys)["Error"]["Type"] == "Timeout"

    @pytest.mark.parametrize("body", ["not json", "[1, 2]"])
    def test_unparseable_pr_state_exits_3(self, capsys, body):
        """AC9: a PR view that is not a JSON object is an external failure."""
        fake = _FakeGh(pr_views=[body])
        rc = _run(["--pull-request", "50"], fake)
        assert rc == 3
        assert _envelope(capsys)["Error"]["Type"] == "ApiError"
        assert fake.put_calls() == []

    @pytest.mark.parametrize(
        ("stderr", "code", "error_type"),
        [
            ("HTTP 403: Resource not accessible by integration", 4, "AuthError"),
            ("HTTP 502: Bad Gateway", 3, "ApiError"),
        ],
    )
    def test_pr_lookup_failure_maps_exit_code(self, capsys, stderr, code, error_type):
        """AC6, AC9: lookup failures split into auth (4) and external (3)."""
        def _fails(cmd, **kwargs):
            return _completed(stderr=stderr, rc=1)

        rc = _run(["--pull-request", "50"], _fails)
        assert rc == code
        assert _envelope(capsys)["Error"]["Type"] == error_type

    def test_missing_head_skips_compare_and_reports_precheck(self, capsys):
        """No head SHA means no compare call; GitHub still adjudicates."""
        fake = _FakeGh(pr_views=[_pr_json(head="")])
        rc = _run(["--pull-request", "50"], fake)
        env = _envelope(capsys)
        assert rc == 0
        assert env["Data"]["precheck"] == "unavailable: PR head SHA or base ref missing"
        assert not any("/compare/" in " ".join(c) for c in fake.calls)

    def test_non_object_api_body_gives_empty_message(self, capsys):
        """A 202 body that is not an object yields an empty message, not a crash."""
        fake = _FakeGh(put=_completed(stdout="[]"))
        rc = _run(["--pull-request", "50"], fake)
        assert rc == 0
        assert _envelope(capsys)["Data"]["message"] == ""

    def test_nonpositive_timeout_exits_1(self, capsys):
        """A zero wait bound is refused before any call."""
        fake = _FakeGh()
        rc = _run(["--pull-request", "50", "--wait", "--timeout-seconds", "0"], fake)
        assert rc == 1
        assert fake.calls == []

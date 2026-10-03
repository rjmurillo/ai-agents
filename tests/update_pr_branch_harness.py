"""Shared import and fakes for the update_pr_branch.py skill script tests.

Each test drives main(argv) and asserts the exit code. HTTP is mocked at the
subprocess boundary: a fake dispatches on the gh argument vector and raises a
named AssertionError for any command it has no response for. Split out so the
core and --wait test modules share one fake instead of copying it.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

from scripts.github_core.api import RepoInfo

_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1]
    / ".claude" / "skills" / "github" / "scripts" / "pr"
)
SKILL_MD = Path(__file__).resolve().parents[1] / ".claude" / "skills" / "github" / "SKILL.md"


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


script = _import_script("update_pr_branch")
main = script.main
# Use the auth types from the library copy the script imported, so enum
# identity checks inside describe_gh_auth_failure hold.
_api = sys.modules["github_core.api"]
GhAuthResult = _api.GhAuthResult
GhAuthStatus = _api.GhAuthStatus

OLD_HEAD = "a" * 40
NEW_HEAD = "b" * 40
OTHER_HEAD = "c" * 40
_PUT_ENDPOINT = "repos/o/r/pulls/50/update-branch"
_ACCEPTED_BODY = json.dumps({
    "message": "Updating pull request branch.",
    "url": "https://github.com/o/r/pull/50",
})
# Bodies captured live from GitHub on 2026-10-03 against PR #6139. Note the
# curly apostrophe in the head-moved message.
HEAD_MOVED_MESSAGE = "expected head sha didn\u2019t match current head ref."
HEAD_MOVED_BODY = json.dumps(
    {"message": HEAD_MOVED_MESSAGE, "status": "422"}, ensure_ascii=False,
)


def completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


def pr_json(state: str = "OPEN", head: str = OLD_HEAD) -> str:
    return json.dumps({"state": state, "headRefOid": head, "baseRefName": "main"})


class FakeGh:
    """Dispatch gh calls on argv. Records every call for later assertions."""

    def __init__(
        self,
        *,
        pr_views: list[str] | None = None,
        behind: list[str] | None = None,
        put: subprocess.CompletedProcess[str] | None = None,
    ) -> None:
        self.pr_views = list(pr_views or [pr_json()])
        self.behind = list(behind or ["3"])
        self.put = put if put is not None else completed(stdout=_ACCEPTED_BODY)
        self.calls: list[list[str]] = []

    def _next(self, queue: list):  # The last response repeats.
        return queue.pop(0) if len(queue) > 1 else queue[0]

    def __call__(self, cmd, **kwargs):
        cmd = list(cmd)
        self.calls.append(cmd)
        if cmd[:3] == ["gh", "pr", "view"]:
            return completed(stdout=self._next(self.pr_views))
        if cmd[:2] == ["gh", "api"] and "/compare/" in cmd[2]:
            return completed(stdout=self._next(self.behind))
        if cmd[:4] == ["gh", "api", "-X", "PUT"]:
            assert cmd[4] == _PUT_ENDPOINT, cmd
            return self.put
        raise AssertionError(f"unexpected subprocess.run command: {cmd!r}")

    def put_calls(self) -> list[list[str]]:
        return [c for c in self.calls if c[:4] == ["gh", "api", "-X", "PUT"]]


def run_main(argv: list[str], fake: Any, *, auth: Any = None):
    """Run main with gh mocked; return (exit code, parsed envelope)."""
    auth = auth or GhAuthResult(GhAuthStatus.AUTHENTICATED)
    with patch.object(script, "check_gh_auth", return_value=auth), patch.object(
        script, "resolve_repo_params", return_value=RepoInfo(owner="o", repo="r"),
    ), patch("subprocess.run", side_effect=fake):
        try:
            rc = main([*argv, "--output-format", "json"])
        except SystemExit as exc:
            rc = exc.code
    return rc


def envelope(capsys) -> dict:
    out = capsys.readouterr().out.strip().splitlines()
    assert out, "no envelope on stdout"
    return json.loads(out[-1])


def assert_expected_sha_forwarded(put_calls: list[list[str]], sha: str) -> None:
    assert len(put_calls) == 1, put_calls
    assert f"expected_head_sha={sha}" in put_calls[0], put_calls[0]


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

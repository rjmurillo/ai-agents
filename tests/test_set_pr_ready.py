"""Tests for set_pr_ready.py: mutation, idempotence, dry run, and the ADR-035 exit codes.

All gh I/O is mocked at the subprocess boundary. A fake dispatches on the gh
argument vector and fails loudly for any command it has no response for.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from scripts.github_core.api import RepoInfo

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS_DIR = _REPO_ROOT / ".claude" / "skills" / "github" / "scripts" / "pr"
SKILL_MD = _REPO_ROOT / ".claude" / "skills" / "github" / "SKILL.md"


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


script = _import_script("set_pr_ready")
# Use the auth types from the library copy the script imported, so enum
# identity checks inside describe_gh_auth_failure hold.
_api = sys.modules["github_core.api"]
GhAuthResult = _api.GhAuthResult
GhAuthStatus = _api.GhAuthStatus

HEAD = "a" * 40
OTHER_HEAD = "c" * 40


def completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


def pr_json(state: str = "OPEN", is_draft: bool = True, head: str = HEAD) -> str:
    return json.dumps({"state": state, "isDraft": is_draft, "headRefOid": head})


class FakeGh:
    """Dispatch gh calls on argv. Records every call for later assertions.

    ``views`` is consumed one entry per ``gh pr view``; the last entry repeats.
    """

    def __init__(self, views: list[Any] | None = None, ready: Any = None):
        self.views = views or [pr_json()]
        self.ready = ready if ready is not None else completed()
        self.calls: list[list[str]] = []
        self._view_index = 0

    def __call__(self, cmd, **kwargs):
        self.calls.append(list(cmd))
        if cmd[:3] == ["gh", "pr", "view"]:
            entry = self.views[min(self._view_index, len(self.views) - 1)]
            self._view_index += 1
            return entry if not isinstance(entry, str) else completed(stdout=entry)
        if cmd[:3] == ["gh", "pr", "ready"]:
            return self.ready
        raise AssertionError(f"unexpected gh call: {cmd}")

    def ready_calls(self) -> list[list[str]]:
        return [c for c in self.calls if c[:3] == ["gh", "pr", "ready"]]


def run_main(argv: list[str], fake: Any, *, auth: Any = None) -> int:
    auth = auth or GhAuthResult(GhAuthStatus.AUTHENTICATED)
    with (
        patch.object(script, "check_gh_auth", return_value=auth),
        patch.object(script, "resolve_repo_params", return_value=RepoInfo(owner="o", repo="r")),
        patch("subprocess.run", side_effect=fake),
    ):
        try:
            return script.main([*argv, "--output-format", "json"])
        except SystemExit as exc:
            assert isinstance(exc.code, int), exc.code
            return exc.code


def envelope(capsys) -> dict:
    out = capsys.readouterr().out.strip().splitlines()
    assert out, "no envelope on stdout"
    return json.loads(out[-1])


class TestMarkReady:
    def test_marks_draft_pr_ready_and_reads_back(self, capsys):
        fake = FakeGh(views=[pr_json(is_draft=True), pr_json(is_draft=False)])
        rc = run_main(["--pull-request", "7"], fake)
        env = envelope(capsys)
        assert rc == 0
        assert env["Success"] is True
        assert env["Data"]["action"] == "marked_ready"
        assert env["Data"]["is_draft"] is False
        assert env["Data"]["head_sha"] == HEAD
        assert fake.ready_calls() == [["gh", "pr", "ready", "7", "--repo", "o/r"]]

    def test_already_ready_is_a_noop_success(self, capsys):
        fake = FakeGh(views=[pr_json(is_draft=False)])
        rc = run_main(["--pull-request", "7"], fake)
        env = envelope(capsys)
        assert rc == 0
        assert env["Data"]["action"] == "none"
        assert fake.ready_calls() == []

    def test_expected_head_sha_matching_proceeds(self, capsys):
        fake = FakeGh(views=[pr_json(is_draft=True), pr_json(is_draft=False)])
        rc = run_main(["--pull-request", "7", "--expected-head-sha", HEAD.upper()], fake)
        env = envelope(capsys)
        assert rc == 0
        assert env["Data"]["expected_head_sha"] == HEAD.upper()
        assert len(fake.ready_calls()) == 1


class TestConvertToDraft:
    def test_draft_flag_passes_undo_and_converts(self, capsys):
        fake = FakeGh(views=[pr_json(is_draft=False), pr_json(is_draft=True)])
        rc = run_main(["--pull-request", "7", "--draft"], fake)
        env = envelope(capsys)
        assert rc == 0
        assert env["Data"]["action"] == "converted_to_draft"
        assert env["Data"]["is_draft"] is True
        assert fake.ready_calls() == [["gh", "pr", "ready", "7", "--repo", "o/r", "--undo"]]

    def test_already_draft_is_a_noop_success(self, capsys):
        fake = FakeGh(views=[pr_json(is_draft=True)])
        rc = run_main(["--pull-request", "7", "--draft"], fake)
        assert rc == 0
        assert envelope(capsys)["Data"]["action"] == "none"
        assert fake.ready_calls() == []


class TestDryRun:
    def test_dry_run_reports_plan_and_mutates_nothing(self, capsys):
        fake = FakeGh(views=[pr_json(is_draft=True)])
        rc = run_main(["--pull-request", "7", "--dry-run"], fake)
        data = envelope(capsys)["Data"]
        assert rc == 0
        assert data["action"] == "would_mark_ready"
        assert data["dry_run"] is True
        assert fake.ready_calls() == []

    def test_dry_run_draft_reports_plan(self, capsys):
        fake = FakeGh(views=[pr_json(is_draft=False)])
        rc = run_main(["--pull-request", "7", "--draft", "--dry-run"], fake)
        data = envelope(capsys)["Data"]
        assert rc == 0
        assert data["action"] == "would_convert_to_draft"
        assert fake.ready_calls() == []

    def test_dry_run_on_matching_state_reports_noop(self, capsys):
        fake = FakeGh(views=[pr_json(is_draft=False)])
        rc = run_main(["--pull-request", "7", "--dry-run"], fake)
        data = envelope(capsys)["Data"]
        assert rc == 0
        assert data["action"] == "none"
        assert data["dry_run"] is True

    def test_dry_run_still_refuses_a_moved_head(self, capsys):
        fake = FakeGh(views=[pr_json(is_draft=True)])
        rc = run_main(["--pull-request", "7", "--dry-run", "--expected-head-sha", OTHER_HEAD], fake)
        assert rc == 1
        assert envelope(capsys)["Data"]["reason"] == "head_moved"


class TestExitCodeContract:
    """One test per ADR-035 code the SKILL.md row documents."""

    def test_exit_0_on_success(self):
        fake = FakeGh(views=[pr_json(is_draft=True), pr_json(is_draft=False)])
        assert run_main(["--pull-request", "7"], fake) == 0

    @pytest.mark.parametrize("state", ["CLOSED", "MERGED"])
    def test_exit_1_when_pr_not_open(self, capsys, state):
        fake = FakeGh(views=[pr_json(state=state)])
        rc = run_main(["--pull-request", "7"], fake)
        env = envelope(capsys)
        assert rc == 1
        assert env["Success"] is False
        assert env["Error"]["Type"] == "InvalidParams"
        assert env["Data"]["state"] == state
        assert fake.ready_calls() == []

    def test_exit_1_when_head_differs_from_pin(self, capsys):
        fake = FakeGh(views=[pr_json(is_draft=True)])
        rc = run_main(["--pull-request", "7", "--expected-head-sha", OTHER_HEAD], fake)
        env = envelope(capsys)
        assert rc == 1
        assert env["Error"]["Type"] == "VerificationFailed"
        assert env["Data"]["reason"] == "head_moved"
        assert env["Data"]["current_head_sha"] == HEAD
        assert fake.ready_calls() == []

    @pytest.mark.parametrize("sha", ["abc", "g" * 40, "a" * 39])
    def test_exit_1_on_malformed_sha(self, capsys, sha):
        fake = FakeGh()
        rc = run_main(["--pull-request", "7", "--expected-head-sha", sha], fake)
        assert rc == 1
        assert envelope(capsys)["Error"]["Type"] == "InvalidParams"
        assert fake.calls == []

    def test_exit_2_when_pr_not_found_on_read(self, capsys):
        fake = FakeGh(views=[completed(stderr="GraphQL: Could not resolve to a PullRequest", rc=1)])
        rc = run_main(["--pull-request", "7"], fake)
        assert rc == 2
        assert envelope(capsys)["Error"]["Type"] == "NotFound"

    def test_exit_2_when_pr_not_found_on_mutation(self, capsys):
        fake = FakeGh(ready=completed(stderr="GraphQL: Could not resolve to a PullRequest", rc=1))
        rc = run_main(["--pull-request", "7"], fake)
        assert rc == 2
        assert envelope(capsys)["Error"]["Type"] == "NotFound"

    def test_exit_3_on_mutation_failure(self, capsys):
        fake = FakeGh(ready=completed(stderr="HTTP 502 bad gateway", rc=1))
        rc = run_main(["--pull-request", "7"], fake)
        env = envelope(capsys)
        assert rc == 3
        assert env["Error"]["Type"] == "ApiError"
        assert len(fake.ready_calls()) == 1

    def test_exit_3_on_read_failure(self, capsys):
        fake = FakeGh(views=[completed(stderr="HTTP 500", rc=1)])
        rc = run_main(["--pull-request", "7"], fake)
        assert rc == 3
        assert envelope(capsys)["Error"]["Type"] == "ApiError"

    def test_exit_3_when_readback_shows_no_change(self, capsys):
        fake = FakeGh(views=[pr_json(is_draft=True), pr_json(is_draft=True)])
        rc = run_main(["--pull-request", "7"], fake)
        env = envelope(capsys)
        assert rc == 3
        assert "outcome unverified" in env["Error"]["Message"]
        assert env["Data"]["is_draft"] is True

    def test_exit_3_on_gh_timeout(self, capsys):
        def _hangs(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd, 30)

        rc = run_main(["--pull-request", "7"], _hangs)
        assert rc == 3
        assert envelope(capsys)["Error"]["Type"] == "Timeout"

    @pytest.mark.parametrize("body", ["not json", "[1, 2]", json.dumps({"state": "OPEN"})])
    def test_exit_3_on_unusable_state_response(self, capsys, body):
        fake = FakeGh(views=[body])
        rc = run_main(["--pull-request", "7"], fake)
        assert rc == 3
        assert envelope(capsys)["Error"]["Type"] == "ApiError"

    def test_exit_4_when_gh_unauthenticated(self, capsys):
        fake = FakeGh()
        rc = run_main(
            ["--pull-request", "7"],
            fake,
            auth=GhAuthResult(GhAuthStatus.INVALID_CREDENTIALS, "bad token"),
        )
        assert rc == 4
        assert fake.calls == []

    def test_exit_4_on_auth_failure_text_from_mutation(self, capsys):
        fake = FakeGh(ready=completed(stderr="HTTP 401: Bad credentials", rc=1))
        rc = run_main(["--pull-request", "7"], fake)
        assert rc == 4
        assert envelope(capsys)["Error"]["Type"] == "AuthError"


class TestSkillDocumentation:
    def test_skill_md_documents_the_script_and_its_exit_codes(self):
        text = SKILL_MD.read_text(encoding="utf-8")
        row = next(line for line in text.splitlines() if "`set_pr_ready.py`" in line)
        for flag in ("--pull-request", "--expected-head-sha", "--draft", "--dry-run"):
            assert flag in row, flag
        assert re.search(r"Exit 0 [^;]+; 1 [^;]+; 2 [^;]+; 3 [^;]+; 4 ", row), row
        assert "head_moved" in row

    def test_skill_md_decision_tree_names_the_script(self):
        text = SKILL_MD.read_text(encoding="utf-8")
        assert "→ set_pr_ready.py" in text

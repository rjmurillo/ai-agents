"""Advisory hook jobs report every non-pass path as a typed result line (issue #5636).

An advisory job returns 0 whatever it found, so its exit code cannot say whether
it found something, could not run, or was switched off. Each job now prints one
``[STATE] job reason=code scope=...`` line on stderr for those paths, and stays
silent on a clean run. The exit code of every path is unchanged and asserted
here, next to the line, because that is the invariant a visibility change must
not break.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from scripts.validation import git_hook_policy as policy

_LINE = re.compile(r"^\[(?P<state>[A-Z]+)\] (?P<job>\S+) reason=(?P<reason>\S+)", re.MULTILINE)


def _proc(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


def _typed(capsys: pytest.CaptureFixture[str]) -> list[tuple[str, str, str]]:
    err = capsys.readouterr().err
    return [(m["state"], m["job"], m["reason"]) for m in _LINE.finditer(err)]


def _dispatch(table: dict[str, object]) -> Callable[..., subprocess.CompletedProcess[str]]:
    """Answer ``_run_command`` by the first matching argv token, never by call order."""

    def run(args: Sequence[str], *_a: object, **_k: object) -> subprocess.CompletedProcess[str]:
        for token, result in table.items():
            if token in args:
                if isinstance(result, BaseException):
                    raise result
                return result  # type: ignore[return-value]
        raise AssertionError(f"unexpected command {list(args)}")

    return run


class TestYamllint:
    def test_the_env_toggle_is_a_typed_skip(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("SKIP_YAMLLINT", "1")

        assert policy.run_yamllint(["a.yml"], tmp_path) == 0
        assert _typed(capsys) == [("SKIP", "yaml-advisory", "policy.env_bypass")]

    def test_a_missing_binary_is_a_typed_blocked(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.delenv("SKIP_YAMLLINT", raising=False)
        monkeypatch.setattr(policy, "_run_command", _dispatch({"yamllint": FileNotFoundError()}))

        assert policy.run_yamllint(["a.yml"], tmp_path) == 0
        assert _typed(capsys) == [("BLOCKED", "yaml-advisory", "tool.absent")]

    def test_findings_are_a_typed_fail_and_still_exit_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.delenv("SKIP_YAMLLINT", raising=False)
        monkeypatch.setattr(policy, "_run_command", _dispatch({"yamllint": _proc(1, "a.yml:1")}))

        assert policy.run_yamllint(["a.yml"], tmp_path) == 0
        assert _typed(capsys) == [("FAIL", "yaml-advisory", "advisory.findings")]

    def test_a_clean_run_and_an_empty_path_list_are_silent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.delenv("SKIP_YAMLLINT", raising=False)
        monkeypatch.setattr(policy, "_run_command", _dispatch({"yamllint": _proc(0)}))

        assert policy.run_yamllint(["a.yml"], tmp_path) == 0
        assert policy.run_yamllint([], tmp_path) == 0
        assert _typed(capsys) == []


class TestPlanningAdvisory:
    def test_findings_are_typed_and_exit_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(policy, "_run_command", lambda *_a, **_k: _proc(1, "bad plan"))

        assert policy.run_planning_advisory(tmp_path) == 0
        assert _typed(capsys) == [("FAIL", "planning-advisory", "advisory.findings")]

    def test_a_clean_run_is_silent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(policy, "_run_command", lambda *_a, **_k: _proc(0))

        assert policy.run_planning_advisory(tmp_path) == 0
        assert _typed(capsys) == []


class TestTasteAdvisory:
    def test_findings_are_typed_and_exit_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = policy._TASTE_LINT_EXIT_VIOLATIONS
        monkeypatch.setattr(policy, "_run_command", lambda *_a, **_k: _proc(code))

        assert policy.run_taste_advisory(["x.py"], tmp_path) == 0
        assert _typed(capsys) == [("FAIL", "taste-advisory", "advisory.findings")]

    def test_a_crash_is_typed_as_the_linter_not_as_advisory_and_still_blocks(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(policy, "_run_command", lambda *_a, **_k: _proc(1, "", "Traceback"))

        assert policy.run_taste_advisory(["x.py"], tmp_path) == 2
        assert _typed(capsys) == [("FAIL", "taste-lints", "script.failed")]

    def test_a_clean_run_is_silent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(policy, "_run_command", lambda *_a, **_k: _proc(0))

        assert policy.run_taste_advisory(["x.py"], tmp_path) == 0
        assert _typed(capsys) == []


class TestAdditionsAdvisory:
    def _numstat(self, added: int) -> subprocess.CompletedProcess[str]:
        return _proc(0, f"{added}\t0\tbig.py\n")

    def test_a_failed_diff_is_a_typed_blocked_and_exits_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(policy, "_run_git", lambda *_a, **_k: _proc(128, "", "bad revision"))

        assert policy.additions_advisory(tmp_path) == 0
        assert _typed(capsys) == [("BLOCKED", "additions-advisory", "diff.failed")]

    def test_over_the_limit_is_a_typed_fail_and_exits_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(policy, "_run_git", lambda *_a, **_k: self._numstat(501))

        assert policy.additions_advisory(tmp_path) == 0
        assert _typed(capsys) == [("FAIL", "additions-advisory", "advisory.findings")]

    def test_exactly_at_the_limit_is_silent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(policy, "_run_git", lambda *_a, **_k: self._numstat(500))

        assert policy.additions_advisory(tmp_path) == 0
        assert _typed(capsys) == []


class TestBotCascadeAdvisory:
    _THREADS = "get_unresolved_review_threads.py"

    def _run(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        *,
        pr: object,
        threads: object = None,
        reviews: object = None,
    ) -> int:
        def run(args: Sequence[str], *_a: object, **_k: object) -> subprocess.CompletedProcess[str]:
            joined = " ".join(str(a) for a in args)
            for needle, result in (("pr view", pr), (self._THREADS, threads), ("api", reviews)):
                if needle in joined and result is not None:
                    if isinstance(result, BaseException):
                        raise result
                    return result  # type: ignore[return-value]
            raise AssertionError(f"unexpected command {joined}")

        monkeypatch.setattr(policy, "_run_command", run)
        return policy.bot_cascade_advisory(tmp_path)

    def test_a_missing_gh_is_a_typed_blocked(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert self._run(tmp_path, monkeypatch, pr=FileNotFoundError()) == 0
        assert _typed(capsys) == [("BLOCKED", "bot-cascade-advisory", "tool.absent")]

    def test_no_resolvable_pr_is_a_typed_skip(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert self._run(tmp_path, monkeypatch, pr=_proc(1, "", "no PR")) == 0
        assert _typed(capsys) == [("SKIP", "bot-cascade-advisory", "pr.unresolved")]

    def test_invalid_thread_json_is_a_typed_unknown(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc = self._run(
            tmp_path, monkeypatch, pr=_proc(0, "7\n"), threads=_proc(0, "not json"),
            reviews=_proc(0, ""),
        )

        assert rc == 0
        assert ("UNKNOWN", "bot-cascade-advisory", "output.malformed") in _typed(capsys)

    def test_unresolved_threads_are_a_typed_fail_with_the_count(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        payload = json.dumps({"fetched_pages_complete": True, "unresolved_count": 3})
        rc = self._run(
            tmp_path, monkeypatch, pr=_proc(0, "7\n"), threads=_proc(0, payload),
            reviews=_proc(0, ""),
        )

        assert rc == 0
        assert _typed(capsys) == [("FAIL", "bot-cascade-advisory", "advisory.findings")]

    def test_zero_unresolved_threads_and_no_bot_review_is_silent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        payload = json.dumps({"fetched_pages_complete": True, "unresolved_count": 0})
        rc = self._run(
            tmp_path, monkeypatch, pr=_proc(0, "7\n"), threads=_proc(0, payload),
            reviews=_proc(0, ""),
        )

        assert rc == 0
        assert _typed(capsys) == []

    def test_a_failed_review_query_is_a_typed_blocked(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        payload = json.dumps({"fetched_pages_complete": True, "unresolved_count": 0})
        rc = self._run(
            tmp_path, monkeypatch, pr=_proc(0, "7\n"), threads=_proc(0, payload),
            reviews=_proc(1, "", "rate limited"),
        )

        assert rc == 0
        assert _typed(capsys) == [("BLOCKED", "bot-cascade-advisory", "lookup.failed")]

    def test_an_unparseable_review_timestamp_is_a_typed_unknown(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        payload = json.dumps({"fetched_pages_complete": True, "unresolved_count": 0})
        rc = self._run(
            tmp_path, monkeypatch, pr=_proc(0, "7\n"), threads=_proc(0, payload),
            reviews=_proc(0, "not-a-time\n"),
        )

        assert rc == 0
        assert _typed(capsys) == [("UNKNOWN", "bot-cascade-advisory", "output.malformed")]


class TestWorkflowLocal:
    def _run(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: int) -> int:
        monkeypatch.setattr(policy, "_select_pushed_workflows", lambda *_a: ["x.yml"])
        monkeypatch.setattr(policy, "_run_command", lambda *_a, **_k: _proc(code))
        return policy.run_workflow_local(["x.yml"], tmp_path)

    def test_exit_four_is_a_typed_blocked_and_still_exits_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert self._run(tmp_path, monkeypatch, 4) == 0
        assert _typed(capsys) == [("BLOCKED", "workflow-local-run", "auth.unavailable")]

    def test_a_pass_is_silent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert self._run(tmp_path, monkeypatch, 0) == 0
        assert _typed(capsys) == []

    def test_a_real_failure_still_blocks_and_is_not_relabeled(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert self._run(tmp_path, monkeypatch, 1) == 1
        assert _typed(capsys) == []


class TestBranchContext:
    """Every fail-open return says which input it was; only a mismatch blocks."""

    @pytest.fixture
    def repo(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        (tmp_path / ".project-toolkit" / "sessions").mkdir(parents=True)
        log = tmp_path / ".project-toolkit" / "sessions" / "today.json"
        log.write_text("{}", encoding="utf-8")
        monkeypatch.setattr(policy, "_merge_in_progress", lambda _r: False)
        monkeypatch.setattr(policy, "_current_branch", lambda _r: "feature/a")
        monkeypatch.setattr(policy, "_today_session_log", lambda _d: log)
        monkeypatch.setattr(policy, "_session_branch", lambda _l: "feature/b")
        monkeypatch.setattr(policy, "_is_merged_history", lambda _r, _l: False)
        monkeypatch.setattr(policy, "_is_linked_worktree", lambda _r: False)
        monkeypatch.setattr(policy, "_is_committed_here", lambda _r, _l: False)
        return tmp_path

    def test_a_mismatch_blocks_and_prints_no_skip_line(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert policy.check_branch_context(repo) == 1
        assert _typed(capsys) == []

    def test_matching_branches_pass_silently(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(policy, "_session_branch", lambda _l: "feature/a")

        assert policy.check_branch_context(repo) == 0
        assert _typed(capsys) == []

    @pytest.mark.parametrize(
        ("patch_name", "value", "reason"),
        [
            ("_merge_in_progress", lambda _r: True, "git.merge_in_progress"),
            ("_current_branch", lambda _r: None, "branch.undetermined"),
            ("_today_session_log", lambda _d: None, "tree.absent"),
            ("_session_branch", lambda _l: None, "evidence.incomplete"),
            ("_is_merged_history", lambda _r, _l: True, "policy.exempt"),
        ],
    )
    def test_each_fail_open_input_is_a_typed_skip_and_exits_zero(
        self,
        repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        patch_name: str,
        value: Callable[..., object],
        reason: str,
    ) -> None:
        monkeypatch.setattr(policy, patch_name, value)

        assert policy.check_branch_context(repo) == 0
        assert _typed(capsys) == [("SKIP", "branch-context", reason)]

    def test_a_linked_worktree_exemption_is_a_typed_skip(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(policy, "_is_linked_worktree", lambda _r: True)
        monkeypatch.setattr(policy, "_is_committed_here", lambda _r, _l: True)

        assert policy.check_branch_context(repo) == 0
        assert _typed(capsys) == [("SKIP", "branch-context", "policy.exempt")]

    def test_no_sessions_directory_is_a_typed_skip(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(policy, "_merge_in_progress", lambda _r: False)

        assert policy.check_branch_context(tmp_path) == 0
        assert _typed(capsys) == [("SKIP", "branch-context", "tree.absent")]

    def test_a_raise_is_a_typed_unknown_and_still_fails_open(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def boom(_r: Path) -> str:
            raise OSError("disk gone")

        monkeypatch.setattr(policy, "_current_branch", boom)

        assert policy.check_branch_context(repo) == 0
        assert _typed(capsys) == [("UNKNOWN", "branch-context", "validator.raised")]

"""Tests for scripts/ci/commit_and_push.py.

Covers the bot commit step extracted from update-reviewer-stats.yml. These
tests pin the branch the shell block encoded: a clean tree is a no-op, a dirty
tree stages only the named paths, every message becomes its own `-m`, and a
failing git command surfaces instead of being swallowed. Git itself is mocked
so no test touches a real repository or network.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS_CI = Path(__file__).resolve().parent.parent.parent / "scripts" / "ci"
_original_path = sys.path.copy()
try:
    sys.path.insert(0, str(_SCRIPTS_CI))
    import commit_and_push  # noqa: E402
    from commit_and_push import main  # noqa: E402
finally:
    sys.path[:] = _original_path

_ARGS = [
    "--path", "a.md",
    "--user-name", "bot",
    "--user-email", "bot@example.com",
    "--message", "subject",
    "--message", "body",
]


class _Recorder:
    """Stand-in for subprocess.run that records argv and replays canned results."""

    def __init__(self, status_out: str = "", failing: str | None = None) -> None:
        self.calls: list[list[str]] = []
        self._status_out = status_out
        self._failing = failing

    def __call__(self, argv, **kwargs):  # noqa: ANN001, ANN204
        self.calls.append(list(argv))
        verb = argv[1]
        if verb == "status":
            return subprocess.CompletedProcess(argv, 0, self._status_out)
        code = 1 if verb == self._failing else 0
        return subprocess.CompletedProcess(argv, code, f"{verb} output")

    def verbs(self) -> list[str]:
        return [c[1] for c in self.calls]


def _install(monkeypatch: pytest.MonkeyPatch, recorder: _Recorder) -> None:
    monkeypatch.setattr(commit_and_push, "subprocess", subprocess)
    monkeypatch.setattr(subprocess, "run", recorder)


def test_clean_tree_is_a_no_op(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    recorder = _Recorder(status_out="")
    _install(monkeypatch, recorder)
    assert main(_ARGS) == 0
    assert "No changes to commit" in capsys.readouterr().out
    assert "commit" not in recorder.verbs()
    assert "push" not in recorder.verbs()


def test_dirty_tree_stages_commits_and_pushes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    recorder = _Recorder(status_out=" M a.md\n")
    _install(monkeypatch, recorder)
    assert main(_ARGS) == 0
    assert "Changes committed and pushed" in capsys.readouterr().out
    assert recorder.verbs() == ["config", "config", "status", "add", "commit", "push"]


def test_status_is_scoped_to_the_named_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _Recorder(status_out="")
    _install(monkeypatch, recorder)
    main(_ARGS)
    status = next(c for c in recorder.calls if c[1] == "status")
    assert status == ["git", "status", "--porcelain", "--", "a.md"]


def test_each_message_becomes_its_own_dash_m(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _Recorder(status_out=" M a.md\n")
    _install(monkeypatch, recorder)
    main(_ARGS)
    commit = next(c for c in recorder.calls if c[1] == "commit")
    assert commit == ["git", "commit", "-m", "subject", "-m", "body"]


def test_add_uses_a_double_dash_separator(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _Recorder(status_out=" M a.md\n")
    _install(monkeypatch, recorder)
    main(_ARGS)
    add = next(c for c in recorder.calls if c[1] == "add")
    assert add == ["git", "add", "--", "a.md"]


def test_multiple_paths_are_all_staged(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _Recorder(status_out=" M a.md\n")
    _install(monkeypatch, recorder)
    main([*_ARGS, "--path", "b.md"])
    add = next(c for c in recorder.calls if c[1] == "add")
    assert add == ["git", "add", "--", "a.md", "b.md"]


@pytest.mark.parametrize("failing", ["config", "add", "commit", "push"])
def test_a_failing_git_command_is_reported(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], failing: str
) -> None:
    recorder = _Recorder(status_out=" M a.md\n", failing=failing)
    _install(monkeypatch, recorder)
    assert main(_ARGS) == 1
    assert f"git {failing}" in capsys.readouterr().err


def test_push_is_not_attempted_after_a_failed_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = _Recorder(status_out=" M a.md\n", failing="commit")
    _install(monkeypatch, recorder)
    main(_ARGS)
    assert "push" not in recorder.verbs()


def test_missing_git_binary_is_a_usage_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _boom(argv, **kwargs):  # noqa: ANN001, ANN202
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", _boom)
    assert main(_ARGS) == 2
    assert "git not available" in capsys.readouterr().err


def test_failed_status_is_reported_not_treated_as_clean(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _status_fails(argv, **kwargs):  # noqa: ANN001, ANN202
        if argv[1] == "status":
            return subprocess.CompletedProcess(argv, 128, "not a repository")
        return subprocess.CompletedProcess(argv, 0, "")

    monkeypatch.setattr(subprocess, "run", _status_fails)
    assert main(_ARGS) == 1
    assert "git status failed" in capsys.readouterr().err

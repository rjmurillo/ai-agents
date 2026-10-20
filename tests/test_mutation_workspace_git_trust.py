"""Tests for the act-only safe.directory trust in mutation_workspace_git.run_git."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.testing import mutation_workspace_git
from scripts.testing.mutation_workspace_git import (
    MutationWorkspaceError,
    git_root,
    run_git,
)

# git reads this variable in release builds and treats every repository as
# owned by another user, which is the state inside an act container.
ASSUME_OTHER_OWNER = "GIT_TEST_ASSUME_DIFFERENT_OWNER"


def _init_repo(path: Path) -> Path:
    path.mkdir()
    subprocess.run(["git", "init", "--quiet"], cwd=path, check=True)
    return path.resolve()


def _safe_directory_args(command: list[str]) -> list[str]:
    return [
        command[index + 1]
        for index, token in enumerate(command[:-1])
        if token == "-c" and command[index + 1].startswith("safe.directory=")
    ]


class _Recorder:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        self.commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    recording = _Recorder()
    monkeypatch.setattr(mutation_workspace_git.subprocess, "run", recording)
    return recording


@pytest.mark.parametrize("marker", ["true", "TRUE", " true "])
def test_act_marker_trusts_only_the_resolved_root(
    marker: str, recorder: _Recorder, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ACT", marker)

    run_git(tmp_path, "status")

    assert _safe_directory_args(recorder.commands[0]) == [f"safe.directory={tmp_path.resolve()}"]


@pytest.mark.parametrize("marker", [None, "", "false", "1", "yes"])
def test_without_act_marker_no_path_is_trusted(
    marker: str | None, recorder: _Recorder, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    if marker is None:
        monkeypatch.delenv("ACT", raising=False)
    else:
        monkeypatch.setenv("ACT", marker)

    run_git(tmp_path, "status")

    assert _safe_directory_args(recorder.commands[0]) == []


def test_trust_is_never_a_wildcard(
    recorder: _Recorder, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ACT", "true")

    run_git(tmp_path, "status")

    assert not any(token.endswith("=*") for token in recorder.commands[0])


def test_act_container_accepts_the_trusted_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = _init_repo(tmp_path / "trusted")
    monkeypatch.setenv(ASSUME_OTHER_OWNER, "1")
    monkeypatch.setenv("ACT", "true")

    assert git_root(repo) == repo


def test_host_still_refuses_a_dubious_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "dubious")
    monkeypatch.setenv(ASSUME_OTHER_OWNER, "1")
    monkeypatch.delenv("ACT", raising=False)

    with pytest.raises(MutationWorkspaceError, match="dubious ownership"):
        git_root(repo)


def test_act_container_still_refuses_an_unrelated_dubious_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    trusted = _init_repo(tmp_path / "trusted")
    unrelated = _init_repo(tmp_path / "unrelated")
    monkeypatch.setenv(ASSUME_OTHER_OWNER, "1")
    monkeypatch.setenv("ACT", "true")

    result = run_git(trusted, "-C", str(unrelated), "rev-parse", "--show-toplevel")

    assert result.returncode != 0
    assert "dubious ownership" in result.stderr

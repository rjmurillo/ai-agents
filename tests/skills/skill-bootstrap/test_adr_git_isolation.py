"""Tests for how the ADR backfill runs git: launch failures, kept stderr, a clean environment."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import adr_scan
import bootstrap_adr
import pytest
from adr_helpers import commit, new_repo, run_cli


def _refusal(stderr: bytes, code: int = 128) -> Any:
    def fake(repo: Path, *args: str, stdin: bytes | None = None) -> Any:
        return subprocess.CompletedProcess(args, code, b"", stderr)

    return fake


# ---------------------------------------------------------------------------
# Item 16: a launch failure is a git error
# ---------------------------------------------------------------------------


def test_a_git_launch_failure_is_a_git_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def refused(*args: Any, **kwargs: Any) -> Any:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(subprocess, "run", refused)
    with pytest.raises(adr_scan.GitError, match="Permission denied"):
        adr_scan.git_bytes(tmp_path, "status")


def test_a_git_launch_failure_exits_three_not_two(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def refused(*args: Any, **kwargs: Any) -> Any:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(subprocess, "run", refused)
    assert bootstrap_adr.main(["locate", "--repo", str(tmp_path)]) == 3
    assert json.loads(capsys.readouterr().out)["error"] == "git"


# ---------------------------------------------------------------------------
# Item 17: git's own words reach the caller
# ---------------------------------------------------------------------------

_DUBIOUS = b"fatal: detected dubious ownership in repository at '/srv/x'\n"


def test_repo_root_keeps_git_stderr_for_a_plain_folder(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(adr_scan.ConfigError, match="not a git repository") as caught:
        adr_scan.repo_root(plain)
    assert "fatal:" in str(caught.value)


def test_a_dubious_ownership_refusal_is_a_git_error_not_a_missing_repository(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(adr_scan, "git_bytes", _refusal(_DUBIOUS))
    with pytest.raises(adr_scan.GitError, match="dubious ownership"):
        adr_scan.repo_root(tmp_path)


def test_a_dubious_ownership_refusal_exits_three(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(adr_scan, "git_bytes", _refusal(_DUBIOUS))
    assert bootstrap_adr.main(["locate", "--repo", str(tmp_path)]) == 3
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"] == "git" and "dubious ownership" in payload["message"]


def test_resolve_rev_keeps_git_stderr(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(adr_scan, "git_bytes", _refusal(b"fatal: unusable object store\n"))
    with pytest.raises(adr_scan.ConfigError, match="unusable object store"):
        adr_scan.resolve_rev(tmp_path, "HEAD")


# ---------------------------------------------------------------------------
# Item 18: the child does not inherit repository-redirecting variables
# ---------------------------------------------------------------------------


def test_git_env_drops_the_repository_variables_and_never_prompts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    names = (
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_COMMON_DIR",
        "GIT_NAMESPACE",
        "GIT_PREFIX",
        "GIT_CONFIG_PARAMETERS",
    )
    for name in names:
        monkeypatch.setenv(name, "/elsewhere")
    env = adr_scan.git_env()
    for name in names:
        assert name not in env
    assert env["GIT_TERMINAL_PROMPT"] == "0" and env["GIT_NO_LAZY_FETCH"] == "1"


def test_git_env_leaves_the_rest_of_the_environment_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_DIR", "/elsewhere")
    monkeypatch.setenv("HOME_MARKER_FOR_TEST", "kept")
    env = adr_scan.git_env()
    assert "GIT_DIR" not in env and env["HOME_MARKER_FOR_TEST"] == "kept"


def test_a_git_dir_in_the_parent_environment_does_not_redirect_scan(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    mine = commit(repo, "Adopt Postgres instead of MySQL\n\nBecause the team runs it already.\n")
    other = new_repo(tmp_path / "other")
    commit(other, "Initial work in the other repository")
    env = {**os.environ, "GIT_DIR": str(other / ".git"), "GIT_WORK_TREE": str(other)}
    code, payload = run_cli(
        "scan", "--repo", str(repo), "--out", str(tmp_path / "scan.json"), env=env
    )
    assert code == 0
    assert payload["head"] == mine and payload["repo"] == str(repo)

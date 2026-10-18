"""bootstrap_boundary: every git call carries a timeout, and a timeout is a GitError."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import bootstrap_boundary
import pytest
from bootstrap_helpers import plan


def test_run_git_passes_the_timeout(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake(*_args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        seen.update(kwargs)
        return subprocess.CompletedProcess([], 0, "ok\n", "")

    monkeypatch.setattr(bootstrap_boundary.subprocess, "run", fake)

    proc = bootstrap_boundary._run_git(repo, "rev-parse", "HEAD")

    assert seen["timeout"] == bootstrap_boundary.GIT_TIMEOUT_S
    assert proc.stdout == "ok\n"


def test_run_git_maps_a_timeout_to_a_git_error(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def slow(*_args: Any, **_kwargs: Any) -> None:
        raise subprocess.TimeoutExpired("git", bootstrap_boundary.GIT_TIMEOUT_S)

    monkeypatch.setattr(bootstrap_boundary.subprocess, "run", slow)

    with pytest.raises(bootstrap_boundary.GitError, match="rev-parse HEAD timed out after 30 s"):
        bootstrap_boundary._run_git(repo, "rev-parse", "HEAD")


def test_plan_exits_three_with_the_git_name_when_git_hangs(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def slow(*_args: Any, **_kwargs: Any) -> None:
        raise subprocess.TimeoutExpired("git", bootstrap_boundary.GIT_TIMEOUT_S)

    monkeypatch.setattr(bootstrap_boundary.subprocess, "run", slow)

    code = bootstrap_boundary.main(
        ["plan", "--repo", str(repo), "--output-root", ".claude/skills", "--name", "new-skill"]
    )

    payload = capsys.readouterr().out
    assert code == 3
    assert '"error": "git"' in payload
    assert "timed out" in payload


def test_a_fast_git_call_is_unaffected(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, payload = plan(capsys, repo, "--name", "new-skill")

    assert code == 0
    assert "error" not in payload

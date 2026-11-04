"""Helpers for the reflect nudge safety tests (REQ-048 TASK-004).

Hosts the git fixtures, the isolation fixture, and the subprocess runner so the
AC-24, AC-15, and AC-05/AC-06 test modules stay small.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from tests.hooks.reflect_nudge_support import REPO_ROOT, human, nudge_state, write_transcript

STATE_SUBDIR: str = nudge_state.STATE_SUBDIR
RENDERED_HOOK = REPO_ROOT / "src" / "claude" / "hooks" / "Stop" / "invoke_reflect_nudge.py"
GIT_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_TERMINAL_PROMPT": "0",
}


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point HOME and the state variables at temp dirs so no test touches ~/.local/state."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("XDG_STATE_HOME", str(home / ".local" / "state"))
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.delenv("AI_AGENTS_RETRO_NUDGE_THRESHOLD", raising=False)
    return home


def correction_records() -> list[Any]:
    return [human("No, use the skill script"), human("that's wrong")]


def git(repo: Path, *args: str) -> str:
    """Run git in ``repo`` with a config-free environment and return stdout."""
    done = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        env={**os.environ, **GIT_ENV},
        timeout=30,
        check=True,
    )
    return done.stdout


def init_repo(path: Path) -> Path:
    """Create a git repository with one empty commit, so the tree starts clean."""
    path.mkdir(parents=True)
    git(path, "init", "-q")
    git(
        path,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@example.invalid",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "init",
    )
    return path


def tree_snapshot(directory: Path) -> dict[str, str]:
    """Map every file under ``directory`` to a content hash, byte for byte."""
    snapshot: dict[str, str] = {}
    for entry in sorted(directory.rglob("*")):
        relative = str(entry.relative_to(directory))
        if entry.is_symlink():
            snapshot[relative] = "link:" + os.readlink(entry)
        elif entry.is_file():
            snapshot[relative] = hashlib.sha256(entry.read_bytes()).hexdigest()
        else:
            snapshot[relative] = "dir"
    return snapshot


def run_subprocess(
    hook: Path, stdin_text: str, env: Mapping[str, str], cwd: Path
) -> subprocess.CompletedProcess[str]:
    """Run the hook script as the harness does: a python child with stdin and env."""
    return subprocess.run(
        [sys.executable, str(hook)],
        input=stdin_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=dict(env),
        cwd=cwd,
        timeout=60,
        check=False,
    )


def child_env(home: Path, state_home: Path) -> dict[str, str]:
    """Minimal child environment: PATH for git, HOME and XDG_STATE_HOME pinned to temp dirs."""
    return {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(home),
        "XDG_STATE_HOME": str(state_home),
        **GIT_ENV,
    }


def stop_payload(transcript: Path, cwd: Path, session_id: str = "sess-1") -> str:
    return json.dumps(
        {"session_id": session_id, "transcript_path": str(transcript), "cwd": str(cwd)}
    )


__all__ = [
    "RENDERED_HOOK",
    "STATE_SUBDIR",
    "child_env",
    "correction_records",
    "git",
    "init_repo",
    "isolated_home",
    "run_subprocess",
    "stop_payload",
    "tree_snapshot",
    "write_transcript",
]

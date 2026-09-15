#!/usr/bin/env python3
"""Shell-injection safety for the repo_root written into $CLAUDE_ENV_FILE.

templates/hooks/session-start.sh resolves repo_root from its own location
(CWE-22 defense: robust against $CLAUDE_PROJECT_DIR/$PWD manipulation) and
then writes an `export PATH=...` line into a file a LATER shell sources
($CLAUDE_ENV_FILE). Before the fix this pinned, repo_root was interpolated
into that line unescaped: a checkout directory name carrying a quote,
newline, or command substitution would execute at source time (CWE-78).

Runs the real installed script (`.claude/hooks/session-start.sh`, the
generated artifact `templates/hooks/session-start.sh` renders to) end to
end under a fake repo whose directory name is a shell-injection payload,
then sources the env file it writes and confirms the payload never ran.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALLED_SCRIPT = REPO_ROOT / ".claude" / "hooks" / "session-start.sh"


def _bash_available() -> bool:
    try:
        proc = subprocess.run(
            ["bash", "-c", "printf ok"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except OSError:
        return False
    return proc.returncode == 0 and proc.stdout == "ok"


requires_bash = pytest.mark.skipif(not _bash_available(), reason="no working bash on PATH")


def _materialize_fake_repo(base: Path, dirname: str) -> Path:
    """Build a fake checkout under a directory name carrying shell metacharacters."""
    repo = base / dirname
    (repo / ".claude" / "hooks").mkdir(parents=True)
    (repo / "scripts").mkdir(parents=True, exist_ok=True)
    bootstrap = repo / "scripts" / "bootstrap-vm.sh"
    bootstrap.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    bootstrap.chmod(bootstrap.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    script_copy = repo / ".claude" / "hooks" / "session-start.sh"
    script_copy.write_bytes(INSTALLED_SCRIPT.read_bytes())
    script_copy.chmod(script_copy.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return repo


def _run_session_start(repo: Path, env_file: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["CLAUDE_CODE_REMOTE"] = "true"
    env["CLAUDE_ENV_FILE"] = str(env_file)
    return subprocess.run(
        ["bash", str(repo / ".claude" / "hooks" / "session-start.sh")],
        cwd=repo,
        env=env,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )


@requires_bash
def test_repo_root_with_quote_and_command_substitution_does_not_inject(tmp_path: Path) -> None:
    """A checkout dir name carrying `"; touch INJECTED; echo "` cannot execute on source."""
    malicious = 'pwn"; touch INJECTED; echo "'
    repo = _materialize_fake_repo(tmp_path, malicious)
    env_file = tmp_path / "env.sh"
    env_file.write_text("", encoding="utf-8")

    proc = _run_session_start(repo, env_file)
    assert proc.returncode == 0, proc.stderr

    marker = tmp_path / "INJECTED"
    subprocess.run(
        ["bash", "-c", f'source "{env_file}"'],
        cwd=tmp_path,
        capture_output=True,
        timeout=10,
        check=False,
    )

    assert not marker.exists()
    assert "export PATH=" in env_file.read_text(encoding="utf-8")


@requires_bash
def test_repo_root_with_space_still_produces_a_working_path(tmp_path: Path) -> None:
    """A benign checkout dir name with a space still round-trips correctly."""
    repo = _materialize_fake_repo(tmp_path, "my repo")
    env_file = tmp_path / "env.sh"
    env_file.write_text("", encoding="utf-8")

    proc = _run_session_start(repo, env_file)
    assert proc.returncode == 0, proc.stderr

    check = subprocess.run(
        ["bash", "-c", f'source "{env_file}" && printf %s "$PATH"'],
        cwd=tmp_path,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
        check=False,
    )
    assert check.returncode == 0, check.stderr
    assert f"{repo}/.venv/bin" in check.stdout


@requires_bash
def test_env_file_written_once_across_repeated_runs(tmp_path: Path) -> None:
    """Idempotency check still recognizes its own escaped entry on a second run."""
    repo = _materialize_fake_repo(tmp_path, "plain-repo")
    env_file = tmp_path / "env.sh"
    env_file.write_text("", encoding="utf-8")

    _run_session_start(repo, env_file)
    first = env_file.read_text(encoding="utf-8")
    _run_session_start(repo, env_file)
    second = env_file.read_text(encoding="utf-8")

    assert first == second
    assert second.count("export PATH=") == 1

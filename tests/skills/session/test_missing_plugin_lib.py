"""Missing plugin lib handling for session log write scripts."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SESSION_WRITE_SCRIPTS = [
    REPO_ROOT / ".claude" / "skills" / "session-init" / "scripts" / "new_session_log.py",
    REPO_ROOT / ".claude" / "skills" / "session-init" / "scripts" / "new_session_log_json.py",
    REPO_ROOT / ".claude" / "skills" / "session-end" / "scripts" / "complete_session_log.py",
    REPO_ROOT
    / "src"
    / "copilot-cli"
    / "skills"
    / "session-init"
    / "scripts"
    / "new_session_log.py",
    REPO_ROOT
    / "src"
    / "copilot-cli"
    / "skills"
    / "session-init"
    / "scripts"
    / "new_session_log_json.py",
    REPO_ROOT
    / "src"
    / "copilot-cli"
    / "skills"
    / "session-end"
    / "scripts"
    / "complete_session_log.py",
]


@pytest.mark.parametrize("script_path", SESSION_WRITE_SCRIPTS)
def test_missing_plugin_lib_fails_closed(script_path: Path, tmp_path: Path) -> None:
    env = os.environ.copy()
    env["COPILOT_PLUGIN_ROOT"] = str(tmp_path / "missing-plugin")
    env.pop("CLAUDE_PLUGIN_ROOT", None)

    result = subprocess.run(
        [sys.executable, str(script_path), "--help"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
        env=env,
    )

    assert result.returncode == 2
    assert "Plugin lib directory not found:" in result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("script_path", SESSION_WRITE_SCRIPTS)
def test_workspace_miss_falls_back_to_bundled_lib(script_path: Path, tmp_path: Path) -> None:
    env = os.environ.copy()
    env["GITHUB_WORKSPACE"] = str(tmp_path / "consumer-repo")
    env.pop("COPILOT_PLUGIN_ROOT", None)
    env.pop("CLAUDE_PLUGIN_ROOT", None)

    result = subprocess.run(
        [sys.executable, str(script_path), "--help"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
        env=env,
    )

    assert result.returncode == 0
    assert "Plugin lib directory not found" not in result.stderr
    assert "Traceback" not in result.stderr

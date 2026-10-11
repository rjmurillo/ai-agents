"""Tests that the pre-push CLI smoke gate arms the local Copilot guard."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

# tests/e2e is not on sys.path under --import-mode=importlib (no __init__.py).
sys.path.insert(0, str(Path(__file__).resolve().parent))

import local_smoke_guard as guard

from scripts.validation import git_hook_policy


def test_gate_flag_name_matches_the_guard() -> None:
    assert git_hook_policy.CLI_E2E_LOCAL_SMOKE_ENV == guard.LOCAL_SMOKE_ENV


def test_run_cli_e2e_arms_the_guard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The gate must set the flag, or the guard never arms."""
    monkeypatch.delenv("SKIP_CLI_E2E", raising=False)
    monkeypatch.setattr(git_hook_policy.shutil, "which", lambda name: name)
    seen: dict[str, object] = {}

    def fake_run_command(_command: object, *_args: object, **kwargs: object) -> object:
        seen.update(kwargs)
        return subprocess.CompletedProcess([], 0, "", "")

    monkeypatch.setattr(git_hook_policy, "_run_command", fake_run_command)

    assert git_hook_policy.run_cli_e2e("tests/e2e/test.py", tmp_path) == 0
    env = seen["process_env"]
    assert isinstance(env, dict)
    assert env[guard.LOCAL_SMOKE_ENV] == "1"

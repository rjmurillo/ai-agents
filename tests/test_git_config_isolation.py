"""Tests for hermetic git-config isolation helpers (issue #2996)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from tests.git_config_isolation import (
    restore_git_config_env,
    snapshot_git_config_env,
    strip_git_config_hooks_path,
)

# --- GIT_CONFIG_PARAMETERS form (git -c) ------------------------------------


def test_strips_hooks_path_from_parameters() -> None:
    env = {"GIT_CONFIG_PARAMETERS": "'core.hooksPath'='/abs/.githooks'"}
    strip_git_config_hooks_path(env)
    assert "GIT_CONFIG_PARAMETERS" not in env


def test_strips_hooks_path_keeps_other_parameters() -> None:
    env = {
        "GIT_CONFIG_PARAMETERS": (
            "'core.hooksPath'='/abs/.githooks' 'user.name'='Jane Doe'"
        )
    }
    strip_git_config_hooks_path(env)
    assert env["GIT_CONFIG_PARAMETERS"] == "'user.name'='Jane Doe'"


def test_parameters_case_insensitive_key() -> None:
    env = {"GIT_CONFIG_PARAMETERS": "'CORE.HOOKSPATH'='/abs'"}
    strip_git_config_hooks_path(env)
    assert "GIT_CONFIG_PARAMETERS" not in env


def test_parameters_bool_key_without_value() -> None:
    # A boolean-true parameter has no '=value' suffix.
    env = {"GIT_CONFIG_PARAMETERS": "'core.hooksPath' 'feature.flag'='1'"}
    strip_git_config_hooks_path(env)
    assert env["GIT_CONFIG_PARAMETERS"] == "'feature.flag'='1'"


def test_parameters_value_with_embedded_space() -> None:
    env = {
        "GIT_CONFIG_PARAMETERS": (
            "'core.hooksPath'='/path with space/.githooks' 'user.name'='x'"
        )
    }
    strip_git_config_hooks_path(env)
    assert env["GIT_CONFIG_PARAMETERS"] == "'user.name'='x'"


# --- GIT_CONFIG_COUNT indexed form ------------------------------------------


def test_strips_hooks_path_from_indexed() -> None:
    env = {
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "core.hooksPath",
        "GIT_CONFIG_VALUE_0": "/abs/.githooks",
    }
    strip_git_config_hooks_path(env)
    assert "GIT_CONFIG_COUNT" not in env
    assert "GIT_CONFIG_KEY_0" not in env
    assert "GIT_CONFIG_VALUE_0" not in env


def test_indexed_renumbers_survivors() -> None:
    env = {
        "GIT_CONFIG_COUNT": "3",
        "GIT_CONFIG_KEY_0": "commit.gpgsign",
        "GIT_CONFIG_VALUE_0": "false",
        "GIT_CONFIG_KEY_1": "core.hooksPath",
        "GIT_CONFIG_VALUE_1": "/abs/.githooks",
        "GIT_CONFIG_KEY_2": "user.name",
        "GIT_CONFIG_VALUE_2": "Jane",
    }
    strip_git_config_hooks_path(env)
    assert env["GIT_CONFIG_COUNT"] == "2"
    assert env["GIT_CONFIG_KEY_0"] == "commit.gpgsign"
    assert env["GIT_CONFIG_VALUE_0"] == "false"
    assert env["GIT_CONFIG_KEY_1"] == "user.name"
    assert env["GIT_CONFIG_VALUE_1"] == "Jane"
    assert "GIT_CONFIG_KEY_2" not in env
    assert "GIT_CONFIG_VALUE_2" not in env


def test_indexed_case_insensitive_key() -> None:
    env = {
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "Core.HooksPath",
        "GIT_CONFIG_VALUE_0": "/abs",
    }
    strip_git_config_hooks_path(env)
    assert "GIT_CONFIG_COUNT" not in env


def test_indexed_malformed_count_left_untouched() -> None:
    env = {"GIT_CONFIG_COUNT": "notanint", "GIT_CONFIG_KEY_0": "core.hooksPath"}
    strip_git_config_hooks_path(env)
    assert env["GIT_CONFIG_COUNT"] == "notanint"
    assert env["GIT_CONFIG_KEY_0"] == "core.hooksPath"


# --- Negative / no-op cases -------------------------------------------------


def test_no_hooks_path_is_noop() -> None:
    env = {
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "commit.gpgsign",
        "GIT_CONFIG_VALUE_0": "false",
        "GIT_CONFIG_PARAMETERS": "'user.name'='x'",
        "UNRELATED": "keep",
    }
    before = dict(env)
    strip_git_config_hooks_path(env)
    assert env == before


def test_empty_environ_is_noop() -> None:
    env: dict[str, str] = {}
    strip_git_config_hooks_path(env)
    assert env == {}


def test_idempotent() -> None:
    env = {
        "GIT_CONFIG_PARAMETERS": "'core.hooksPath'='/abs' 'user.name'='x'",
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "core.hooksPath",
        "GIT_CONFIG_VALUE_0": "/abs",
    }
    strip_git_config_hooks_path(env)
    once = dict(env)
    strip_git_config_hooks_path(env)
    assert env == once


# --- snapshot / restore -----------------------------------------------------


def test_snapshot_and_restore_roundtrip() -> None:
    env = {
        "GIT_CONFIG_PARAMETERS": "'core.hooksPath'='/abs'",
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "core.hooksPath",
        "GIT_CONFIG_VALUE_0": "/abs",
        "PATH": "/usr/bin",
    }
    snapshot = snapshot_git_config_env(env)
    strip_git_config_hooks_path(env)
    # gpgsign injection would happen here in the real fixture.
    env["GIT_CONFIG_COUNT"] = "1"
    env["GIT_CONFIG_KEY_0"] = "commit.gpgsign"
    env["GIT_CONFIG_VALUE_0"] = "false"
    restore_git_config_env(env, snapshot)
    assert env["GIT_CONFIG_PARAMETERS"] == "'core.hooksPath'='/abs'"
    assert env["GIT_CONFIG_KEY_0"] == "core.hooksPath"
    assert env["PATH"] == "/usr/bin"


def test_restore_removes_injected_keys() -> None:
    env: dict[str, str] = {"PATH": "/usr/bin"}
    snapshot = snapshot_git_config_env(env)
    env["GIT_CONFIG_COUNT"] = "1"
    env["GIT_CONFIG_KEY_0"] = "commit.gpgsign"
    env["GIT_CONFIG_VALUE_0"] = "false"
    restore_git_config_env(env, snapshot)
    assert "GIT_CONFIG_COUNT" not in env
    assert env == {"PATH": "/usr/bin"}


# --- Behavioral: prove a leaked absolute hooksPath no longer fires ----------


def test_leaked_absolute_hooks_path_no_longer_runs_hook(tmp_path: Path) -> None:
    """Reproduce the #2925 push failure and prove the strip neutralizes it.

    Without the strip, a leaked absolute ``core.hooksPath`` makes ``git commit``
    in a fresh repo run the real (failing) pre-commit hook. After the strip, the
    commit succeeds.
    """
    hooks = tmp_path / "realhooks"
    hooks.mkdir()
    pre_commit = hooks / "pre-commit"
    pre_commit.write_text("#!/bin/sh\necho HOOK_RAN >&2\nexit 1\n")
    pre_commit.chmod(0o755)

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)

    leaked_env = {
        "PATH": os.environ["PATH"],
        "HOME": str(tmp_path),
        "GIT_CONFIG_PARAMETERS": f"'core.hooksPath'='{hooks}'",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
    }
    commit_cmd = [
        "git",
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@t.com",
        "commit",
        "--allow-empty",
        "-m",
        "probe",
    ]

    # Positive control: with the leak, the hook runs and the commit fails.
    polluted = subprocess.run(
        commit_cmd, cwd=repo, env=leaked_env, capture_output=True, encoding="utf-8"
    )
    assert polluted.returncode != 0
    assert "HOOK_RAN" in polluted.stderr

    # After the strip, the hook does not run and the commit succeeds.
    strip_git_config_hooks_path(leaked_env)
    cleaned = subprocess.run(
        commit_cmd, cwd=repo, env=leaked_env, capture_output=True, encoding="utf-8"
    )
    assert cleaned.returncode == 0, cleaned.stderr
    assert "HOOK_RAN" not in cleaned.stderr

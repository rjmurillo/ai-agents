"""Behavioral check for the commit-signing conftest fixture (issue #2548)."""

from __future__ import annotations

import os
import subprocess

import pytest


def test_subprocess_git_sees_signing_disabled() -> None:
    # The autouse session fixture injects commit.gpgsign=false via
    # GIT_CONFIG_COUNT, so a git subprocess must report it as false.
    if os.environ.get("GIT_CONFIG_KEY_0") != "commit.gpgsign":
        pytest.skip("commit.gpgsign fixture did not claim GIT_CONFIG_KEY_0")
    result = subprocess.run(
        ["git", "config", "--get", "commit.gpgsign"],
        capture_output=True,
        encoding="utf-8",
        env={**os.environ, "LC_ALL": "C"},
        check=False,
    )
    assert result.stdout.strip() == "false"

"""Tests for shared validation subprocess behavior."""

from __future__ import annotations

import sys
from unittest.mock import patch

from scripts.validation import subprocess_runner


def test_subprocess_resolves_windows_command_shim() -> None:
    completed = subprocess_runner.subprocess.CompletedProcess(
        ["npx.cmd", "--version"], 0, "11.17.0\n", ""
    )
    with (
        patch.object(
            subprocess_runner,
            "resolve_executable",
            return_value=r"C:\Program Files\nodejs\npx.cmd",
        ) as resolver,
        patch.object(subprocess_runner.subprocess, "run", return_value=completed) as run,
    ):
        result = subprocess_runner._run_subprocess(["npx", "--version"])

    assert result == (0, "11.17.0\n", "")
    resolver.assert_called_once_with("npx", env=None)
    assert run.call_args.args[0] == [
        r"C:\Program Files\nodejs\npx.cmd",
        "--version",
    ]


def test_subprocess_preserves_explicit_executable_path() -> None:
    completed = subprocess_runner.subprocess.CompletedProcess(
        [sys.executable, "--version"], 0, "Python\n", ""
    )
    with (
        patch.object(subprocess_runner, "resolve_executable") as resolver,
        patch.object(subprocess_runner.subprocess, "run", return_value=completed) as run,
    ):
        result = subprocess_runner._run_subprocess([sys.executable, "--version"])

    assert result == (0, "Python\n", "")
    resolver.assert_not_called()
    assert run.call_args.args[0] == [sys.executable, "--version"]

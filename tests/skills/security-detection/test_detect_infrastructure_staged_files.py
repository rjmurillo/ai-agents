#!/usr/bin/env python3
"""Tests for get_staged_files."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

HERE = str(Path(__file__).resolve().parent)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from detect_infrastructure_test_helpers import get_staged_files


def test_get_staged_files_returns_git_paths() -> None:
    with patch(
        "subprocess.run",
        return_value=subprocess.CompletedProcess([], 0, "one.py\ntwo.yml\n", ""),
    ):
        assert get_staged_files() == ["one.py", "two.yml"]


def test_get_staged_files_returns_empty_on_git_failure() -> None:
    with patch(
        "subprocess.run",
        return_value=subprocess.CompletedProcess([], 1, "", "failed"),
    ):
        assert get_staged_files() == []


@pytest.mark.parametrize(
    "error",
    [
        FileNotFoundError(),
        subprocess.TimeoutExpired(["git"], 30),
    ],
)
def test_get_staged_files_returns_empty_when_git_cannot_run(
    error: BaseException,
) -> None:
    with patch("subprocess.run", side_effect=error):
        assert get_staged_files() == []

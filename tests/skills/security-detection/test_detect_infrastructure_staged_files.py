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

from detect_infrastructure_test_helpers import detect_infrastructure, get_staged_files, mod

GitReadError = mod.GitReadError


def test_get_staged_files_returns_git_paths() -> None:
    with patch(
        "subprocess.run",
        return_value=subprocess.CompletedProcess([], 0, "one.py\ntwo.yml\n", ""),
    ):
        assert get_staged_files() == ["one.py", "two.yml"]


def test_get_staged_files_returns_empty_list_when_nothing_is_staged() -> None:
    """An empty answer from git is a real "nothing staged", not a failure."""
    with patch(
        "subprocess.run",
        return_value=subprocess.CompletedProcess([], 0, "", ""),
    ):
        assert get_staged_files() == []


def test_get_staged_files_raises_on_git_failure() -> None:
    with (
        patch(
            "subprocess.run",
            return_value=subprocess.CompletedProcess([], 1, "", "fatal: not a git repository"),
        ),
        pytest.raises(GitReadError, match="not a git repository"),
    ):
        get_staged_files()


def test_get_staged_files_raises_when_git_is_missing_from_path() -> None:
    with (
        patch("shutil.which", return_value=None),
        pytest.raises(GitReadError, match="git not found") as caught,
    ):
        get_staged_files()
    assert caught.value.state == "BLOCKED"


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (FileNotFoundError(), "tool.absent"),
        (subprocess.TimeoutExpired(["git"], 15), "timeout"),
    ],
)
def test_get_staged_files_raises_when_git_cannot_run(
    error: BaseException,
    reason: str,
) -> None:
    with (
        patch("subprocess.run", side_effect=error),
        pytest.raises(GitReadError) as caught,
    ):
        get_staged_files()
    assert caught.value.reason == reason
    assert caught.value.state == "BLOCKED"


def test_detect_infrastructure_propagates_the_staged_files_failure() -> None:
    with (
        patch("subprocess.run", side_effect=subprocess.TimeoutExpired(["git"], 15)),
        pytest.raises(GitReadError),
    ):
        detect_infrastructure(use_git_staged=True)


def test_get_staged_files_reads_the_given_repo_root(tmp_path: Path) -> None:
    with patch(
        "subprocess.run",
        return_value=subprocess.CompletedProcess([], 0, "a.py\n", ""),
    ) as run:
        assert get_staged_files(tmp_path) == ["a.py"]
    assert run.call_args.args[0][3] == str(tmp_path)


def test_detect_infrastructure_passes_repo_root_to_the_staged_read(tmp_path: Path) -> None:
    with patch(
        "subprocess.run",
        return_value=subprocess.CompletedProcess([], 0, ".github/workflows/ci.yml\n", ""),
    ) as run:
        result = detect_infrastructure(use_git_staged=True, repo_root=tmp_path)
    assert run.call_args.args[0][3] == str(tmp_path)
    assert result["highest_risk"] != "none"

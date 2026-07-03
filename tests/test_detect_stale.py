"""Tests for scripts/memory/detect_stale.py."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from scripts.memory import detect_stale


def test_get_git_last_modified_surfaces_timeout(
    capsys,
) -> None:
    with patch(
        "scripts.memory.detect_stale.subprocess.run",
        side_effect=subprocess.TimeoutExpired(["git"], 10),
    ):
        result = detect_stale.get_git_last_modified(Path(".serena/memories/a.md"))

    assert result is None
    assert "git log timed out" in capsys.readouterr().err


def test_get_git_last_modified_surfaces_missing_git(
    capsys,
) -> None:
    with patch(
        "scripts.memory.detect_stale.subprocess.run",
        side_effect=FileNotFoundError("git"),
    ):
        result = detect_stale.get_git_last_modified(Path(".serena/memories/a.md"))

    assert result is None
    assert "git executable not found" in capsys.readouterr().err

#!/usr/bin/env python3
"""main() tests for invoke_context_loader.py: no retrospective injection.

The SessionStart loader no longer injects the latest retrospective (ADR-008
amendment dated 2026-11-20; Issues #7471, #7472). These tests drive main()
end to end and pin that no retrospective content reaches stdout, that the
symlinked-ancestor guard holds at the main() level, and that both audit-log
branches are written.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

HOOKS_DIR = str(Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "SessionStart")
sys.path.insert(0, HOOKS_DIR)

import invoke_context_loader

MARKER = invoke_context_loader.RETRO_STATE_MARKER


def _date_days_ago(days: int) -> str:
    return (datetime.now(tz=UTC).date() - timedelta(days=days)).isoformat()


def _write_skeleton(retro_dir: Path, date_text: str) -> Path:
    """Write an unfilled auto-retro skeleton carrying the marker."""
    retro_dir.mkdir(parents=True, exist_ok=True)
    path = retro_dir / f"{date_text}-auto-retro.md"
    path.write_text(f"{MARKER}\n# Retrospective: {date_text}\n\nfilled content\n", encoding="utf-8")
    return path


def _symlink_or_skip(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("cannot create symlink on this platform")


def _run_main_with_project(project_dir: Path) -> str:
    """Run the hook against project_dir; return captured stdout."""
    captured = StringIO()
    with (
        patch("sys.stdin", StringIO("")),
        patch.object(invoke_context_loader, "get_project_directory", return_value=str(project_dir)),
        patch.object(invoke_context_loader, "skip_if_consumer_repo", return_value=False),
        patch("sys.stdout", captured),
    ):
        invoke_context_loader.main()
    return captured.getvalue()


def _write_retrospective(retro_dir: Path, filename: str, body: str) -> Path:
    retro_dir.mkdir(parents=True, exist_ok=True)
    path = retro_dir / filename
    path.write_text(body, encoding="utf-8")
    return path


def test_main_does_not_inject_retrospective_content(tmp_path: Path) -> None:
    """A fresh, filled retrospective is no longer injected into the session."""
    # Arrange
    (tmp_path / ".agents").mkdir()
    retro_dir = tmp_path / ".project-toolkit" / "retrospective"
    _write_retrospective(
        retro_dir,
        f"{_date_days_ago(0)}-sweep.md",
        "# Retrospective: sweep\n\nRETRO_BODY_SENTINEL\n",
    )

    # Act
    out = _run_main_with_project(tmp_path)

    # Assert
    assert "RETRO_BODY_SENTINEL" not in out
    assert "Latest Retrospective" not in out
    assert out == ""


def test_main_reminder_carries_no_retrospective_content(tmp_path: Path) -> None:
    """With a pending skeleton and a filled retro, only the reminder is emitted."""
    # Arrange
    (tmp_path / ".agents").mkdir()
    retro_dir = tmp_path / ".project-toolkit" / "retrospective"
    skeleton_date = _date_days_ago(0)
    _write_skeleton(retro_dir, skeleton_date)
    _write_retrospective(
        retro_dir,
        f"{_date_days_ago(1)}-sweep.md",
        "# Retrospective: sweep\n\nRETRO_BODY_SENTINEL\n",
    )

    # Act
    out = _run_main_with_project(tmp_path)

    # Assert
    assert out.startswith("## ⏳ 1 retro(s) need completion")
    assert "RETRO_BODY_SENTINEL" not in out
    assert "filled content" not in out


def test_main_emits_nothing_when_retro_dir_is_missing(tmp_path: Path) -> None:
    # Arrange
    (tmp_path / ".agents").mkdir()

    # Act
    out = _run_main_with_project(tmp_path)

    # Assert
    assert out == ""


def test_main_ignores_skeletons_behind_a_symlinked_project_toolkit(tmp_path: Path) -> None:
    """A symlinked ``.project-toolkit`` must not leak an outside skeleton (CWE-59)."""
    # Arrange
    project_dir = tmp_path / "project"
    (project_dir / ".agents").mkdir(parents=True)
    outside_toolkit = tmp_path / "outside-toolkit"
    _write_skeleton(outside_toolkit / "retrospective", _date_days_ago(0))
    _symlink_or_skip(project_dir / ".project-toolkit", outside_toolkit)

    # Act
    out = _run_main_with_project(project_dir)

    # Assert
    assert out == ""


def test_main_counts_skeletons_in_a_real_project_toolkit(tmp_path: Path) -> None:
    """Control for the symlink case: the same layout without a link is counted."""
    # Arrange
    project_dir = tmp_path / "project"
    (project_dir / ".agents").mkdir(parents=True)
    _write_skeleton(project_dir / ".project-toolkit" / "retrospective", _date_days_ago(0))

    # Act
    out = _run_main_with_project(project_dir)

    # Assert
    assert "1 retro(s) need completion" in out


def test_main_audit_log_records_pending_count(tmp_path: Path) -> None:
    # Arrange
    (tmp_path / ".agents").mkdir()
    _write_skeleton(tmp_path / ".project-toolkit" / "retrospective", _date_days_ago(0))

    # Act
    _run_main_with_project(tmp_path)

    # Assert
    logs = list((tmp_path / ".project-toolkit" / ".hook-state").glob("context-loader-*.log"))
    assert len(logs) == 1
    assert "Loaded: pending-retros:1" in logs[0].read_text(encoding="utf-8")


def test_main_audit_log_records_none_when_nothing_pending(tmp_path: Path) -> None:
    # Arrange
    (tmp_path / ".agents").mkdir()

    # Act
    _run_main_with_project(tmp_path)

    # Assert
    logs = list((tmp_path / ".project-toolkit" / ".hook-state").glob("context-loader-*.log"))
    assert len(logs) == 1
    assert "Loaded: (none)" in logs[0].read_text(encoding="utf-8")

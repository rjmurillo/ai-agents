#!/usr/bin/env python3
"""Tests for invoke_context_loader.py SessionStart hook.

Covers the pending-retro skeleton reminder added for Issue #2079: counting
unfilled skeletons by their RETRO-STATE marker, capping by filename date,
extracting fill dates, and surfacing the reminder in the injected context.
"""

from __future__ import annotations

import os
import sys
import time
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path
from unittest.mock import patch

HOOKS_DIR = str(
    Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "SessionStart"
)
sys.path.insert(0, HOOKS_DIR)

import invoke_context_loader  # noqa: E402

MARKER = invoke_context_loader.RETRO_STATE_MARKER


def _date_days_ago(days: int) -> str:
    return (datetime.now(tz=UTC).date() - timedelta(days=days)).isoformat()


def _write_skeleton(retro_dir: Path, date: str, *, filled: bool = False) -> Path:
    """Write an auto-retro file; unfilled carries the marker, filled does not."""
    retro_dir.mkdir(parents=True, exist_ok=True)
    path = retro_dir / f"{date}-auto-retro.md"
    body = f"# Retrospective: {date}\n\nfilled content\n"
    if not filled:
        body = f"{MARKER}\n" + body
    path.write_text(body, encoding="utf-8")
    return path


def _write_skeleton_file(
    retro_dir: Path, filename: str, *, filled: bool = False
) -> Path:
    retro_dir.mkdir(parents=True, exist_ok=True)
    path = retro_dir / filename
    body = f"# Retrospective: {filename}\n\nfilled content\n"
    if not filled:
        body = f"{MARKER}\n" + body
    path.write_text(body, encoding="utf-8")
    return path


def _age_file(path: Path, days_old: float) -> None:
    """Backdate a file's mtime by ``days_old`` days."""
    past = time.time() - days_old * 86400
    os.utime(path, (past, past))


# --- _count_pending_skeletons ---------------------------------------------


def test_counts_single_in_window_skeleton() -> None:
    # Arrange
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        retro_dir = Path(tmp) / "retrospective"
        skeleton_date = _date_days_ago(0)
        _write_skeleton(retro_dir, skeleton_date)

        # Act
        count, names = invoke_context_loader._count_pending_skeletons(retro_dir)

        # Assert
        assert count == 1
        assert names == [f"{skeleton_date}-auto-retro.md"]


def test_filled_retro_not_counted() -> None:
    # Arrange
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        retro_dir = Path(tmp) / "retrospective"
        _write_skeleton(retro_dir, _date_days_ago(0), filled=True)

        # Act
        count, names = invoke_context_loader._count_pending_skeletons(retro_dir)

        # Assert: a filled retro (no marker) is not pending
        assert count == 0
        assert names == []


def test_stale_skeleton_excluded_by_age_cap() -> None:
    # Arrange: marker present but filename date older than the 7-day window
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        retro_dir = Path(tmp) / "retrospective"
        _write_skeleton(retro_dir, _date_days_ago(30))

        # Act
        count, names = invoke_context_loader._count_pending_skeletons(
            retro_dir, max_age_days=7
        )

        # Assert
        assert count == 0
        assert names == []


def test_boundary_at_max_age_days_included() -> None:
    # Arrange: a skeleton dated on the age boundary is still counted
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        retro_dir = Path(tmp) / "retrospective"
        skeleton_date = _date_days_ago(7)
        _write_skeleton(retro_dir, skeleton_date)

        # Act
        count, names = invoke_context_loader._count_pending_skeletons(
            retro_dir, max_age_days=7
        )

        # Assert
        assert count == 1
        assert names == [f"{skeleton_date}-auto-retro.md"]


def test_undated_skeleton_falls_back_to_mtime_age_cap() -> None:
    # Arrange: non-standard skeleton names fall back to mtime for age capping
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        retro_dir = Path(tmp) / "retrospective"
        recent = _write_skeleton_file(retro_dir, "auto-retro.md")
        stale = _write_skeleton_file(retro_dir, "older-auto-retro.md")
        _age_file(recent, days_old=1)
        _age_file(stale, days_old=30)

        # Act
        count, names = invoke_context_loader._count_pending_skeletons(
            retro_dir, max_age_days=7
        )

        # Assert
        assert count == 1
        assert names == ["auto-retro.md"]


def test_missing_directory_yields_zero() -> None:
    # Arrange
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        missing = Path(tmp) / "does-not-exist"

        # Act
        count, names = invoke_context_loader._count_pending_skeletons(missing)

        # Assert: fail-open, no crash
        assert count == 0
        assert names == []


def test_unreadable_file_skipped_not_fatal() -> None:
    # Arrange: one good skeleton plus one that raises on read
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        retro_dir = Path(tmp) / "retrospective"
        good_date = _date_days_ago(0)
        bad_date = _date_days_ago(1)
        _write_skeleton(retro_dir, good_date)
        bad = retro_dir / f"{bad_date}-auto-retro.md"
        bad.write_text(f"{MARKER}\nbad", encoding="utf-8")

        real_open = Path.open

        def _selective_open(self: Path, *args: object, **kwargs: object) -> object:
            if self.name == bad.name:
                raise OSError("simulated unreadable file")
            return real_open(self, *args, **kwargs)

        # Act
        with patch.object(Path, "open", _selective_open):
            count, names = invoke_context_loader._count_pending_skeletons(retro_dir)

        # Assert: the bad file is skipped, the good one still counts
        assert count == 1
        assert names == [f"{good_date}-auto-retro.md"]


# --- _skeleton_dates ------------------------------------------------------


def test_skeleton_dates_extracts_and_dedupes() -> None:
    names = [
        "2026-06-03-auto-retro.md",
        "2026-06-03-manual-retro.md",
        "2026-06-01-auto-retro.md",
        "no-date-here.md",
    ]
    assert invoke_context_loader._skeleton_dates(names) == [
        "2026-06-03",
        "2026-06-01",
    ]


def test_skeleton_dates_empty_when_no_dates() -> None:
    assert invoke_context_loader._skeleton_dates(["weird.md"]) == []


# --- main(): reminder surfacing -------------------------------------------


def _run_main_with_project(project_dir: Path) -> str:
    """Run the hook against project_dir; return captured stdout."""
    captured = StringIO()
    with patch("sys.stdin", StringIO("")), patch.object(
        invoke_context_loader, "get_project_directory", return_value=str(project_dir)
    ), patch.object(
        invoke_context_loader, "skip_if_consumer_repo", return_value=False
    ), patch("sys.stdout", captured):
        invoke_context_loader.main()
    return captured.getvalue()


def test_main_surfaces_pending_reminder_with_fill_command() -> None:
    # Arrange
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        project_dir = Path(tmp)
        (project_dir / ".agents").mkdir()
        retro_dir = project_dir / ".agents" / "retrospective"
        skeleton_date = _date_days_ago(0)
        _write_skeleton(retro_dir, skeleton_date)

        # Act
        out = _run_main_with_project(project_dir)

        # Assert
        assert "1 retro(s) need completion" in out
        assert f"{skeleton_date}-auto-retro.md" in out
        assert f"/retro fill {skeleton_date}" in out


def test_main_surfaces_single_fill_example_for_multiple_pending_retros() -> None:
    # Arrange
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        project_dir = Path(tmp)
        (project_dir / ".agents").mkdir()
        retro_dir = project_dir / ".agents" / "retrospective"
        older_date = _date_days_ago(1)
        newer_date = _date_days_ago(0)
        _write_skeleton(retro_dir, older_date)
        _write_skeleton(retro_dir, newer_date)

        # Act
        out = _run_main_with_project(project_dir)

        # Assert
        assert "2 retro(s) need completion" in out
        assert f"Run `/retro fill {older_date}`" in out
        assert f"/retro fill {older_date}, {newer_date}" not in out
        assert f"Other available dates: {newer_date}." in out


def test_main_no_reminder_when_no_skeletons() -> None:
    # Arrange: a filled retro only, no pending skeletons
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        project_dir = Path(tmp)
        (project_dir / ".agents").mkdir()
        retro_dir = project_dir / ".agents" / "retrospective"
        _write_skeleton(retro_dir, _date_days_ago(0), filled=True)

        # Act
        out = _run_main_with_project(project_dir)

        # Assert: no nagging line when nothing is pending
        assert "need completion" not in out


def test_main_no_reminder_when_skeleton_stale() -> None:
    # Arrange: a marker-bearing but stale filename date must not nag
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        project_dir = Path(tmp)
        (project_dir / ".agents").mkdir()
        retro_dir = project_dir / ".agents" / "retrospective"
        _write_skeleton(retro_dir, _date_days_ago(30))

        # Act
        out = _run_main_with_project(project_dir)

        # Assert
        assert "need completion" not in out


if __name__ == "__main__":
    import unittest

    # Allow `python3 tests/hooks/test_context_loader.py` to run via pytest-style
    # functions by delegating to pytest when available.
    try:
        import pytest

        raise SystemExit(pytest.main([__file__, "-q"]))
    except ImportError:
        unittest.main()

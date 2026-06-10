#!/usr/bin/env python3
"""Tests for invoke_context_loader.py SessionStart hook.

The pending-retro skeleton reminder was removed for Issue #2531 (the Stop hook
no longer writes skeletons, so the SessionStart hook has nothing to nag about).
These tests assert the banner stays absent even when legacy marker-bearing
skeleton files are still on disk in a repo that pre-dates the removal.
"""

from __future__ import annotations

import os
import sys
import tempfile
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

# Legacy marker literal. The constant lived in invoke_context_loader before
# Issue #2531; it now only exists in the Stop hook for back-compat detection.
# We hardcode it here so these tests do not depend on the constant being
# re-exported by the SessionStart hook.
LEGACY_MARKER = "<!-- RETRO-STATE: skeleton-pending-fill -->"


def _date_days_ago(days: int) -> str:
    return (datetime.now(tz=UTC).date() - timedelta(days=days)).isoformat()


def _write_skeleton(retro_dir: Path, date: str, *, filled: bool = False) -> Path:
    """Write an auto-retro file; unfilled carries the legacy marker."""
    retro_dir.mkdir(parents=True, exist_ok=True)
    path = retro_dir / f"{date}-auto-retro.md"
    body = f"# Retrospective: {date}\n\nfilled content\n"
    if not filled:
        body = f"{LEGACY_MARKER}\n" + body
    path.write_text(body, encoding="utf-8")
    return path


def _age_file(path: Path, days_old: float) -> None:
    """Backdate a file's mtime by ``days_old`` days."""
    past = time.time() - days_old * 86400
    os.utime(path, (past, past))


# --- main(): pending-skeleton banner removal -----------------------------


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


def test_main_does_not_nag_when_legacy_skeleton_present_today() -> None:
    """A marker-bearing skeleton dated today must NOT surface a reminder."""
    with tempfile.TemporaryDirectory() as tmp:
        project_dir = Path(tmp)
        (project_dir / ".agents").mkdir()
        retro_dir = project_dir / ".agents" / "retrospective"
        skeleton_date = _date_days_ago(0)
        _write_skeleton(retro_dir, skeleton_date)

        out = _run_main_with_project(project_dir)

        assert "retro(s) need completion" not in out
        assert "Unfilled skeletons" not in out
        assert "/retro fill" not in out


def test_main_does_not_nag_when_multiple_legacy_skeletons_present() -> None:
    """Multiple unfilled skeletons (today + yesterday) must still stay silent."""
    with tempfile.TemporaryDirectory() as tmp:
        project_dir = Path(tmp)
        (project_dir / ".agents").mkdir()
        retro_dir = project_dir / ".agents" / "retrospective"
        _write_skeleton(retro_dir, _date_days_ago(1))
        _write_skeleton(retro_dir, _date_days_ago(0))

        out = _run_main_with_project(project_dir)

        assert "retro(s) need completion" not in out
        assert "Other available dates" not in out


def test_main_does_not_nag_when_skeleton_stale() -> None:
    """A marker-bearing skeleton dated long ago must NOT surface a reminder."""
    with tempfile.TemporaryDirectory() as tmp:
        project_dir = Path(tmp)
        (project_dir / ".agents").mkdir()
        retro_dir = project_dir / ".agents" / "retrospective"
        _write_skeleton(retro_dir, _date_days_ago(30))

        out = _run_main_with_project(project_dir)

        assert "retro(s) need completion" not in out


def test_main_does_not_nag_when_no_retros() -> None:
    """An empty retrospective dir must produce no reminder (sanity check)."""
    with tempfile.TemporaryDirectory() as tmp:
        project_dir = Path(tmp)
        (project_dir / ".agents").mkdir()
        retro_dir = project_dir / ".agents" / "retrospective"
        retro_dir.mkdir()

        out = _run_main_with_project(project_dir)

        assert "retro(s) need completion" not in out
        assert "Unfilled skeletons" not in out


def test_main_does_not_nag_when_only_filled_retros() -> None:
    """A filled retro (no marker) must produce no reminder."""
    with tempfile.TemporaryDirectory() as tmp:
        project_dir = Path(tmp)
        (project_dir / ".agents").mkdir()
        retro_dir = project_dir / ".agents" / "retrospective"
        _write_skeleton(retro_dir, _date_days_ago(0), filled=True)

        out = _run_main_with_project(project_dir)

        assert "retro(s) need completion" not in out


def test_removed_scanner_helpers_are_gone() -> None:
    """Confirm the dead-symbol surface from Issue #2531 stayed removed.

    A regression on this list would mean a future change re-imported the
    skeleton-scanning logic without re-introducing the banner contract.
    """
    removed = (
        "_count_pending_skeletons",
        "_is_pending_skeleton_recent",
        "_filename_date",
        "_skeleton_dates",
        "_pending_skeleton_summary",
        "RETRO_STATE_MARKER",
        "PENDING_RETRO_MAX_AGE_DAYS",
        "_RETRO_DATE_RE",
    )
    for name in removed:
        assert not hasattr(invoke_context_loader, name), (
            f"{name} reintroduced; the SessionStart pending-retro banner was "
            "removed for Issue #2531 and must stay removed."
        )


# --- Loaded retros still surface (independent of the removed nag) --------


def test_main_still_loads_latest_filled_retro() -> None:
    """The 'latest retrospective' auto-injection path is independent of the
    removed scanner and must still work for filled retros."""
    with tempfile.TemporaryDirectory() as tmp:
        project_dir = Path(tmp)
        (project_dir / ".agents").mkdir()
        retro_dir = project_dir / ".agents" / "retrospective"
        filled = _write_skeleton(retro_dir, _date_days_ago(0), filled=True)
        # Tick mtime so _find_latest_retrospective picks it up deterministically
        os.utime(filled, None)

        out = _run_main_with_project(project_dir)

        assert "Auto-loaded: Latest Retrospective" in out
        assert filled.name in out


if __name__ == "__main__":
    import unittest

    try:
        import pytest

        raise SystemExit(pytest.main([__file__, "-q"]))
    except ImportError:
        unittest.main()

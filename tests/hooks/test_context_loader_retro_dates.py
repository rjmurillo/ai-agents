#!/usr/bin/env python3
"""Tests for SessionStart/invoke_context_loader.py retrospective selection (#7227).

A git checkout stamps every file with one mtime, so the hook orders
retrospectives by the document's own date and refuses to inject one that is
older than the age cap.
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

HOOKS_DIR = str(Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "SessionStart")
sys.path.insert(0, HOOKS_DIR)

import invoke_context_loader

_TODAY = date(2026, 1, 15)


def _days_ago(days: int) -> str:
    return (datetime.now(tz=UTC).date() - timedelta(days=days)).isoformat()


# --- _find_latest_retrospective: order by the document's own date (#7227) --


def _write_retro(retro_dir: Path, name: str, body: str = "retro\n") -> Path:
    retro_dir.mkdir(parents=True, exist_ok=True)
    path = retro_dir / name
    path.write_text(body, encoding="utf-8")
    return path


def _stamp_all(paths: list[Path], mtime: float) -> None:
    """Give every file the same mtime, as a git checkout does."""
    for path in paths:
        os.utime(path, (mtime, mtime))


def _latest(
    retro_dir: Path,
    root: Path,
    max_age_days: int = invoke_context_loader.RETRO_MAX_AGE_DAYS,
) -> Path | None:
    return invoke_context_loader._find_latest_retrospective(
        retro_dir, root, max_age_days=max_age_days, today=_TODAY
    )


def test_identical_mtimes_newest_filename_date_wins(tmp_path: Path) -> None:
    retro_dir = tmp_path / "retrospective"
    paths = [
        _write_retro(retro_dir, "2026-01-02-b.md"),
        _write_retro(retro_dir, "2026-01-10-newest.md"),
        _write_retro(retro_dir, "2025-12-20-old.md"),
        _write_retro(retro_dir, "2026-01-05-mid.md"),
    ]
    _stamp_all(paths, 1_700_000_000)

    assert _latest(retro_dir, tmp_path) == retro_dir / "2026-01-10-newest.md"


def test_filename_date_beats_a_newer_mtime(tmp_path: Path) -> None:
    retro_dir = tmp_path / "retrospective"
    newest_by_date = _write_retro(retro_dir, "2026-01-10-new.md")
    stale_by_date = _write_retro(retro_dir, "2026-01-01-old.md")
    os.utime(newest_by_date, (1000, 1000))
    os.utime(stale_by_date, (9000, 9000))

    assert _latest(retro_dir, tmp_path) == newest_by_date


def test_header_date_used_when_filename_has_none(tmp_path: Path) -> None:
    retro_dir = tmp_path / "retrospective"
    old = _write_retro(retro_dir, "alpha.md", "# Old\n\n**Date**: 2026-01-03\n")
    new = _write_retro(retro_dir, "beta.md", "# New\n\n- **Date**: 2026-01-12\n")
    _stamp_all([old, new], 1_700_000_000)

    assert _latest(retro_dir, tmp_path) == new


def test_plain_date_header_is_recognized(tmp_path: Path) -> None:
    retro_dir = tmp_path / "retrospective"
    plain = _write_retro(retro_dir, "plain.md", "# T\nDate: 2026-01-11\n")

    assert _latest(retro_dir, tmp_path) == plain


def test_filename_date_and_header_date_files_are_ranked_together(tmp_path: Path) -> None:
    retro_dir = tmp_path / "retrospective"
    by_name = _write_retro(retro_dir, "2026-01-04-named.md")
    by_header = _write_retro(retro_dir, "headered.md", "**Date**: 2026-01-09\n")
    _stamp_all([by_name, by_header], 1_700_000_000)

    assert _latest(retro_dir, tmp_path) == by_header


def test_header_date_beyond_the_scan_window_is_ignored(tmp_path: Path) -> None:
    retro_dir = tmp_path / "retrospective"
    body = "filler\n" * 25 + "**Date**: 2026-01-12\n"
    _write_retro(retro_dir, "deep.md", body)

    assert _latest(retro_dir, tmp_path) is None


def test_mtime_only_breaks_a_tie_between_equal_dates(tmp_path: Path) -> None:
    retro_dir = tmp_path / "retrospective"
    older = _write_retro(retro_dir, "2026-01-10-a.md")
    newer = _write_retro(retro_dir, "2026-01-10-b.md")
    os.utime(older, (1000, 1000))
    os.utime(newer, (2000, 2000))

    assert _latest(retro_dir, tmp_path) == newer


def test_no_parseable_dates_injects_nothing(tmp_path: Path) -> None:
    retro_dir = tmp_path / "retrospective"
    _write_retro(retro_dir, "phase1-remediation.md", "# No date here\n")
    _write_retro(retro_dir, "notes.md", "Date: soon\n")
    _write_retro(retro_dir, "2026-13-45-bad-calendar.md", "# Bad filename date\n")

    assert _latest(retro_dir, tmp_path) is None


def test_invalid_calendar_header_is_undated(tmp_path: Path) -> None:
    retro_dir = tmp_path / "retrospective"
    _write_retro(retro_dir, "bad.md", "**Date**: 2026-02-31\n")

    assert _latest(retro_dir, tmp_path) is None


def test_newest_older_than_age_cap_injects_nothing(tmp_path: Path) -> None:
    retro_dir = tmp_path / "retrospective"
    stale = _TODAY - timedelta(days=invoke_context_loader.RETRO_MAX_AGE_DAYS + 1)
    _write_retro(retro_dir, f"{stale.isoformat()}-stale.md")

    assert _latest(retro_dir, tmp_path) is None


def test_newest_exactly_at_age_cap_is_injected(tmp_path: Path) -> None:
    retro_dir = tmp_path / "retrospective"
    edge = _TODAY - timedelta(days=invoke_context_loader.RETRO_MAX_AGE_DAYS)
    path = _write_retro(retro_dir, f"{edge.isoformat()}-edge.md")

    assert _latest(retro_dir, tmp_path) == path


def test_age_cap_is_adjustable(tmp_path: Path) -> None:
    retro_dir = tmp_path / "retrospective"
    path = _write_retro(retro_dir, "2026-01-05-ten-days.md")

    assert _latest(retro_dir, tmp_path, max_age_days=5) is None
    assert _latest(retro_dir, tmp_path, max_age_days=10) == path


def test_default_age_cap_is_thirty_days() -> None:
    assert invoke_context_loader.RETRO_MAX_AGE_DAYS == 30


def test_age_cap_uses_the_real_clock_when_today_is_omitted(tmp_path: Path) -> None:
    retro_dir = tmp_path / "retrospective"
    fresh = _write_retro(retro_dir, f"{_days_ago(1)}-fresh.md")
    _write_retro(retro_dir, "2025-12-16-ancient.md")

    latest = invoke_context_loader._find_latest_retrospective(retro_dir, tmp_path)

    assert latest == fresh


def test_index_md_is_ignored_even_when_it_carries_the_newest_date(tmp_path: Path) -> None:
    retro_dir = tmp_path / "retrospective"
    _write_retro(retro_dir, "INDEX.md", "**Date**: 2026-01-14\n")
    real = _write_retro(retro_dir, "2026-01-02-real.md")

    assert _latest(retro_dir, tmp_path) == real


def test_only_index_md_injects_nothing(tmp_path: Path) -> None:
    retro_dir = tmp_path / "retrospective"
    _write_retro(retro_dir, "INDEX.md", "**Date**: 2026-01-14\n")

    assert _latest(retro_dir, tmp_path) is None


def test_undated_file_never_beats_a_dated_one(tmp_path: Path) -> None:
    retro_dir = tmp_path / "retrospective"
    undated = _write_retro(retro_dir, "undated.md", "# nothing\n")
    dated = _write_retro(retro_dir, "2026-01-02-dated.md")
    os.utime(dated, (1000, 1000))
    os.utime(undated, (9000, 9000))

    assert _latest(retro_dir, tmp_path) == dated


def test_unstattable_file_is_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    retro_dir = tmp_path / "retrospective"
    good = _write_retro(retro_dir, "2026-01-02-good.md")
    bad = _write_retro(retro_dir, "2026-01-10-bad.md")
    real_stat = Path.stat

    def flaky_stat(self: Path, *args: Any, **kwargs: Any):
        if self.name == bad.name:
            raise OSError("raced with deletion")
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", flaky_stat)

    assert _latest(retro_dir, tmp_path) == good


def test_header_read_failure_counts_as_undated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    retro_dir = tmp_path / "retrospective"
    path = _write_retro(retro_dir, "headered.md", "**Date**: 2026-01-12\n")
    real_open = Path.open

    def failing_open(self: Path, *args: Any, **kwargs: Any):
        if self == path:
            raise PermissionError("denied")
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", failing_open)

    assert _latest(retro_dir, tmp_path) is None


def test_main_injects_the_newest_dated_retrospective_with_equal_mtimes(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    retro_dir = tmp_path / ".project-toolkit" / "retrospective"
    old = _write_retro(retro_dir, "2025-12-16-ancient.md", "ANCIENT_BODY\n")
    new = _write_retro(retro_dir, f"{_days_ago(2)}-recent.md", "RECENT_BODY\n")
    _stamp_all([old, new], 1_700_000_000)

    with (
        patch.object(invoke_context_loader, "skip_if_consumer_repo", return_value=False),
        patch.object(invoke_context_loader, "get_project_directory", return_value=str(tmp_path)),
    ):
        invoke_context_loader.main()

    out = capsys.readouterr().out
    assert "RECENT_BODY" in out
    assert "ANCIENT_BODY" not in out


def test_main_injects_nothing_when_every_retrospective_is_stale(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    retro_dir = tmp_path / ".project-toolkit" / "retrospective"
    _write_retro(retro_dir, "2025-12-16-ancient.md", "ANCIENT_BODY\n")

    with (
        patch.object(invoke_context_loader, "skip_if_consumer_repo", return_value=False),
        patch.object(invoke_context_loader, "get_project_directory", return_value=str(tmp_path)),
    ):
        invoke_context_loader.main()

    out = capsys.readouterr().out
    assert "ANCIENT_BODY" not in out
    assert "No context files found" in out

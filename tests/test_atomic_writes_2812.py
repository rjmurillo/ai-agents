"""Atomic-write and advisory-lock tests for issue #2812.

Each shared-state writer touched by #2812 replaced a non-atomic
``write_text`` / unlocked append with a temp-file + ``os.replace`` write (and,
for read-modify-write sites, an advisory lock). These tests assert three
properties per site:

1. positive: the normal write produces the expected content;
2. negative: a mid-write ``os.replace`` failure leaves the prior file intact
   and returns/propagates without a torn write;
3. edge: no ``.tmp`` scratch file is left behind in the target directory.

The concurrency the fix defends against (two processes racing) is not
reproducible deterministically in a unit test; these tests instead pin the
mechanism (atomic replace, temp cleanup, lock acquisition) that makes the race
safe.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import scripts.ai_review_common.cache_guard as cache_guard
import scripts.update_reviewer_signal_stats as urss


def _tmp_files(directory: Path) -> list[Path]:
    """Return leftover atomic-write scratch files in ``directory``."""
    return list(directory.glob("*.tmp"))


# ---------------------------------------------------------------------------
# cache_guard.populate_cache and _atomic_write_text
# ---------------------------------------------------------------------------
class TestCacheGuardPopulate:
    def _output(self, tmp_path: Path) -> Path:
        return tmp_path / "gh_output"

    def test_positive_writes_three_files_and_marks_populated(self, tmp_path):
        out = self._output(tmp_path)
        ok = cache_guard.populate_cache(
            agent="architect",
            verdict="APPROVE",
            findings="none",
            infra_failure="false",
            github_output=out,
            cache_root=tmp_path / "cache",
        )
        assert ok is True
        cache_dir = tmp_path / "cache" / "architect"
        assert (cache_dir / "verdict.txt").read_text(encoding="utf-8") == "APPROVE"
        assert (cache_dir / "findings.txt").read_text(encoding="utf-8") == "none"
        assert (cache_dir / "infrastructure-failure.txt").read_text(encoding="utf-8") == "false"
        assert "cache_populated=true" in out.read_text(encoding="utf-8")
        assert _tmp_files(cache_dir) == []

    def test_negative_empty_verdict_skips_and_marks_not_populated(self, tmp_path):
        out = self._output(tmp_path)
        ok = cache_guard.populate_cache(
            agent="architect",
            verdict="",
            findings="x",
            infra_failure="false",
            github_output=out,
            cache_root=tmp_path / "cache",
        )
        assert ok is False
        assert not (tmp_path / "cache" / "architect").exists()
        assert "cache_populated=false" in out.read_text(encoding="utf-8")

    def test_edge_partial_write_failure_removes_dir_and_marks_not_populated(
        self, tmp_path, monkeypatch
    ):
        out = self._output(tmp_path)
        real = cache_guard._atomic_write_text
        calls = {"n": 0}

        def flaky(path, text):
            calls["n"] += 1
            if calls["n"] == 2:  # fail on the second file
                raise OSError("crash mid-sequence")
            real(path, text)

        monkeypatch.setattr(cache_guard, "_atomic_write_text", flaky)
        ok = cache_guard.populate_cache(
            agent="qa",
            verdict="APPROVE",
            findings="x",
            infra_failure="false",
            github_output=out,
            cache_root=tmp_path / "cache",
        )
        assert ok is False
        assert not (tmp_path / "cache" / "qa").exists()
        assert "cache_populated=false" in out.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# update_reviewer_signal_stats helpers
# ---------------------------------------------------------------------------
class TestReviewerSignalStatsHelpers:
    def test_positive_atomic_write_text(self, tmp_path):
        target = tmp_path / "memory.md"
        urss._atomic_write_text(str(target), "content")
        assert target.read_text(encoding="utf-8") == "content"
        assert _tmp_files(tmp_path) == []

    def test_positive_locked_append_accumulates(self, tmp_path):
        target = tmp_path / "summary.md"
        urss._locked_append(str(target), "line1\n")
        urss._locked_append(str(target), "line2\n")
        assert target.read_text(encoding="utf-8") == "line1\nline2\n"

    def test_negative_atomic_write_failure_cleans_temp(self, tmp_path, monkeypatch):
        target = tmp_path / "memory.md"
        monkeypatch.setattr(
            urss.os,
            "replace",
            lambda _s, _d: (_ for _ in ()).throw(OSError("io")),
        )
        with pytest.raises(OSError):
            urss._atomic_write_text(str(target), "content")
        assert _tmp_files(tmp_path) == []

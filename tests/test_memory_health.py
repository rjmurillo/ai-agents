"""Tests for memory health reporting and staleness detection."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from scripts.memory_enhancement.models import (
    Citation,
    CitationStatus,
    HealthReport,
    MemoryWithCitations,
    SourceType,
)
from scripts.memory_enhancement.health import (
    detect_stale_memories,
    format_report,
    generate_health_report,
)


class TestGenerateHealthReport:
    """Generate aggregate health reports from memory directories."""

    @pytest.mark.unit
    def test_empty_directory(self, tmp_path):
        report = generate_health_report(tmp_path, tmp_path)
        assert report.total_memories == 0
        assert report.health_score == 1.0

    @pytest.mark.unit
    def test_with_valid_citations(self, tmp_path):
        (tmp_path / "exists.py").write_text("content\n")
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        (mem_dir / "m1.md").write_text(
            "# M1 (2026-01-01)\n\n[cite:file](exists.py) - ref\n"
        )
        report = generate_health_report(mem_dir, tmp_path)
        assert report.total_memories == 1
        assert report.total_citations == 1
        assert report.valid_citations == 1

    @pytest.mark.unit
    def test_with_broken_citations(self, tmp_path):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        (mem_dir / "m1.md").write_text(
            "# M1 (2026-01-01)\n\n[cite:file](missing.py) - ref\n"
        )
        report = generate_health_report(mem_dir, tmp_path)
        assert report.broken_citations >= 1
        assert report.health_score < 1.0


class TestDetectStaleMemories:
    """Detect memories that are old or have broken citations."""

    @pytest.mark.unit
    def test_old_memory_detected(self, tmp_path):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        old_date = (datetime.now(timezone.utc) - timedelta(days=60)).strftime("%Y-%m-%d")
        (mem_dir / "old.md").write_text(f"# Old ({old_date})\n\nContent\n")
        stale = detect_stale_memories(mem_dir, tmp_path, max_age_days=30)
        assert "old" in stale

    @pytest.mark.unit
    def test_recent_memory_not_stale(self, tmp_path):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        (mem_dir / "fresh.md").write_text(f"# Fresh ({today})\n\nContent\n")
        stale = detect_stale_memories(mem_dir, tmp_path, max_age_days=30)
        # Fresh memory with no broken citations should not be stale
        assert "fresh" not in stale

    @pytest.mark.unit
    def test_memory_with_broken_citation_detected(self, tmp_path):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        (mem_dir / "broken.md").write_text(
            f"# Broken ({today})\n\n[cite:file](nonexistent.py) - ref\n"
        )
        stale = detect_stale_memories(mem_dir, tmp_path, max_age_days=30)
        assert "broken" in stale


class TestFormatReport:
    """Format HealthReport as markdown."""

    @pytest.mark.unit
    def test_format_basic_report(self):
        report = HealthReport(
            total_memories=5,
            total_citations=10,
            valid_citations=8,
            stale_citations=1,
            broken_citations=1,
            unverified_citations=0,
            health_score=0.75,
            stale_memories=["old-mem"],
            recommendations=["Fix 1 broken citation(s)."],
        )
        text = format_report(report)
        assert "Memory Health Report" in text
        assert "75.0%" in text
        assert "old-mem" in text
        assert "Fix 1 broken citation" in text

    @pytest.mark.unit
    def test_format_empty_report(self):
        report = HealthReport(
            total_memories=0,
            total_citations=0,
            valid_citations=0,
            stale_citations=0,
            broken_citations=0,
            unverified_citations=0,
            health_score=1.0,
            stale_memories=[],
            recommendations=[],
        )
        text = format_report(report)
        assert "100.0%" in text
        assert "Stale Memories" not in text

"""Tests for memory health reporting and staleness detection."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from memory_enhancement.health import (
    _calculate_health_score,
    detect_stale_memories,
    format_report,
    generate_health_report,
)
from memory_enhancement.models import (
    HealthReport,
)


class TestCalculateHealthScore:
    """Unit tests for _calculate_health_score covering all branches."""

    @pytest.mark.unit
    def test_empty_corpus_scores_one(self):
        """Empty corpus (no memories) is vacuously healthy."""
        counts = {"total": 0, "valid": 0, "stale": 0, "broken": 0, "unverified": 0}
        assert _calculate_health_score(counts, total_memories=0) == 1.0

    @pytest.mark.unit
    def test_memories_with_no_citations_score_zero(self):
        """Memories exist but have no citations: score is 0.0, not vacuously 1.0."""
        counts = {"total": 0, "valid": 0, "stale": 0, "broken": 0, "unverified": 0}
        assert _calculate_health_score(counts, total_memories=878) == 0.0

    @pytest.mark.unit
    def test_all_valid_citations_score_one(self):
        """Corpus with all valid citations scores 1.0."""
        counts = {"total": 5, "valid": 5, "stale": 0, "broken": 0, "unverified": 0}
        assert _calculate_health_score(counts, total_memories=2) == 1.0

    @pytest.mark.unit
    def test_all_broken_citations_score_zero(self):
        """Corpus with all broken citations scores 0.0."""
        counts = {"total": 4, "valid": 0, "stale": 0, "broken": 4, "unverified": 0}
        assert _calculate_health_score(counts, total_memories=2) == 0.0

    @pytest.mark.unit
    def test_mixed_corpus_scores_between_zero_and_one(self):
        """Mixed valid/broken corpus scores between 0 and 1."""
        counts = {"total": 4, "valid": 2, "stale": 0, "broken": 2, "unverified": 0}
        score = _calculate_health_score(counts, total_memories=2)
        assert 0.0 < score < 1.0

    @pytest.mark.unit
    def test_stale_citations_contribute_half(self):
        """Stale citations count 0.5 each toward the weighted score."""
        counts = {"total": 4, "valid": 0, "stale": 4, "broken": 0, "unverified": 0}
        score = _calculate_health_score(counts, total_memories=2)
        assert score == pytest.approx(0.5)

    @pytest.mark.unit
    def test_score_clamped_to_one(self):
        """Score is capped at 1.0 even with unexpected over-count."""
        counts = {"total": 1, "valid": 2, "stale": 0, "broken": 0, "unverified": 0}
        assert _calculate_health_score(counts, total_memories=1) == 1.0


class TestGenerateHealthReport:
    """Generate aggregate health reports from memory directories."""

    @pytest.mark.unit
    def test_empty_directory(self, tmp_path):
        report = generate_health_report(tmp_path, tmp_path)
        assert report.total_memories == 0
        assert report.health_score == 1.0

    @pytest.mark.unit
    def test_memories_with_no_citations_not_healthy(self, tmp_path):
        """Regression for issue #3980: 878 memories with 0 citations must not score 1.0."""
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        (mem_dir / "m1.md").write_text("# M1 (2026-01-01)\n\nNo citations here.\n")
        report = generate_health_report(mem_dir, tmp_path)
        assert report.total_memories == 1
        assert report.total_citations == 0
        assert report.health_score == 0.0

    @pytest.mark.unit
    def test_with_valid_citations(self, tmp_path):
        (tmp_path / "exists.py").write_text("content\n")
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        (mem_dir / "m1.md").write_text("# M1 (2026-01-01)\n\n[cite:file](exists.py) - ref\n")
        report = generate_health_report(mem_dir, tmp_path)
        assert report.total_memories == 1
        assert report.total_citations == 1
        assert report.valid_citations == 1

    @pytest.mark.unit
    def test_with_broken_citations(self, tmp_path):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        (mem_dir / "m1.md").write_text("# M1 (2026-01-01)\n\n[cite:file](missing.py) - ref\n")
        report = generate_health_report(mem_dir, tmp_path)
        assert report.broken_citations >= 1
        assert report.health_score < 1.0


class TestDetectStaleMemories:
    """Detect memories that are old or have broken citations."""

    @pytest.mark.unit
    def test_old_memory_detected(self, tmp_path):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        old_date = (datetime.now(UTC) - timedelta(days=60)).strftime("%Y-%m-%d")
        (mem_dir / "old.md").write_text(f"# Old ({old_date})\n\nContent\n")
        stale = detect_stale_memories(mem_dir, tmp_path, max_age_days=30)
        assert "old" in stale

    @pytest.mark.unit
    def test_recent_memory_not_stale(self, tmp_path):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        (mem_dir / "fresh.md").write_text(f"# Fresh ({today})\n\nContent\n")
        stale = detect_stale_memories(mem_dir, tmp_path, max_age_days=30)
        # Fresh memory with no broken citations should not be stale
        assert "fresh" not in stale

    @pytest.mark.unit
    def test_memory_with_broken_citation_detected(self, tmp_path):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        today = datetime.now(UTC).strftime("%Y-%m-%d")
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


class TestDocumentationMatchesScoring:
    """Guard the SKILL.md health_score prose against the code it describes.

    PR #4008 documented ``1.0 when there are none`` while PR #4003 changed the
    nonempty-corpus-with-no-citations case to 0.0. The two PRs touched disjoint
    files, so git merged them without a conflict and the documentation was left
    asserting the opposite of the code. Prose and behavior are checked together
    here because nothing else compares them.
    """

    SKILL_PATHS = (
        Path(".claude/skills/memory-enhancement/SKILL.md"),
        Path("src/copilot-cli/skills/memory-enhancement/SKILL.md"),
    )

    def _repo_root(self) -> Path:
        return Path(__file__).resolve().parents[1]

    @pytest.mark.unit
    def test_documented_empty_corpus_score_matches_code(self):
        counts = {"total": 0, "valid": 0, "stale": 0, "broken": 0, "unverified": 0}
        assert _calculate_health_score(counts, total_memories=0) == 1.0
        for rel in self.SKILL_PATHS:
            text = (self._repo_root() / rel).read_text(encoding="utf-8")
            assert "1.0 for an empty corpus" in text, f"{rel} does not document the 1.0 case"

    @pytest.mark.unit
    def test_documented_uncited_corpus_score_matches_code(self):
        counts = {"total": 0, "valid": 0, "stale": 0, "broken": 0, "unverified": 0}
        assert _calculate_health_score(counts, total_memories=878) == 0.0
        for rel in self.SKILL_PATHS:
            text = (self._repo_root() / rel).read_text(encoding="utf-8")
            assert "0.0 when memories exist but carry no citations" in text, (
                f"{rel} does not document the 0.0 case"
            )

    @pytest.mark.unit
    def test_superseded_claim_is_absent(self):
        """The pre-#4003 wording must not survive anywhere in the two mirrors."""
        for rel in self.SKILL_PATHS:
            text = (self._repo_root() / rel).read_text(encoding="utf-8")
            assert "total`; 1.0 when there are none)" not in text, (
                f"{rel} still carries the superseded health_score claim"
            )

"""Tests for confidence scoring of memories."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from scripts.memory_enhancement.models import (
    Citation,
    LinkType,
    MemoryLink,
    MemoryWithCitations,
    SourceType,
    VerificationResult,
)
from scripts.memory_enhancement.confidence import (
    calculate_confidence,
    update_confidence_scores,
)


def _make_memory(
    days_old: int = 0,
    days_since_update: int = 0,
    num_links: int = 0,
) -> MemoryWithCitations:
    now = datetime.now(timezone.utc)
    links = [
        MemoryLink(link_type=LinkType.RELATED_TO, target_id=f"link-{i}", context="")
        for i in range(num_links)
    ]
    return MemoryWithCitations(
        memory_id="test",
        title="Test",
        content="body",
        created_at=now - timedelta(days=days_old),
        updated_at=now - timedelta(days=days_since_update),
        links=links,
    )


def _make_results(
    num_valid: int, num_invalid: int
) -> list[VerificationResult]:
    results: list[VerificationResult] = []
    for i in range(num_valid):
        c = Citation(source_type=SourceType.FILE, target=f"v{i}.py", context="")
        results.append(VerificationResult(citation=c, is_valid=True, reason="ok"))
    for i in range(num_invalid):
        c = Citation(source_type=SourceType.FILE, target=f"i{i}.py", context="")
        results.append(VerificationResult(citation=c, is_valid=False, reason="missing"))
    return results


class TestCalculateConfidence:
    """Confidence scoring based on multiple weighted factors."""

    @pytest.mark.unit
    def test_perfect_score(self):
        memory = _make_memory(days_old=0, days_since_update=0, num_links=10)
        results = _make_results(5, 0)
        score = calculate_confidence(memory, results)
        assert score == pytest.approx(1.0, abs=0.01)

    @pytest.mark.unit
    def test_no_citations_still_scores(self):
        memory = _make_memory(days_old=0, days_since_update=0)
        score = calculate_confidence(memory, [])
        # validity=1.0, recency=1.0, links=0.0, age=1.0
        assert score > 0.5

    @pytest.mark.unit
    def test_all_invalid_citations(self):
        memory = _make_memory(days_old=0, days_since_update=0)
        results = _make_results(0, 5)
        score = calculate_confidence(memory, results)
        assert score < 0.5

    @pytest.mark.unit
    def test_old_memory_lower_score(self):
        recent = _make_memory(days_old=1, days_since_update=1, num_links=5)
        old = _make_memory(days_old=300, days_since_update=80, num_links=5)
        results = _make_results(3, 0)
        recent_score = calculate_confidence(recent, results)
        old_score = calculate_confidence(old, results)
        assert recent_score > old_score

    @pytest.mark.unit
    def test_more_links_higher_score(self):
        few_links = _make_memory(num_links=1)
        many_links = _make_memory(num_links=10)
        results = _make_results(3, 0)
        few_score = calculate_confidence(few_links, results)
        many_score = calculate_confidence(many_links, results)
        assert many_score > few_score

    @pytest.mark.unit
    def test_score_clamped_to_unit_range(self):
        memory = _make_memory(days_old=1000, days_since_update=500)
        results = _make_results(0, 10)
        score = calculate_confidence(memory, results)
        assert 0.0 <= score <= 1.0


class TestUpdateConfidenceScores:
    """Batch confidence recalculation across a directory."""

    @pytest.mark.unit
    def test_update_scores(self, tmp_path):
        (tmp_path / "a.md").write_text("# A (2026-01-01)\n\nContent\n")
        (tmp_path / "b.md").write_text("# B (2026-01-02)\n\nContent\n")
        scores = update_confidence_scores(tmp_path, tmp_path)
        assert "a" in scores
        assert "b" in scores
        assert all(0.0 <= s <= 1.0 for s in scores.values())

    @pytest.mark.unit
    def test_empty_directory(self, tmp_path):
        scores = update_confidence_scores(tmp_path, tmp_path)
        assert scores == {}

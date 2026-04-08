"""Tests for memory enhancement data models."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from memory_enhancement.models import (
    Citation,
    CitationStatus,
    HealthReport,
    LinkType,
    MemoryLink,
    MemoryWithCitations,
    SourceType,
    VerificationResult,
)


class TestSourceType:
    """SourceType enum contains all expected members."""

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "value,expected",
        [
            ("file", SourceType.FILE),
            ("function", SourceType.FUNCTION),
            ("issue", SourceType.ISSUE),
            ("pr", SourceType.PR),
            ("adr", SourceType.ADR),
            ("memory", SourceType.MEMORY),
            ("url", SourceType.URL),
        ],
    )
    def test_source_type_values(self, value, expected):
        assert SourceType(value) == expected

    @pytest.mark.unit
    def test_invalid_source_type_raises(self):
        with pytest.raises(ValueError):
            SourceType("invalid")


class TestCitationStatus:
    """CitationStatus enum contains all expected members."""

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "value",
        ["valid", "stale", "broken", "unverified"],
    )
    def test_citation_status_values(self, value):
        assert CitationStatus(value).value == value


class TestLinkType:
    """LinkType enum contains all expected members."""

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "value",
        ["depends_on", "related_to", "supersedes", "contradicts", "refines"],
    )
    def test_link_type_values(self, value):
        assert LinkType(value).value == value


class TestCitation:
    """Citation dataclass is immutable and stores expected fields."""

    @pytest.mark.unit
    def test_create_citation(self):
        c = Citation(
            source_type=SourceType.FILE,
            target="scripts/validate.py:42",
            context="validation logic",
        )
        assert c.source_type == SourceType.FILE
        assert c.target == "scripts/validate.py:42"
        assert c.context == "validation logic"
        assert c.verified_at is None
        assert c.status == CitationStatus.UNVERIFIED

    @pytest.mark.unit
    def test_citation_is_frozen(self):
        c = Citation(source_type=SourceType.FILE, target="f.py", context="")
        with pytest.raises(AttributeError):
            c.target = "other.py"

    @pytest.mark.unit
    def test_citation_empty_target_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            Citation(source_type=SourceType.FILE, target="", context="")

    @pytest.mark.unit
    def test_citation_status_verified_at_consistency(self):
        """Non-UNVERIFIED status without verified_at raises."""
        with pytest.raises(ValueError, match="verified_at"):
            Citation(
                source_type=SourceType.FILE,
                target="f.py",
                context="",
                status=CitationStatus.VALID,
                verified_at=None,
            )


    @pytest.mark.unit
    def test_citation_unverified_with_verified_at_raises(self):
        with pytest.raises(ValueError, match="unverified"):
            Citation(
                source_type=SourceType.FILE,
                target="f.py",
                context="",
                status=CitationStatus.UNVERIFIED,
                verified_at=datetime.now(UTC),
            )


class TestMemoryLink:
    """MemoryLink dataclass stores relationship data."""

    @pytest.mark.unit
    def test_create_link(self):
        link = MemoryLink(
            link_type=LinkType.DEPENDS_ON,
            target_id="other-memory",
            context="needed for context",
        )
        assert link.link_type == LinkType.DEPENDS_ON
        assert link.target_id == "other-memory"

    @pytest.mark.unit
    def test_empty_target_id_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            MemoryLink(
                link_type=LinkType.DEPENDS_ON,
                target_id="",
                context="",
            )


class TestVerificationResult:
    """VerificationResult captures verification outcome."""

    @pytest.mark.unit
    def test_create_result(self):
        c = Citation(source_type=SourceType.FILE, target="f.py", context="")
        now = datetime.now(UTC)
        r = VerificationResult(
            citation=c, is_valid=True, reason="File exists", checked_at=now
        )
        assert r.is_valid is True
        assert r.reason == "File exists"
        assert r.checked_at == now

    @pytest.mark.unit
    def test_default_checked_at(self):
        c = Citation(source_type=SourceType.FILE, target="f.py", context="")
        r = VerificationResult(citation=c, is_valid=False, reason="Not found")
        assert r.checked_at is not None


class TestMemoryWithCitations:
    """MemoryWithCitations provides behavior methods over citation data."""

    def _make_memory(self, statuses: list[CitationStatus]) -> MemoryWithCitations:
        now = datetime.now(UTC)
        citations = [
            Citation(
                source_type=SourceType.FILE,
                target=f"f{i}.py",
                context="",
                status=status,
                verified_at=now if status != CitationStatus.UNVERIFIED else None,
            )
            for i, status in enumerate(statuses)
        ]
        return MemoryWithCitations(
            memory_id="test",
            title="Test",
            content="body",
            citations=citations,
        )

    @pytest.mark.unit
    def test_has_stale_citations_true(self):
        m = self._make_memory([CitationStatus.VALID, CitationStatus.STALE])
        assert m.has_stale_citations() is True

    @pytest.mark.unit
    def test_has_stale_citations_false(self):
        m = self._make_memory([CitationStatus.VALID])
        assert m.has_stale_citations() is False

    @pytest.mark.unit
    def test_has_broken_citations(self):
        m = self._make_memory([CitationStatus.BROKEN])
        assert m.has_broken_citations() is True

    @pytest.mark.unit
    def test_citation_validity_ratio(self):
        m = self._make_memory([CitationStatus.VALID, CitationStatus.BROKEN])
        assert m.citation_validity_ratio() == pytest.approx(0.5)

    @pytest.mark.unit
    def test_citation_validity_ratio_no_citations(self):
        m = self._make_memory([])
        assert m.citation_validity_ratio() == 1.0

    @pytest.mark.unit
    def test_unverified_citations(self):
        m = self._make_memory([CitationStatus.UNVERIFIED, CitationStatus.VALID])
        result = m.unverified_citations()
        assert len(result) == 1
        assert result[0].status == CitationStatus.UNVERIFIED


class TestMemoryWithCitationsPostInit:
    """MemoryWithCitations __post_init__ validation."""

    @pytest.mark.unit
    def test_empty_memory_id_raises(self):
        with pytest.raises(ValueError, match="memory_id"):
            MemoryWithCitations(memory_id="", title="T", content="C")

    @pytest.mark.unit
    def test_invalid_confidence_raises(self):
        with pytest.raises(ValueError, match="confidence"):
            MemoryWithCitations(
                memory_id="t", title="T", content="C", confidence=1.5
            )

    @pytest.mark.unit
    def test_updated_before_created_raises(self):
        now = datetime.now(UTC)
        with pytest.raises(ValueError, match="updated_at"):
            MemoryWithCitations(
                memory_id="t",
                title="T",
                content="C",
                created_at=now,
                updated_at=now - timedelta(days=1),
            )

    @pytest.mark.unit
    def test_citations_converted_to_tuple(self):
        m = MemoryWithCitations(
            memory_id="t",
            title="T",
            content="C",
            citations=[
                Citation(source_type=SourceType.FILE, target="f.py", context="")
            ],
        )
        assert isinstance(m.citations, tuple)

    @pytest.mark.unit
    def test_links_converted_to_tuple(self):
        m = MemoryWithCitations(
            memory_id="t",
            title="T",
            content="C",
            links=[
                MemoryLink(
                    link_type=LinkType.RELATED_TO,
                    target_id="other",
                    context="",
                )
            ],
        )
        assert isinstance(m.links, tuple)


class TestHealthReport:
    """HealthReport is an immutable aggregate."""

    @pytest.mark.unit
    def test_create_report(self):
        r = HealthReport(
            total_memories=10,
            total_citations=20,
            valid_citations=15,
            stale_citations=3,
            broken_citations=1,
            unverified_citations=1,
            health_score=0.75,
            stale_memories=["mem-1"],
            recommendations=["Fix broken citations"],
        )
        assert r.total_memories == 10
        assert r.health_score == 0.75
        assert len(r.recommendations) == 1
        assert isinstance(r.stale_memories, tuple)
        assert isinstance(r.recommendations, tuple)

    @pytest.mark.unit
    def test_negative_count_raises(self):
        with pytest.raises(ValueError, match="non-negative"):
            HealthReport(
                total_memories=-1,
                total_citations=0,
                valid_citations=0,
                stale_citations=0,
                broken_citations=0,
                unverified_citations=0,
                health_score=0.0,
                stale_memories=[],
                recommendations=[],
            )

    @pytest.mark.unit
    def test_citation_sum_mismatch_raises(self):
        with pytest.raises(ValueError, match="sum"):
            HealthReport(
                total_memories=1,
                total_citations=10,
                valid_citations=5,
                stale_citations=0,
                broken_citations=0,
                unverified_citations=0,
                health_score=0.5,
                stale_memories=[],
                recommendations=[],
            )

    @pytest.mark.unit
    def test_invalid_health_score_raises(self):
        with pytest.raises(ValueError, match="health_score"):
            HealthReport(
                total_memories=0,
                total_citations=0,
                valid_citations=0,
                stale_citations=0,
                broken_citations=0,
                unverified_citations=0,
                health_score=1.5,
                stale_memories=[],
                recommendations=[],
            )

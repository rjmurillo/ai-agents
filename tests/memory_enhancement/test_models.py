"""Tests for memory_enhancement.models."""

from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path

import pytest

from memory_enhancement.models import Citation, Link, LinkType, Memory, _parse_date


class TestCitation:
    """Tests for Citation dataclass."""

    @pytest.mark.unit
    def test_creation_with_defaults(self) -> None:
        c = Citation(path="src/foo.py")
        assert c.path == "src/foo.py"
        assert c.line is None
        assert c.snippet is None
        assert c.verified is None
        assert c.valid is None
        assert c.mismatch_reason is None

    @pytest.mark.unit
    def test_creation_with_all_fields(self) -> None:
        now = datetime(2026, 1, 15, 12, 0, 0)
        c = Citation(
            path="src/bar.py",
            line=42,
            snippet="def bar",
            verified=now,
            valid=True,
            mismatch_reason=None,
        )
        assert c.path == "src/bar.py"
        assert c.line == 42
        assert c.snippet == "def bar"
        assert c.verified == now
        assert c.valid is True


class TestLink:
    """Tests for Link dataclass."""

    @pytest.mark.unit
    def test_creation(self) -> None:
        link = Link(link_type=LinkType.RELATED, target_id="other-memory")
        assert link.link_type == LinkType.RELATED
        assert link.target_id == "other-memory"


class TestLinkType:
    """Tests for LinkType enum."""

    @pytest.mark.unit
    def test_all_values(self) -> None:
        expected = {"related", "supersedes", "blocks", "implements", "extends"}
        actual = {lt.value for lt in LinkType}
        assert actual == expected

    @pytest.mark.unit
    def test_value_lookup(self) -> None:
        assert LinkType("related") == LinkType.RELATED
        assert LinkType("supersedes") == LinkType.SUPERSEDES
        assert LinkType("blocks") == LinkType.BLOCKS
        assert LinkType("implements") == LinkType.IMPLEMENTS
        assert LinkType("extends") == LinkType.EXTENDS

    @pytest.mark.unit
    def test_invalid_value_raises(self) -> None:
        with pytest.raises(ValueError):
            LinkType("nonexistent")


class TestMemory:
    """Tests for Memory dataclass."""

    @pytest.mark.unit
    def test_creation_with_defaults(self) -> None:
        m = Memory(id="test", subject="Test", path=Path("x.md"), content="body")
        assert m.id == "test"
        assert m.subject == "Test"
        assert m.citations == []
        assert m.links == []
        assert m.tags == []
        assert m.confidence == 0.5
        assert m.last_verified is None

    @pytest.mark.unit
    def test_from_file_basic(self, sample_memory_file: Path) -> None:
        m = Memory.from_file(sample_memory_file)
        assert m.id == "test-memory"
        assert m.subject == "Test Subject"
        assert m.content.strip() == "Memory content here."
        assert m.confidence == 0.8
        assert m.tags == ["test", "example"]

    @pytest.mark.unit
    def test_from_file_citations(self, sample_memory_file: Path) -> None:
        m = Memory.from_file(sample_memory_file)
        assert len(m.citations) == 1
        c = m.citations[0]
        assert c.path == "src/example.py"
        assert c.line == 2
        assert c.snippet == "def hello"

    @pytest.mark.unit
    def test_from_file_links(self, sample_memory_file: Path) -> None:
        m = Memory.from_file(sample_memory_file)
        assert len(m.links) == 1
        link = m.links[0]
        assert link.link_type == LinkType.RELATED
        assert link.target_id == "other-memory"

    @pytest.mark.unit
    def test_from_file_id_defaults_to_stem(self, memories_dir: Path) -> None:
        path = memories_dir / "no-id-field.md"
        path.write_text(
            "---\nsubject: No ID\n---\nContent.\n",
            encoding="utf-8",
        )
        m = Memory.from_file(path)
        assert m.id == "no-id-field"

    @pytest.mark.unit
    def test_from_file_unknown_link_type_warns(
        self, memories_dir: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        path = memories_dir / "unknown-link.md"
        path.write_text(
            "---\n"
            "id: unknown-link\n"
            "subject: Unknown Link\n"
            "links:\n"
            "  - alien_type: some-target\n"
            "---\n"
            "Content.\n",
            encoding="utf-8",
        )
        with caplog.at_level(logging.WARNING, logger="memory_enhancement.models"):
            m = Memory.from_file(path)
        assert len(m.links) == 0
        assert "Unknown link type" in caplog.text

    @pytest.mark.unit
    def test_from_file_no_citations_or_links(self, memories_dir: Path) -> None:
        path = memories_dir / "bare.md"
        path.write_text(
            "---\nid: bare\nsubject: Bare\n---\nBody.\n",
            encoding="utf-8",
        )
        m = Memory.from_file(path)
        assert m.citations == []
        assert m.links == []

    @pytest.mark.unit
    def test_from_file_with_last_verified(self, memories_dir: Path) -> None:
        path = memories_dir / "verified.md"
        path.write_text(
            "---\n"
            "id: verified\n"
            "subject: Verified\n"
            "last_verified: '2026-01-15'\n"
            "---\n"
            "Content.\n",
            encoding="utf-8",
        )
        m = Memory.from_file(path)
        assert m.last_verified == datetime(2026, 1, 15)

    @pytest.mark.unit
    def test_get_links_by_type(self) -> None:
        m = Memory(
            id="multi-link",
            subject="Multi",
            path=Path("x.md"),
            content="",
            links=[
                Link(link_type=LinkType.RELATED, target_id="a"),
                Link(link_type=LinkType.BLOCKS, target_id="b"),
                Link(link_type=LinkType.RELATED, target_id="c"),
            ],
        )
        related = m.get_links_by_type(LinkType.RELATED)
        assert related == ["a", "c"]

    @pytest.mark.unit
    def test_get_links_by_type_empty(self) -> None:
        m = Memory(id="no-links", subject="X", path=Path("x.md"), content="")
        assert m.get_links_by_type(LinkType.EXTENDS) == []


class TestParseDate:
    """Tests for _parse_date helper."""

    @pytest.mark.unit
    def test_none_returns_none(self) -> None:
        assert _parse_date(None) is None

    @pytest.mark.unit
    def test_datetime_passthrough(self) -> None:
        dt = datetime(2026, 3, 1, 10, 30)
        assert _parse_date(dt) is dt

    @pytest.mark.unit
    def test_date_converts_to_datetime(self) -> None:
        d = date(2026, 3, 1)
        result = _parse_date(d)
        assert result == datetime(2026, 3, 1)
        assert isinstance(result, datetime)

    @pytest.mark.unit
    def test_iso_string(self) -> None:
        result = _parse_date("2026-03-01")
        assert result == datetime(2026, 3, 1)

    @pytest.mark.unit
    def test_iso_string_with_time(self) -> None:
        result = _parse_date("2026-03-01T10:30:00")
        assert result == datetime(2026, 3, 1, 10, 30)

    @pytest.mark.unit
    def test_invalid_string_returns_none(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING, logger="memory_enhancement.models"):
            result = _parse_date("not-a-date")
        assert result is None
        assert "Cannot parse date string" in caplog.text

    @pytest.mark.unit
    def test_non_string_non_date_returns_none(self) -> None:
        assert _parse_date(12345) is None
        assert _parse_date([]) is None
        assert _parse_date({}) is None

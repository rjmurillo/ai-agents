"""Tests for memory_enhancement.models."""

from datetime import date, datetime
from pathlib import Path

import pytest
from memory_enhancement.models import (
    Citation,
    Link,
    LinkType,
    Memory,
    _parse_date,
)


class TestCitation:
    """Tests for the Citation dataclass."""

    def test_minimal_citation(self):
        c = Citation(path="src/main.py")
        assert c.path == "src/main.py"
        assert c.line is None
        assert c.snippet is None
        assert c.valid is None

    def test_full_citation(self):
        c = Citation(
            path="src/main.py",
            line=42,
            snippet="def main():",
            verified=datetime(2026, 1, 1),
        )
        assert c.line == 42
        assert c.snippet == "def main():"
        assert c.verified == datetime(2026, 1, 1)


class TestLinkType:
    """Tests for the LinkType enum."""

    def test_all_types_exist(self):
        assert LinkType.RELATED.value == "related"
        assert LinkType.SUPERSEDES.value == "supersedes"
        assert LinkType.BLOCKS.value == "blocks"
        assert LinkType.IMPLEMENTS.value == "implements"
        assert LinkType.EXTENDS.value == "extends"

    def test_invalid_type_raises(self):
        with pytest.raises(ValueError):
            LinkType("nonexistent")


class TestParseDate:
    """Tests for the _parse_date helper."""

    def test_none_returns_none(self):
        assert _parse_date(None) is None

    def test_datetime_passthrough(self):
        dt = datetime(2026, 1, 15)
        assert _parse_date(dt) == dt

    def test_iso_string(self):
        result = _parse_date("2026-01-15T10:30:00")
        assert result == datetime(2026, 1, 15, 10, 30, 0)

    def test_date_only_string(self):
        result = _parse_date("2026-01-15")
        assert result is not None
        assert result.year == 2026

    def test_date_object_converted_to_datetime(self):
        d = date(2026, 1, 15)
        result = _parse_date(d)
        assert isinstance(result, datetime)
        assert result.year == 2026
        assert result.month == 1
        assert result.day == 15

    def test_malformed_iso_string_returns_none(self):
        assert _parse_date("not-a-date") is None
        assert _parse_date("2026-13-45") is None
        assert _parse_date("last week") is None

    def test_unsupported_type_returns_none(self):
        assert _parse_date(12345) is None


class TestMemoryFromFile:
    """Tests for Memory.from_file parsing."""

    def test_memory_with_full_frontmatter(self, tmp_path):
        memory_file = tmp_path / "test-memory.md"
        memory_file.write_text(
            "---\n"
            "id: mem-test-001\n"
            "subject: Test memory subject\n"
            "citations:\n"
            "  - path: src/main.py\n"
            "    line: 10\n"
            "    snippet: 'import os'\n"
            "    verified: 2026-01-15\n"
            "links:\n"
            "  - related: mem-other-002\n"
            "  - supersedes: mem-old-003\n"
            "tags: [testing, memory]\n"
            "confidence: 0.85\n"
            "last_verified: 2026-01-15T10:30:00\n"
            "---\n"
            "\n"
            "This is the memory content.\n"
        )

        memory = Memory.from_file(memory_file)

        assert memory.id == "mem-test-001"
        assert memory.subject == "Test memory subject"
        assert memory.path == memory_file
        assert "This is the memory content." in memory.content
        assert len(memory.citations) == 1
        assert memory.citations[0].path == "src/main.py"
        assert memory.citations[0].line == 10
        assert memory.citations[0].snippet == "import os"
        assert len(memory.links) == 2
        assert memory.links[0].link_type == LinkType.RELATED
        assert memory.links[0].target_id == "mem-other-002"
        assert memory.links[1].link_type == LinkType.SUPERSEDES
        assert memory.tags == ["testing", "memory"]
        assert memory.confidence == 0.85
        assert memory.last_verified is not None

    def test_memory_without_frontmatter(self, tmp_path):
        memory_file = tmp_path / "plain-memory.md"
        memory_file.write_text("Just plain content.\n")

        memory = Memory.from_file(memory_file)

        assert memory.id == "plain-memory"
        assert memory.subject == ""
        assert memory.citations == []
        assert memory.links == []
        assert memory.confidence == 0.5

    def test_memory_with_minimal_frontmatter(self, tmp_path):
        memory_file = tmp_path / "minimal.md"
        memory_file.write_text(
            "---\n"
            "id: mem-minimal\n"
            "---\n"
            "\n"
            "Minimal content.\n"
        )

        memory = Memory.from_file(memory_file)

        assert memory.id == "mem-minimal"
        assert memory.citations == []
        assert memory.confidence == 0.5

    def test_memory_id_falls_back_to_stem(self, tmp_path):
        memory_file = tmp_path / "my-fallback-id.md"
        memory_file.write_text(
            "---\n"
            "subject: Has subject but no ID\n"
            "---\n"
            "\n"
            "Content.\n"
        )

        memory = Memory.from_file(memory_file)
        assert memory.id == "my-fallback-id"

    def test_unknown_link_type_skipped(self, tmp_path):
        memory_file = tmp_path / "bad-links.md"
        memory_file.write_text(
            "---\n"
            "id: mem-bad-links\n"
            "links:\n"
            "  - unknown_type: mem-target\n"
            "  - related: mem-good\n"
            "---\n"
            "\n"
            "Content.\n"
        )

        memory = Memory.from_file(memory_file)
        assert len(memory.links) == 1
        assert memory.links[0].link_type == LinkType.RELATED

    def test_multiple_citations(self, tmp_path):
        memory_file = tmp_path / "multi-cite.md"
        memory_file.write_text(
            "---\n"
            "id: mem-multi\n"
            "citations:\n"
            "  - path: file1.py\n"
            "    line: 1\n"
            "  - path: file2.py\n"
            "    line: 50\n"
            "    snippet: 'class Foo'\n"
            "  - path: file3.py\n"
            "---\n"
            "\n"
            "Content.\n"
        )

        memory = Memory.from_file(memory_file)
        assert len(memory.citations) == 3
        assert memory.citations[2].line is None


class TestMemoryGetLinksByType:
    """Tests for Memory.get_links_by_type."""

    def test_filters_by_type(self):
        memory = Memory(
            id="test",
            subject="test",
            path=Path("test.md"),
            content="",
            links=[
                Link(LinkType.RELATED, "a"),
                Link(LinkType.BLOCKS, "b"),
                Link(LinkType.RELATED, "c"),
            ],
        )

        related = memory.get_links_by_type(LinkType.RELATED)
        assert related == ["a", "c"]

        blocks = memory.get_links_by_type(LinkType.BLOCKS)
        assert blocks == ["b"]

    def test_empty_for_missing_type(self):
        memory = Memory(
            id="test",
            subject="test",
            path=Path("test.md"),
            content="",
            links=[Link(LinkType.RELATED, "a")],
        )

        assert memory.get_links_by_type(LinkType.SUPERSEDES) == []

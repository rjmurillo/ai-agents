"""Tests for Serena memory file parsing and persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from memory_enhancement.models import (
    Citation,
    CitationStatus,
    LinkType,
    MemoryLink,
    MemoryWithCitations,
    SourceType,
)
from memory_enhancement.serena_integration import (
    load_memories,
    load_memory,
    parse_citation_block,
    parse_link_block,
    save_memory,
)


class TestParseCitationBlock:
    """Citation block parsing from markdown text."""

    @pytest.mark.unit
    def test_parse_single_citation(self):
        text = "[cite:file](scripts/validate.py:42) - validation logic"
        result = parse_citation_block(text)
        assert len(result) == 1
        assert result[0].source_type == SourceType.FILE
        assert result[0].target == "scripts/validate.py:42"
        assert result[0].context == "validation logic"

    @pytest.mark.unit
    def test_parse_multiple_citations(self):
        text = (
            "[cite:file](a.py) - first\n"
            "[cite:issue](#123) - second\n"
            "[cite:url](https://example.com)\n"
        )
        result = parse_citation_block(text)
        assert len(result) == 3
        assert result[0].source_type == SourceType.FILE
        assert result[1].source_type == SourceType.ISSUE
        assert result[2].source_type == SourceType.URL

    @pytest.mark.unit
    def test_parse_no_context(self):
        text = "[cite:adr](ADR-007.md)"
        result = parse_citation_block(text)
        assert len(result) == 1
        assert result[0].context == ""

    @pytest.mark.unit
    def test_parse_invalid_source_type_skipped(self):
        text = "[cite:invalid_type](target)"
        result = parse_citation_block(text)
        assert len(result) == 0

    @pytest.mark.unit
    def test_parse_empty_text(self):
        assert parse_citation_block("") == []


class TestParseLinkBlock:
    """Link block parsing from markdown text."""

    @pytest.mark.unit
    def test_parse_single_link(self):
        text = "[link:depends_on](other-memory) - needed for context"
        result = parse_link_block(text)
        assert len(result) == 1
        assert result[0].link_type == LinkType.DEPENDS_ON
        assert result[0].target_id == "other-memory"
        assert result[0].context == "needed for context"

    @pytest.mark.unit
    def test_parse_invalid_link_type_skipped(self):
        text = "[link:invalid](target)"
        result = parse_link_block(text)
        assert len(result) == 0


class TestLoadMemory:
    """Load a single memory file."""

    @pytest.mark.unit
    def test_load_plain_markdown(self, tmp_path):
        md = tmp_path / "test-memory.md"
        md.write_text("# My Memory (2026-01-15)\n\nSome content.\n")
        result = load_memory(md)
        assert result is not None
        assert result.memory_id == "test-memory"
        assert result.title == "My Memory"
        assert result.created_at.year == 2026

    @pytest.mark.unit
    def test_load_with_frontmatter(self, tmp_path):
        md = tmp_path / "fm-memory.md"
        md.write_text(
            "---\ntitle: FM Title\ntags:\n  - tag1\n  - tag2\n"
            "created_at: '2026-03-01T00:00:00+00:00'\n"
            "updated_at: '2026-03-15T00:00:00+00:00'\n---\n\nContent here.\n"
        )
        result = load_memory(md)
        assert result is not None
        assert result.title == "FM Title"
        assert result.tags == ("tag1", "tag2")
        assert result.created_at.month == 3

    @pytest.mark.unit
    def test_load_with_citations(self, tmp_path):
        md = tmp_path / "cited.md"
        md.write_text(
            "# Cited Memory (2026-01-01)\n\n"
            "[cite:file](scripts/main.py:10) - entry point\n"
            "[link:related_to](other-mem) - related\n"
        )
        result = load_memory(md)
        assert result is not None
        assert len(result.citations) == 1
        assert len(result.links) == 1

    @pytest.mark.unit
    def test_load_nonexistent_returns_none(self, tmp_path):
        result = load_memory(tmp_path / "nonexistent.md")
        assert result is None

    @pytest.mark.unit
    def test_load_no_title_uses_stem(self, tmp_path):
        md = tmp_path / "no-title.md"
        md.write_text("Just some content without a header.\n")
        result = load_memory(md)
        assert result is not None
        assert result.title == "no-title"


class TestLoadMemories:
    """Load all memories from a directory."""

    @pytest.mark.unit
    def test_load_multiple(self, tmp_path):
        (tmp_path / "a.md").write_text("# A (2026-01-01)\n\nContent A\n")
        (tmp_path / "b.md").write_text("# B (2026-01-02)\n\nContent B\n")
        result = load_memories(tmp_path)
        assert len(result) == 2

    @pytest.mark.unit
    def test_skips_readme_and_claude(self, tmp_path):
        (tmp_path / "README.md").write_text("# Index\n")
        (tmp_path / "CLAUDE.md").write_text("# Claude\n")
        (tmp_path / "real.md").write_text("# Real (2026-01-01)\n\nContent\n")
        result = load_memories(tmp_path)
        assert len(result) == 1
        assert result[0].memory_id == "real"

    @pytest.mark.unit
    def test_loads_subdirectories(self, tmp_path):
        sub = tmp_path / "adr"
        sub.mkdir()
        (sub / "adr-001.md").write_text("# ADR 001 (2026-01-01)\n\nContent\n")
        result = load_memories(tmp_path)
        assert len(result) == 1

    @pytest.mark.unit
    def test_empty_directory(self, tmp_path):
        assert load_memories(tmp_path) == []

    @pytest.mark.unit
    def test_nonexistent_directory(self, tmp_path):
        assert load_memories(tmp_path / "nonexistent") == []


class TestSaveMemory:
    """Save a memory to disk with frontmatter."""

    @pytest.mark.unit
    def test_save_and_reload(self, tmp_path):
        now = datetime.now(timezone.utc)
        memory = MemoryWithCitations(
            memory_id="save-test",
            title="Save Test",
            content="Test content.",
            citations=[
                Citation(
                    source_type=SourceType.FILE,
                    target="a.py",
                    context="test",
                )
            ],
            links=[
                MemoryLink(
                    link_type=LinkType.RELATED_TO,
                    target_id="other",
                    context="related",
                )
            ],
            confidence=0.85,
            created_at=now,
            updated_at=now,
            tags=["test", "save"],
        )
        path = save_memory(memory, tmp_path)
        assert path.is_file()

        reloaded = load_memory(path)
        assert reloaded is not None
        assert reloaded.title == "Save Test"
        assert reloaded.tags == ("test", "save")
        assert len(reloaded.citations) == 1
        assert len(reloaded.links) == 1

    @pytest.mark.unit
    def test_save_load_roundtrip_confidence(self, tmp_path):
        now = datetime.now(timezone.utc)
        memory = MemoryWithCitations(
            memory_id="conf-test",
            title="Confidence Test",
            content="Body.",
            confidence=0.85,
            created_at=now,
            updated_at=now,
        )
        path = save_memory(memory, tmp_path)
        reloaded = load_memory(path)
        assert reloaded is not None
        assert reloaded.confidence == pytest.approx(0.85)

    @pytest.mark.unit
    def test_save_creates_directory(self, tmp_path):
        target_dir = tmp_path / "new" / "dir"
        memory = MemoryWithCitations(
            memory_id="nested", title="Nested", content="Body"
        )
        path = save_memory(memory, target_dir)
        assert path.is_file()

    @pytest.mark.unit
    def test_save_path_traversal_blocked(self, tmp_path):
        """CWE-22: memory_id with traversal path must be rejected."""
        memory = MemoryWithCitations(
            memory_id="../escape", title="Escape", content="Body"
        )
        with pytest.raises(ValueError, match="traversal"):
            save_memory(memory, tmp_path)

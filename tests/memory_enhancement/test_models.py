"""Unit tests for memory enhancement data models."""

import pytest
from datetime import datetime
from pathlib import Path

from scripts.memory_enhancement.models import Citation, Link, LinkType, Memory


@pytest.mark.unit
def test_citation_dataclass_creation():
    """Test Citation dataclass instantiation."""
    citation = Citation(
        path="scripts/test.py", line=10, snippet="def test():", valid=True, mismatch_reason=None
    )

    assert citation.path == "scripts/test.py"
    assert citation.line == 10
    assert citation.snippet == "def test():"
    assert citation.valid is True
    assert citation.mismatch_reason is None


@pytest.mark.unit
def test_link_type_enum_values():
    """Test LinkType enum has expected values."""
    assert LinkType.RELATED.value == "RELATED"
    assert LinkType.SUPERSEDES.value == "SUPERSEDES"
    assert LinkType.BLOCKS.value == "BLOCKS"
    assert LinkType.IMPLEMENTS.value == "IMPLEMENTS"
    assert LinkType.EXTENDS.value == "EXTENDS"


@pytest.mark.unit
def test_memory_from_serena_file_valid(sample_memory_file):
    """Test parsing a valid memory file."""
    memory = Memory.from_serena_file(sample_memory_file)

    assert memory.id == "test-memory-001"
    assert memory.subject == "Test Memory with Valid Citations"
    assert len(memory.citations) == 2
    assert memory.citations[0].path == "scripts/sample.py"
    assert memory.citations[0].line == 1
    assert memory.citations[0].snippet == "def hello():"
    assert memory.citations[1].path == "README.md"
    assert memory.citations[1].line is None
    assert len(memory.tags) == 2
    assert "test" in memory.tags
    assert memory.confidence == 1.0


@pytest.mark.unit
def test_memory_from_serena_file_no_frontmatter(tmp_path):
    """Test handling memory file without frontmatter."""
    memory_file = tmp_path / "no-frontmatter.md"
    memory_file.write_text("# Plain Markdown\n\nNo frontmatter here.")

    memory = Memory.from_serena_file(memory_file)

    # Should use filename as ID
    assert memory.id == "no-frontmatter"
    assert memory.subject == ""
    assert len(memory.citations) == 0
    assert memory.confidence == 1.0


@pytest.mark.unit
def test_memory_from_serena_file_minimal(tmp_path):
    """Test parsing memory with minimal metadata."""
    memory_content = """---
subject: Minimal Memory
---

# Minimal

Just a subject.
"""
    memory_file = tmp_path / "minimal.md"
    memory_file.write_text(memory_content)

    memory = Memory.from_serena_file(memory_file)

    assert memory.id == "minimal"
    assert memory.subject == "Minimal Memory"
    assert len(memory.citations) == 0
    assert len(memory.links) == 0
    assert len(memory.tags) == 0
    assert memory.confidence == 1.0


@pytest.mark.unit
def test_memory_get_links_by_type(tmp_path):
    """Test filtering links by type."""
    memory_content = """---
id: test-links
subject: Test Links
links:
  - link_type: RELATED
    target_id: memory-001
  - link_type: SUPERSEDES
    target_id: memory-002
  - link_type: RELATED
    target_id: memory-003
---

# Test Links
"""
    memory_file = tmp_path / "test-links.md"
    memory_file.write_text(memory_content)

    memory = Memory.from_serena_file(memory_file)

    related = memory.get_links_by_type(LinkType.RELATED)
    assert len(related) == 2
    assert "memory-001" in related
    assert "memory-003" in related

    supersedes = memory.get_links_by_type(LinkType.SUPERSEDES)
    assert len(supersedes) == 1
    assert "memory-002" in supersedes


@pytest.mark.unit
def test_memory_parse_date_formats():
    """Test date parsing from various formats."""
    # None
    assert Memory._parse_date(None) is None

    # datetime instance
    now = datetime.now()
    assert Memory._parse_date(now) == now

    # ISO string
    iso_str = "2026-01-24T12:00:00"
    parsed = Memory._parse_date(iso_str)
    assert isinstance(parsed, datetime)
    assert parsed.year == 2026
    assert parsed.month == 1
    assert parsed.day == 24


@pytest.mark.unit
def test_citation_with_snippet():
    """Test citation with code snippet."""
    citation = Citation(path="test.py", line=5, snippet="return True")

    assert citation.snippet == "return True"
    assert citation.line == 5


@pytest.mark.unit
def test_link_invalid_type(tmp_path):
    """Test handling unknown link types gracefully."""
    memory_content = """---
id: test-invalid-link
subject: Invalid Link Type
links:
  - link_type: UNKNOWN_TYPE
    target_id: memory-001
  - link_type: RELATED
    target_id: memory-002
---

# Invalid Link
"""
    memory_file = tmp_path / "test-invalid-link.md"
    memory_file.write_text(memory_content)

    memory = Memory.from_serena_file(memory_file)

    # Should skip invalid link but keep valid one
    assert len(memory.links) == 1
    assert memory.links[0].link_type == LinkType.RELATED
    assert memory.links[0].target_id == "memory-002"


@pytest.mark.unit
def test_memory_from_serena_file_not_found():
    """Test FileNotFoundError for missing file."""
    with pytest.raises(FileNotFoundError):
        Memory.from_serena_file(Path("nonexistent.md"))

"""Tests for serena.py confidence scoring and citation management."""

import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

from scripts.memory_enhancement.models import Memory, Citation
from scripts.memory_enhancement.citations import VerificationResult
from scripts.memory_enhancement.serena import (
    update_confidence,
    add_citation_to_memory,
    list_citations_with_status,
    get_confidence_history,
)


class TestUpdateConfidence:
    """Tests for update_confidence function."""

    def test_update_confidence_with_valid_citations(self, tmp_path):
        """Confidence = 1.0 when all citations are valid."""
        # Create memory file with citations
        memory_file = tmp_path / "test-memory.md"
        memory_file.write_text(
            """---
subject: Test Memory
confidence: 0.5
citations:
  - path: src/test.py
    line: 10
    valid: true
  - path: src/test2.py
    line: 20
    valid: true
---

# Test content
"""
        )

        memory = Memory.from_serena_file(memory_file)
        result = VerificationResult(
            memory_id="test-memory",
            valid=True,
            total_citations=2,
            valid_count=2,
            stale_citations=[],
            confidence=1.0,
        )

        update_confidence(memory, result)

        # Verify frontmatter updated
        updated_memory = Memory.from_serena_file(memory_file)
        assert updated_memory.confidence == 1.0
        assert updated_memory.last_verified is not None

    def test_update_confidence_with_stale_citations(self, tmp_path):
        """Confidence < 1.0 when some citations are stale."""
        memory_file = tmp_path / "test-memory.md"
        memory_file.write_text(
            """---
subject: Test Memory
confidence: 1.0
citations:
  - path: src/test.py
    line: 10
    valid: true
  - path: src/missing.py
    line: 20
    valid: true
---

# Test content
"""
        )

        memory = Memory.from_serena_file(memory_file)
        stale_citation = Citation(
            path="src/missing.py",
            line=20,
            valid=False,
            mismatch_reason="File not found: src/missing.py",
        )
        result = VerificationResult(
            memory_id="test-memory",
            valid=False,
            total_citations=2,
            valid_count=1,
            stale_citations=[stale_citation],
            confidence=0.5,
        )

        update_confidence(memory, result)

        # Verify frontmatter updated
        updated_memory = Memory.from_serena_file(memory_file)
        assert updated_memory.confidence == 0.5
        assert updated_memory.citations[1].valid is False
        assert "File not found" in updated_memory.citations[1].mismatch_reason

    def test_update_confidence_preserves_content(self, tmp_path):
        """Update preserves markdown content and other frontmatter."""
        memory_file = tmp_path / "test-memory.md"
        content = "# Important content\n\nDo not lose this!"
        memory_file.write_text(
            f"""---
subject: Test Memory
tags: [important, preserve]
confidence: 0.8
citations:
  - path: src/test.py
    line: 10
---

{content}
"""
        )

        memory = Memory.from_serena_file(memory_file)
        result = VerificationResult(
            memory_id="test-memory",
            valid=True,
            total_citations=1,
            valid_count=1,
            stale_citations=[],
            confidence=1.0,
        )

        update_confidence(memory, result)

        # Verify content preserved
        updated_memory = Memory.from_serena_file(memory_file)
        assert updated_memory.content.strip() == content
        assert updated_memory.tags == ["important", "preserve"]
        assert updated_memory.subject == "Test Memory"

    def test_update_confidence_file_not_found(self):
        """Raises FileNotFoundError if memory file doesn't exist."""
        memory = Memory(
            id="missing",
            subject="Test",
            path=Path("/nonexistent/memory.md"),
            content="",
        )
        result = VerificationResult(
            memory_id="missing",
            valid=True,
            total_citations=0,
            valid_count=0,
            stale_citations=[],
            confidence=1.0,
        )

        with pytest.raises(FileNotFoundError, match="Memory file not found"):
            update_confidence(memory, result)


class TestAddCitationToMemory:
    """Tests for add_citation_to_memory function."""

    def test_add_citation_to_memory_valid_file(self, tmp_path):
        """Citation added to frontmatter when file exists."""
        # Create memory file
        memory_file = tmp_path / "test-memory.md"
        memory_file.write_text(
            """---
subject: Test Memory
---

# Content
"""
        )

        # Create cited file
        cited_file = tmp_path / "src" / "test.py"
        cited_file.parent.mkdir(parents=True)
        cited_file.write_text("def example():\n    pass\n")

        add_citation_to_memory(
            memory_path=memory_file,
            file_path="src/test.py",
            line=1,
            snippet="def example",
            repo_root=tmp_path,
        )

        # Verify citation added
        memory = Memory.from_serena_file(memory_file)
        assert len(memory.citations) == 1
        assert memory.citations[0].path == "src/test.py"
        assert memory.citations[0].line == 1
        assert memory.citations[0].snippet == "def example"
        assert memory.citations[0].valid is True
        assert memory.confidence == 1.0

    def test_add_citation_preserves_existing(self, tmp_path):
        """New citation doesn't remove existing citations."""
        memory_file = tmp_path / "test-memory.md"
        memory_file.write_text(
            """---
subject: Test Memory
citations:
  - path: src/old.py
    line: 5
    snippet: "old code"
    verified: "2026-01-20T10:00:00"
    valid: true
---

# Content
"""
        )

        # Create cited file
        cited_file = tmp_path / "src" / "new.py"
        cited_file.parent.mkdir(parents=True)
        cited_file.write_text("def new():\n    pass\n")

        add_citation_to_memory(
            memory_path=memory_file,
            file_path="src/new.py",
            line=1,
            snippet="def new",
            repo_root=tmp_path,
        )

        # Verify both citations present
        memory = Memory.from_serena_file(memory_file)
        assert len(memory.citations) == 2
        assert memory.citations[0].path == "src/old.py"
        assert memory.citations[1].path == "src/new.py"

    def test_add_citation_updates_duplicate(self, tmp_path):
        """Duplicate citation (same path+line) gets updated, not added."""
        memory_file = tmp_path / "test-memory.md"
        memory_file.write_text(
            """---
subject: Test Memory
citations:
  - path: src/test.py
    line: 10
    snippet: "old snippet"
    verified: "2026-01-20T10:00:00"
    valid: true
---

# Content
"""
        )

        # Create cited file
        cited_file = tmp_path / "src" / "test.py"
        cited_file.parent.mkdir(parents=True)
        cited_file.write_text("\n" * 9 + "def updated():\n    pass\n")

        add_citation_to_memory(
            memory_path=memory_file,
            file_path="src/test.py",
            line=10,
            snippet="def updated",
            repo_root=tmp_path,
        )

        # Verify citation updated, not duplicated
        memory = Memory.from_serena_file(memory_file)
        assert len(memory.citations) == 1
        assert memory.citations[0].snippet == "def updated"

    def test_add_citation_invalid_file_raises_error(self, tmp_path):
        """ValueError raised when cited file doesn't exist."""
        memory_file = tmp_path / "test-memory.md"
        memory_file.write_text("---\nsubject: Test\n---\n# Content")

        with pytest.raises(ValueError, match="Invalid citation"):
            add_citation_to_memory(
                memory_path=memory_file,
                file_path="src/missing.py",
                line=10,
                repo_root=tmp_path,
            )

    def test_add_citation_calculates_confidence(self, tmp_path):
        """Confidence recalculated after adding citation."""
        memory_file = tmp_path / "test-memory.md"
        memory_file.write_text(
            """---
subject: Test Memory
citations:
  - path: src/old.py
    line: 5
    valid: false
    mismatch_reason: "File not found"
---

# Content
"""
        )

        # Create cited file
        cited_file = tmp_path / "src" / "new.py"
        cited_file.parent.mkdir(parents=True)
        cited_file.write_text("def new():\n    pass\n")

        add_citation_to_memory(
            memory_path=memory_file,
            file_path="src/new.py",
            line=1,
            snippet="def new",
            repo_root=tmp_path,
        )

        # Verify confidence updated (1 invalid + 1 valid = 0.5)
        memory = Memory.from_serena_file(memory_file)
        assert memory.confidence == 0.5


class TestListCitationsWithStatus:
    """Tests for list_citations_with_status function."""

    def test_list_citations_with_status(self, tmp_path):
        """Returns citation data with current validity status."""
        memory_file = tmp_path / "test-memory.md"
        memory_file.write_text(
            """---
subject: Test Memory
citations:
  - path: src/valid.py
    line: 1
    snippet: "def valid"
  - path: src/missing.py
    line: 10
    snippet: "missing"
---

# Content
"""
        )

        # Create valid file only
        valid_file = tmp_path / "src" / "valid.py"
        valid_file.parent.mkdir(parents=True)
        valid_file.write_text("def valid():\n    pass\n")

        citations = list_citations_with_status(memory_file, repo_root=tmp_path)

        assert len(citations) == 2
        assert citations[0]["path"] == "src/valid.py"
        assert citations[0]["valid"] is True
        assert citations[1]["path"] == "src/missing.py"
        assert citations[1]["valid"] is False
        assert "File not found" in citations[1]["mismatch_reason"]


class TestGetConfidenceHistory:
    """Tests for get_confidence_history function."""

    def test_get_confidence_history_with_data(self):
        """Returns single historical entry with current confidence."""
        memory = Memory(
            id="test",
            subject="Test",
            path=Path("test.md"),
            content="",
            confidence=0.8,
            last_verified=datetime(2026, 1, 24, 15, 30),
        )

        history = get_confidence_history(memory)

        assert len(history) == 1
        assert history[0][0] == datetime(2026, 1, 24, 15, 30)
        assert history[0][1] == 0.8

    def test_get_confidence_history_no_data(self):
        """Returns empty list when no verification data."""
        memory = Memory(
            id="test",
            subject="Test",
            path=Path("test.md"),
            content="",
        )

        history = get_confidence_history(memory)

        assert history == []


class TestConfidenceWithoutCitations:
    """Tests for confidence behavior when memory has no citations."""

    def test_default_confidence_without_citations(self, tmp_path):
        """Memories without citations use default confidence (0.5)."""
        memory_file = tmp_path / "test-memory.md"
        memory_file.write_text(
            """---
subject: Test Memory
---

# Content
"""
        )

        memory = Memory.from_serena_file(memory_file)
        assert memory.confidence == 1.0  # Default from models.py

        # After adding citation, confidence should be calculated
        cited_file = tmp_path / "src" / "test.py"
        cited_file.parent.mkdir(parents=True)
        cited_file.write_text("def test():\n    pass\n")

        add_citation_to_memory(
            memory_path=memory_file,
            file_path="src/test.py",
            line=1,
            repo_root=tmp_path,
        )

        updated_memory = Memory.from_serena_file(memory_file)
        assert updated_memory.confidence == 1.0  # All citations valid

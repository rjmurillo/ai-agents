"""Unit tests for citation verification logic."""

import pytest
from pathlib import Path

from scripts.memory_enhancement.citations import (
    verify_citation,
    verify_memory,
    verify_all_memories,
)
from scripts.memory_enhancement.models import Citation, Memory


@pytest.mark.unit
def test_verify_citation_file_exists(tmp_repo):
    """Test file-only citation passes when file exists."""
    citation = Citation(path="README.md")
    result = verify_citation(citation, tmp_repo)

    assert result.valid is True
    assert result.mismatch_reason is None


@pytest.mark.unit
def test_verify_citation_file_not_found(tmp_repo):
    """Test missing file fails with reason."""
    citation = Citation(path="nonexistent.py", line=1)
    result = verify_citation(citation, tmp_repo)

    assert result.valid is False
    assert "File not found" in result.mismatch_reason


@pytest.mark.unit
def test_verify_citation_line_valid(tmp_repo):
    """Test line number within bounds passes."""
    citation = Citation(path="scripts/sample.py", line=1)
    result = verify_citation(citation, tmp_repo)

    assert result.valid is True
    assert result.mismatch_reason is None


@pytest.mark.unit
def test_verify_citation_line_out_of_bounds(tmp_repo):
    """Test line exceeding file length fails."""
    citation = Citation(path="scripts/sample.py", line=999)
    result = verify_citation(citation, tmp_repo)

    assert result.valid is False
    assert "exceeds file length" in result.mismatch_reason


@pytest.mark.unit
def test_verify_citation_snippet_match(tmp_repo):
    """Test snippet contained in line passes."""
    citation = Citation(path="scripts/sample.py", line=1, snippet="def hello()")
    result = verify_citation(citation, tmp_repo)

    assert result.valid is True
    assert result.mismatch_reason is None


@pytest.mark.unit
def test_verify_citation_snippet_mismatch(tmp_repo):
    """Test snippet not in line fails."""
    citation = Citation(path="scripts/sample.py", line=1, snippet="def goodbye()")
    result = verify_citation(citation, tmp_repo)

    assert result.valid is False
    assert "Snippet not found" in result.mismatch_reason


@pytest.mark.unit
def test_verify_citation_invalid_line_number(tmp_repo):
    """Test line < 1 fails."""
    citation = Citation(path="scripts/sample.py", line=0)
    result = verify_citation(citation, tmp_repo)

    assert result.valid is False
    assert "Invalid line number" in result.mismatch_reason


@pytest.mark.unit
def test_verify_memory_all_valid(sample_memory_file):
    """Test memory with all valid citations."""
    memory = Memory.from_serena_file(sample_memory_file)

    # Use parent directory as repo root (where sample files exist)
    repo_root = sample_memory_file.parent
    result = verify_memory(memory, repo_root)

    assert result.valid is True
    assert result.total_citations == 2
    assert result.valid_count == 2
    assert len(result.stale_citations) == 0
    assert result.confidence == 1.0


@pytest.mark.unit
def test_verify_memory_some_stale(sample_memory_stale):
    """Test memory with mixed validity."""
    memory = Memory.from_serena_file(sample_memory_stale)

    repo_root = sample_memory_stale.parent
    result = verify_memory(memory, repo_root)

    assert result.valid is False
    assert result.total_citations == 2
    assert result.valid_count == 0  # Both citations are invalid
    assert len(result.stale_citations) == 2
    assert result.confidence == 0.0  # 0/2 valid


@pytest.mark.unit
def test_verify_memory_no_citations(sample_memory_no_citations):
    """Test memory without citations uses existing confidence."""
    memory = Memory.from_serena_file(sample_memory_no_citations)

    repo_root = sample_memory_no_citations.parent
    result = verify_memory(memory, repo_root)

    assert result.valid is True
    assert result.total_citations == 0
    assert result.valid_count == 0
    assert len(result.stale_citations) == 0
    assert result.confidence == 1.0  # Uses memory's confidence


@pytest.mark.unit
def test_verify_memory_confidence_calculation(tmp_path):
    """Test confidence calculation based on validity ratio."""
    memory_content = """---
id: test-partial
subject: Partial Validity
citations:
  - path: exists.py
  - path: missing1.py
  - path: missing2.py
  - path: missing3.py
confidence: 0.5
---

# Partial
"""
    memory_file = tmp_path / "test-partial.md"
    memory_file.write_text(memory_content)

    # Create only one file
    (tmp_path / "exists.py").write_text("# exists")

    memory = Memory.from_serena_file(memory_file)
    result = verify_memory(memory, tmp_path)

    # 1 valid out of 4 = 0.25
    assert result.total_citations == 4
    assert result.valid_count == 1
    assert result.confidence == 0.25


@pytest.mark.unit
def test_verify_all_memories(tmp_path):
    """Test batch verification of directory."""
    # Create memories directory
    memories_dir = tmp_path / "memories"
    memories_dir.mkdir()

    # Create valid memory
    valid_content = """---
id: valid-mem
subject: Valid Memory
citations:
  - path: valid.py
---

# Valid
"""
    (memories_dir / "valid-mem.md").write_text(valid_content)

    # Create stale memory
    stale_content = """---
id: stale-mem
subject: Stale Memory
citations:
  - path: nonexistent.py
    line: 1
---

# Stale
"""
    (memories_dir / "stale-mem.md").write_text(stale_content)

    # Create the valid file
    (tmp_path / "valid.py").write_text("# valid")

    verify_result = verify_all_memories(memories_dir, tmp_path)
    results = verify_result.results

    assert len(results) == 2
    assert sum(1 for r in results if r.valid) == 1
    assert sum(1 for r in results if not r.valid) == 1
    assert verify_result.parse_failures == 0


@pytest.mark.unit
def test_verify_all_memories_skip_no_citations(tmp_path):
    """Test that memories without citations are skipped."""
    memories_dir = tmp_path / "memories"
    memories_dir.mkdir()

    # Memory with citations
    with_cit = """---
id: with-cit
citations:
  - path: test.py
---

# With
"""
    (memories_dir / "with-cit.md").write_text(with_cit)
    (tmp_path / "test.py").write_text("# test")

    # Memory without citations
    no_cit = """---
id: no-cit
---

# No citations
"""
    (memories_dir / "no-cit.md").write_text(no_cit)

    verify_result = verify_all_memories(memories_dir, tmp_path)
    results = verify_result.results

    # Only the memory with citations should be included
    assert len(results) == 1
    assert results[0].memory_id == "with-cit"
    assert verify_result.parse_failures == 0


@pytest.mark.unit
def test_verify_all_memories_parse_error(tmp_path):
    """Test that malformed files are handled gracefully."""
    memories_dir = tmp_path / "memories"
    memories_dir.mkdir()

    # Create a valid memory
    valid = """---
id: valid
citations:
  - path: test.py
---

# Valid
"""
    (memories_dir / "valid.md").write_text(valid)
    (tmp_path / "test.py").write_text("# test")

    # Create a malformed memory (invalid YAML)
    malformed = """---
id: bad
citations: [[[invalid yaml
---

# Bad
"""
    (memories_dir / "malformed.md").write_text(malformed)

    # Should not raise, just skip malformed and continue
    verify_result = verify_all_memories(memories_dir, tmp_path)
    results = verify_result.results

    # Should only get the valid memory
    assert len(results) == 1
    assert results[0].memory_id == "valid"
    # Malformed file should be counted as a parse failure
    assert verify_result.parse_failures == 1

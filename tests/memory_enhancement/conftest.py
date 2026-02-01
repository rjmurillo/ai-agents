"""Pytest fixtures for memory enhancement tests."""

import pytest
from pathlib import Path


@pytest.fixture
def tmp_repo(tmp_path):
    """Create a temporary repository with sample files.

    Args:
        tmp_path: Pytest temporary path fixture

    Returns:
        Path to temporary repo root
    """
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    # Create sample file structure
    (repo_root / "scripts").mkdir()
    (repo_root / "scripts" / "sample.py").write_text(
        "def hello():\n    print('Hello, World!')\n    return True\n"
    )

    (repo_root / "README.md").write_text("# Sample Project\n\nThis is a sample.\n")

    return repo_root


@pytest.fixture
def sample_memory_file(tmp_path):
    """Create a memory file with valid citations.

    Args:
        tmp_path: Pytest temporary path fixture

    Returns:
        Path to memory file
    """
    memory_content = """---
id: test-memory-001
subject: Test Memory with Valid Citations
citations:
  - path: scripts/sample.py
    line: 1
    snippet: "def hello():"
  - path: README.md
tags:
  - test
  - example
confidence: 1.0
---

# Test Memory

This is a test memory with valid citations.
"""

    memory_file = tmp_path / "test-memory-001.md"
    memory_file.write_text(memory_content)

    # Create the referenced files
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir(exist_ok=True)
    (scripts_dir / "sample.py").write_text(
        "def hello():\n    print('Hello, World!')\n    return True\n"
    )

    (tmp_path / "README.md").write_text("# Sample Project\n\nThis is a sample.\n")

    return memory_file


@pytest.fixture
def sample_memory_stale(tmp_path):
    """Create a memory file with stale citations.

    Args:
        tmp_path: Pytest temporary path fixture

    Returns:
        Path to memory file
    """
    memory_content = """---
id: test-memory-stale
subject: Test Memory with Stale Citations
citations:
  - path: scripts/nonexistent.py
    line: 1
  - path: scripts/sample.py
    line: 999
    snippet: "not found"
tags:
  - test
confidence: 0.5
---

# Stale Memory

This memory has stale citations.
"""

    memory_file = tmp_path / "test-memory-stale.md"
    memory_file.write_text(memory_content)

    # Create one valid file (but citation will fail due to invalid line/snippet)
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir(exist_ok=True)
    (scripts_dir / "sample.py").write_text("def hello():\n    print('Hello')\n")

    return memory_file


@pytest.fixture
def sample_memory_no_citations(tmp_path):
    """Create a memory file without citations.

    Args:
        tmp_path: Pytest temporary path fixture

    Returns:
        Path to memory file
    """
    memory_content = """---
id: test-memory-no-cit
subject: Test Memory Without Citations
tags:
  - test
confidence: 1.0
---

# No Citations

This memory has no citations.
"""

    memory_file = tmp_path / "test-memory-no-cit.md"
    memory_file.write_text(memory_content)

    return memory_file

"""Shared fixtures for memory_enhancement tests."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def repo_root(tmp_path: Path) -> Path:
    """Create a temporary repo root with sample source files."""
    (tmp_path / ".git").mkdir()

    src = tmp_path / "src"
    src.mkdir()
    example = src / "example.py"
    example.write_text(
        "# Example module\n"
        "def hello():\n"
        '    return "hello"\n'
        "\n"
        "def goodbye():\n"
        '    return "goodbye"\n',
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture()
def memories_dir(repo_root: Path) -> Path:
    """Create a memories directory with sample .md files."""
    mem_dir = repo_root / ".serena" / "memories"
    mem_dir.mkdir(parents=True)
    return mem_dir


@pytest.fixture()
def sample_memory_content() -> str:
    """Return valid YAML frontmatter memory content."""
    return (
        "---\n"
        "id: test-memory\n"
        "subject: Test Subject\n"
        "citations:\n"
        "  - path: src/example.py\n"
        "    line: 2\n"
        '    snippet: "def hello"\n'
        "links:\n"
        "  - related: other-memory\n"
        "tags:\n"
        "  - test\n"
        "  - example\n"
        "confidence: 0.8\n"
        "---\n"
        "Memory content here.\n"
    )


@pytest.fixture()
def sample_memory_file(memories_dir: Path, sample_memory_content: str) -> Path:
    """Write a sample memory file and return its path."""
    path = memories_dir / "test-memory.md"
    path.write_text(sample_memory_content, encoding="utf-8")
    return path

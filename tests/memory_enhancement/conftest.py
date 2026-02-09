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


def _write_memory(
    directory: Path,
    memory_id: str,
    subject: str,
    links: list[tuple[str, str]] | None = None,
    tags: list[str] | None = None,
    confidence: float = 0.9,
) -> Path:
    """Write a memory markdown file with YAML frontmatter.

    Args:
        directory: Directory to write the file into.
        memory_id: Unique memory identifier.
        subject: Human-readable subject line.
        links: List of (link_type, target_id) tuples.
        tags: Optional tag list.
        confidence: Confidence score.

    Returns:
        Path to the written file.
    """
    lines = [
        "---",
        f"id: {memory_id}",
        f"subject: {subject}",
    ]
    if links:
        lines.append("links:")
        for link_type, target_id in links:
            lines.append(f"  - {link_type}: {target_id}")
    if tags:
        lines.append("tags:")
        for tag in tags:
            lines.append(f"  - {tag}")
    lines.append(f"confidence: {confidence}")
    lines.append("---")
    lines.append(f"Content for {memory_id}.")
    lines.append("")

    path = directory / f"{memory_id}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


@pytest.fixture()
def graph_memories_dir(memories_dir: Path) -> Path:
    """Create interconnected memory files for graph testing.

    Graph structure:
        A -> B -> C (chain)
        A -> D (branch)
        D -> E (related)
    """
    _write_memory(
        memories_dir, "memory-a", "Memory A",
        links=[("related", "memory-b"), ("implements", "memory-d")],
        tags=["test"],
    )
    _write_memory(
        memories_dir, "memory-b", "Memory B",
        links=[("extends", "memory-c")],
        tags=["test"],
    )
    _write_memory(
        memories_dir, "memory-c", "Memory C",
        tags=["test"],
    )
    _write_memory(
        memories_dir, "memory-d", "Memory D",
        links=[("related", "memory-e")],
        tags=["test"],
    )
    _write_memory(
        memories_dir, "memory-e", "Memory E",
        tags=["test"],
    )
    return memories_dir


@pytest.fixture()
def cyclic_memories_dir(memories_dir: Path) -> Path:
    """Create memory files with cycles for cycle detection testing.

    Graph structure:
        A -> B -> C -> A (triangle cycle)
    """
    _write_memory(
        memories_dir, "cycle-a", "Cycle A",
        links=[("related", "cycle-b")],
    )
    _write_memory(
        memories_dir, "cycle-b", "Cycle B",
        links=[("extends", "cycle-c")],
    )
    _write_memory(
        memories_dir, "cycle-c", "Cycle C",
        links=[("blocks", "cycle-a")],
    )
    return memories_dir


@pytest.fixture(scope="session")
def large_graph_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Generate 1000+ memory files for performance benchmarking (session-scoped)."""
    tmp_path = tmp_path_factory.mktemp("large_graph")
    mem_dir = tmp_path / ".serena" / "memories"
    mem_dir.mkdir(parents=True)

    node_count = 1100

    for i in range(node_count):
        # Deterministic link generation: each node links to next 3 nodes (wrapping)
        num_links = 3
        targets = [(i + offset) % node_count for offset in range(1, num_links + 1)]
        links = [("related", f"node-{t}") for t in targets]

        link_lines = []
        for link_type, target_name in links:
            link_lines.append(f"  - {link_type}: {target_name}")
        links_yaml = "\n".join(link_lines)

        content = (
            f"---\n"
            f"id: node-{i}\n"
            f"subject: Node {i}\n"
            f"links:\n"
            f"{links_yaml}\n"
            f"---\n"
            f"Content for node {i}.\n"
        )
        (mem_dir / f"node-{i}.md").write_text(content, encoding="utf-8")

    return mem_dir

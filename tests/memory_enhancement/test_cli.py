"""CLI integration tests for memory enhancement layer.

Tests CLI invocation in-process to verify:
- Exit codes for various conditions
- JSON output schemas
- Path traversal security (CWE-22)
- Memory path resolution
- Corrupt YAML error handling
- Path resolution regression (CWE-22 fix)
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pytest

from scripts.memory_enhancement.__main__ import (
    CLIError,
    _resolve_directory_path,
    _resolve_memory_path,
    main,
)


@dataclass
class CLIResult:
    """Mirrors subprocess.CompletedProcess interface for in-process CLI calls."""

    returncode: int
    stdout: str
    stderr: str


@pytest.fixture
def call_main(monkeypatch, capsys):
    """Fixture that calls main() in-process via monkeypatch + capsys.

    Returns a callable(*args, cwd=None) -> CLIResult.
    """

    def _call(*args: str, cwd: Optional[Path] = None) -> CLIResult:
        argv = ["memory_enhancement", *args]
        monkeypatch.setattr("sys.argv", argv)
        if cwd is not None:
            monkeypatch.chdir(cwd)

        try:
            returncode = main()
        except SystemExit as exc:
            # argparse calls sys.exit(2) on bad args
            returncode = exc.code if exc.code is not None else 0

        captured = capsys.readouterr()
        return CLIResult(
            returncode=returncode,
            stdout=captured.out,
            stderr=captured.err,
        )

    return _call


# ============================================================================
# Path Traversal Security Tests (CWE-22)
# ============================================================================


class TestPathTraversalSecurity:
    """Tests for CWE-22 path traversal protection."""

    def test_verify_rejects_path_traversal(self, tmp_path, call_main):
        """verify command blocks ../../../etc/passwd style paths."""
        # Create a valid memory in tmp_path to ensure we're testing path validation
        memories_dir = tmp_path / ".serena" / "memories"
        memories_dir.mkdir(parents=True)

        # Create a legitimate memory file
        memory_file = memories_dir / "test-memory.md"
        memory_file.write_text(
            "---\n"
            "id: test-memory\n"
            "subject: Test\n"
            "---\n"
            "Content"
        )

        # Attempt path traversal
        result = call_main("verify", "../../../etc/passwd", cwd=tmp_path)

        # Should exit with non-zero code (1=validation error for not found, or 4=security)
        assert result.returncode != 0, f"Should reject path traversal, got exit 0"
        # Should NOT contain sensitive file contents in output
        assert "root:" not in result.stdout
        assert "root:" not in result.stderr

    def test_graph_rejects_dir_path_traversal(self, tmp_path, call_main):
        """graph --dir rejects ../../../etc style paths."""
        # Create minimal setup
        memories_dir = tmp_path / ".serena" / "memories"
        memories_dir.mkdir(parents=True)
        (memories_dir / "test.md").write_text(
            "---\nid: test\n---\nContent"
        )

        # Attempt path traversal via --dir
        result = call_main(
            "graph", "test", "--dir", "../../../etc",
            cwd=tmp_path
        )

        # Should exit with security error (4) or not found (2)
        assert result.returncode in (2, 4), f"Expected exit 2 or 4, got {result.returncode}"

    def test_add_citation_rejects_path_traversal_in_file(self, tmp_path, call_main):
        """add-citation blocks path traversal in --file argument."""
        memories_dir = tmp_path / ".serena" / "memories"
        memories_dir.mkdir(parents=True)

        memory_file = memories_dir / "test-memory.md"
        memory_file.write_text(
            "---\n"
            "id: test-memory\n"
            "subject: Test\n"
            "---\n"
            "Content"
        )

        # Attempt path traversal in --file argument
        result = call_main(
            "add-citation", str(memory_file),
            "--file", "../../../etc/passwd",
            cwd=tmp_path
        )

        # Should fail validation (exit 1) because file is outside repo
        assert result.returncode != 0, "Should reject path traversal"
        # Should not leak file contents
        assert "root:" not in result.stdout
        assert "root:" not in result.stderr


# ============================================================================
# Exit Code Tests
# ============================================================================


class TestExitCodes:
    """Tests for CLI exit codes."""

    def test_verify_returns_0_on_valid(self, tmp_path, call_main):
        """verify exits 0 for memory with valid citations."""
        # Create directory structure
        memories_dir = tmp_path / ".serena" / "memories"
        memories_dir.mkdir(parents=True)

        # Create referenced file
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "test.py").write_text("def hello():\n    pass\n")

        # Create memory with valid citation
        memory_file = memories_dir / "valid-memory.md"
        memory_file.write_text(
            "---\n"
            "id: valid-memory\n"
            "subject: Valid Memory\n"
            "citations:\n"
            "  - path: src/test.py\n"
            "    line: 1\n"
            "    snippet: def hello\n"
            "---\n"
            "Content"
        )

        result = call_main("verify", str(memory_file), cwd=tmp_path)

        assert result.returncode == 0, f"Expected exit 0, got {result.returncode}: {result.stderr}"
        assert "VALID" in result.stdout

    def test_verify_returns_1_on_stale(self, tmp_path, call_main):
        """verify exits 1 for memory with stale citations."""
        memories_dir = tmp_path / ".serena" / "memories"
        memories_dir.mkdir(parents=True)

        # Create memory referencing nonexistent file
        memory_file = memories_dir / "stale-memory.md"
        memory_file.write_text(
            "---\n"
            "id: stale-memory\n"
            "subject: Stale Memory\n"
            "citations:\n"
            "  - path: nonexistent/file.py\n"
            "    line: 1\n"
            "---\n"
            "Content"
        )

        result = call_main("verify", str(memory_file), cwd=tmp_path)

        assert result.returncode == 1, f"Expected exit 1, got {result.returncode}: {result.stderr}"
        assert "STALE" in result.stdout

    def test_verify_returns_nonzero_on_not_found(self, tmp_path, call_main):
        """verify exits non-zero for nonexistent memory."""
        result = call_main("verify", "nonexistent-memory", cwd=tmp_path)

        # CLI uses exit_code param (1 for verify) when memory not found
        assert result.returncode != 0, f"Expected non-zero exit, got {result.returncode}"
        assert "not found" in result.stderr.lower()

    def test_graph_returns_2_on_missing_dir(self, tmp_path, call_main):
        """graph exits 2 for nonexistent directory."""
        result = call_main(
            "graph", "test-root",
            "--dir", "nonexistent/directory",
            cwd=tmp_path
        )

        assert result.returncode == 2, f"Expected exit 2, got {result.returncode}"
        assert "not found" in result.stderr.lower()

    def test_add_citation_returns_1_on_invalid_file(self, tmp_path, call_main):
        """add-citation exits 1 when cited file doesn't exist."""
        memories_dir = tmp_path / ".serena" / "memories"
        memories_dir.mkdir(parents=True)

        memory_file = memories_dir / "test-memory.md"
        memory_file.write_text(
            "---\n"
            "id: test-memory\n"
            "subject: Test\n"
            "---\n"
            "Content"
        )

        result = call_main(
            "add-citation", str(memory_file),
            "--file", "nonexistent/file.py",
            cwd=tmp_path
        )

        # Should fail validation (exit 1)
        assert result.returncode == 1, f"Expected exit 1, got {result.returncode}"

    def test_verify_all_returns_0_when_all_valid(self, tmp_path, call_main):
        """verify-all exits 0 when all memories are valid."""
        memories_dir = tmp_path / ".serena" / "memories"
        memories_dir.mkdir(parents=True)

        # Create referenced file
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "test.py").write_text("def hello():\n    pass\n")

        # Create memory with valid citation
        (memories_dir / "valid-memory.md").write_text(
            "---\n"
            "id: valid-memory\n"
            "subject: Valid\n"
            "citations:\n"
            "  - path: src/test.py\n"
            "    line: 1\n"
            "---\n"
            "Content"
        )

        result = call_main("verify-all", "--dir", str(memories_dir), cwd=tmp_path)

        assert result.returncode == 0, f"Expected exit 0, got {result.returncode}: {result.stderr}"

    def test_verify_all_returns_1_when_any_stale(self, tmp_path, call_main):
        """verify-all exits 1 when any memory has stale citations."""
        memories_dir = tmp_path / ".serena" / "memories"
        memories_dir.mkdir(parents=True)

        # Create memory with stale citation
        (memories_dir / "stale-memory.md").write_text(
            "---\n"
            "id: stale-memory\n"
            "subject: Stale\n"
            "citations:\n"
            "  - path: nonexistent.py\n"
            "    line: 1\n"
            "---\n"
            "Content"
        )

        result = call_main("verify-all", "--dir", str(memories_dir), cwd=tmp_path)

        assert result.returncode == 1, f"Expected exit 1, got {result.returncode}"


# ============================================================================
# CLI JSON Output Schema Tests
# ============================================================================


class TestJsonOutputSchemas:
    """Tests for JSON output format schemas."""

    def test_verify_json_output_schema(self, tmp_path, call_main):
        """verify --json has expected fields."""
        memories_dir = tmp_path / ".serena" / "memories"
        memories_dir.mkdir(parents=True)

        # Create referenced file
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "test.py").write_text("def hello():\n    pass\n")

        # Create memory
        memory_file = memories_dir / "test-memory.md"
        memory_file.write_text(
            "---\n"
            "id: test-memory\n"
            "subject: Test\n"
            "citations:\n"
            "  - path: src/test.py\n"
            "    line: 1\n"
            "    snippet: def hello\n"
            "---\n"
            "Content"
        )

        # --json is a global flag and must come before the subcommand
        result = call_main("--json", "verify", str(memory_file), cwd=tmp_path)

        assert result.returncode == 0, f"CLI failed: {result.stderr}"

        data = json.loads(result.stdout)

        # Required fields
        assert "memory_id" in data
        assert "valid" in data
        assert "confidence" in data
        assert "stale_citations" in data

        # Type checks
        assert isinstance(data["memory_id"], str)
        assert isinstance(data["valid"], bool)
        assert isinstance(data["confidence"], (int, float))
        assert isinstance(data["stale_citations"], list)

    def test_verify_json_stale_citation_schema(self, tmp_path, call_main):
        """verify --json stale_citations have expected fields."""
        memories_dir = tmp_path / ".serena" / "memories"
        memories_dir.mkdir(parents=True)

        # Create memory with stale citation
        memory_file = memories_dir / "stale-memory.md"
        memory_file.write_text(
            "---\n"
            "id: stale-memory\n"
            "subject: Stale\n"
            "citations:\n"
            "  - path: nonexistent.py\n"
            "    line: 10\n"
            "---\n"
            "Content"
        )

        # --json is a global flag and must come before the subcommand
        result = call_main("--json", "verify", str(memory_file), cwd=tmp_path)

        # Will exit 1 due to stale citation, but should still output JSON
        data = json.loads(result.stdout)

        assert not data["valid"]
        assert len(data["stale_citations"]) == 1

        stale = data["stale_citations"][0]
        assert "path" in stale
        assert "line" in stale
        assert "reason" in stale

    def test_verify_all_json_output_schema(self, tmp_path, call_main):
        """verify-all --json has expected fields."""
        memories_dir = tmp_path / ".serena" / "memories"
        memories_dir.mkdir(parents=True)

        # Create referenced file
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "test.py").write_text("def hello():\n    pass\n")

        # Create memory
        (memories_dir / "test-memory.md").write_text(
            "---\n"
            "id: test-memory\n"
            "subject: Test\n"
            "citations:\n"
            "  - path: src/test.py\n"
            "    line: 1\n"
            "---\n"
            "Content"
        )

        # --json is a global flag and must come before the subcommand
        result = call_main(
            "--json", "verify-all", "--dir", str(memories_dir),
            cwd=tmp_path
        )

        assert result.returncode == 0, f"CLI failed: {result.stderr}"

        data = json.loads(result.stdout)

        # Required fields
        assert "results" in data
        assert "parse_failures" in data

        # Type checks
        assert isinstance(data["results"], list)
        assert isinstance(data["parse_failures"], int)

        # Each result has expected fields
        if data["results"]:
            result_entry = data["results"][0]
            assert "memory_id" in result_entry
            assert "valid" in result_entry
            assert "confidence" in result_entry

    def test_graph_json_output_schema(self, tmp_path, call_main):
        """graph --json has expected fields."""
        memories_dir = tmp_path / ".serena" / "memories"
        memories_dir.mkdir(parents=True)

        # Create linked memories
        (memories_dir / "memory-a.md").write_text(
            "---\n"
            "id: memory-a\n"
            "links:\n"
            "  - target: memory-b\n"
            "    type: RELATED\n"
            "---\n"
            "Content"
        )
        (memories_dir / "memory-b.md").write_text(
            "---\n"
            "id: memory-b\n"
            "---\n"
            "Content"
        )

        # --json is a global flag and must come before the subcommand
        result = call_main(
            "--json", "graph", "memory-a", "--dir", str(memories_dir),
            cwd=tmp_path
        )

        assert result.returncode == 0, f"CLI failed: {result.stderr}"

        data = json.loads(result.stdout)

        # Required fields
        assert "root_id" in data
        assert "strategy" in data
        assert "max_depth" in data
        assert "nodes" in data
        assert "cycles" in data

        # Type checks
        assert isinstance(data["root_id"], str)
        assert isinstance(data["strategy"], str)
        assert isinstance(data["max_depth"], int)
        assert isinstance(data["nodes"], list)
        assert isinstance(data["cycles"], list)

        # Node structure
        if data["nodes"]:
            node = data["nodes"][0]
            assert "memory_id" in node
            assert "depth" in node
            # parent and link_type can be None for root

    def test_health_json_output_format(self, tmp_path, call_main):
        """health --format json outputs valid JSON with summary."""
        memories_dir = tmp_path / ".serena" / "memories"
        memories_dir.mkdir(parents=True)

        # Create memory
        (memories_dir / "test-memory.md").write_text(
            "---\n"
            "id: test-memory\n"
            "subject: Test\n"
            "---\n"
            "Content"
        )

        result = call_main(
            "health", "--format", "json", "--dir", str(memories_dir),
            cwd=tmp_path
        )

        assert result.returncode == 0, f"CLI failed: {result.stderr}"

        data = json.loads(result.stdout)

        # Required summary fields
        assert "summary" in data
        summary = data["summary"]
        assert "total_memories" in summary
        assert "memories_with_citations" in summary
        assert "valid_memories" in summary
        assert "stale_memories" in summary
        assert "average_confidence" in summary

    def test_health_text_format(self, tmp_path, call_main):
        """health --format text outputs markdown."""
        memories_dir = tmp_path / ".serena" / "memories"
        memories_dir.mkdir(parents=True)

        (memories_dir / "test-memory.md").write_text(
            "---\n"
            "id: test-memory\n"
            "subject: Test\n"
            "---\n"
            "Content"
        )

        result = call_main(
            "health", "--format", "text", "--dir", str(memories_dir),
            cwd=tmp_path
        )

        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        # Text format produces markdown
        assert "# Memory Health Report" in result.stdout
        assert "## Summary" in result.stdout

    def test_health_markdown_format(self, tmp_path, call_main):
        """health --format markdown outputs markdown."""
        memories_dir = tmp_path / ".serena" / "memories"
        memories_dir.mkdir(parents=True)

        (memories_dir / "test-memory.md").write_text(
            "---\n"
            "id: test-memory\n"
            "subject: Test\n"
            "---\n"
            "Content"
        )

        result = call_main(
            "health", "--format", "markdown", "--dir", str(memories_dir),
            cwd=tmp_path
        )

        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        assert "# Memory Health Report" in result.stdout


# ============================================================================
# Memory Path Resolution Tests
# ============================================================================


class TestMemoryPathResolution:
    """Tests for memory ID vs path resolution."""

    def test_verify_accepts_memory_id(self, tmp_path, call_main):
        """verify resolves 'memory-id' to .serena/memories/memory-id.md."""
        memories_dir = tmp_path / ".serena" / "memories"
        memories_dir.mkdir(parents=True)

        # Create memory file
        (memories_dir / "my-memory.md").write_text(
            "---\n"
            "id: my-memory\n"
            "subject: Test\n"
            "---\n"
            "Content"
        )

        result = call_main("verify", "my-memory", cwd=tmp_path)

        assert result.returncode == 0, f"Expected exit 0, got {result.returncode}: {result.stderr}"
        assert "VALID" in result.stdout

    def test_verify_accepts_full_path(self, tmp_path, call_main):
        """verify accepts explicit file path."""
        memories_dir = tmp_path / "custom" / "location"
        memories_dir.mkdir(parents=True)

        memory_file = memories_dir / "my-memory.md"
        memory_file.write_text(
            "---\n"
            "id: my-memory\n"
            "subject: Test\n"
            "---\n"
            "Content"
        )

        result = call_main("verify", str(memory_file), cwd=tmp_path)

        assert result.returncode == 0, f"Expected exit 0, got {result.returncode}: {result.stderr}"

    def test_verify_prefers_existing_path_over_id_resolution(self, tmp_path, call_main):
        """verify uses existing path before trying ID resolution."""
        # Create a file that could be confused with memory ID resolution
        memories_dir = tmp_path / ".serena" / "memories"
        memories_dir.mkdir(parents=True)

        # Create direct path file
        direct_file = tmp_path / "test-memory.md"
        direct_file.write_text(
            "---\n"
            "id: direct-memory\n"
            "subject: Direct\n"
            "---\n"
            "Direct content"
        )

        # Create memory in standard location
        (memories_dir / "test-memory.md").write_text(
            "---\n"
            "id: resolved-memory\n"
            "subject: Resolved\n"
            "---\n"
            "Resolved content"
        )

        # --json is a global flag and must come before the subcommand
        result = call_main("--json", "verify", "test-memory.md", cwd=tmp_path)

        data = json.loads(result.stdout)
        # Should use the direct path (file exists), not ID resolution
        assert data["memory_id"] == "direct-memory"


# ============================================================================
# Edge Cases
# ============================================================================


class TestEdgeCases:
    """Edge case tests for CLI behavior."""

    def test_verify_memory_without_citations(self, tmp_path, call_main):
        """verify succeeds for memory with no citations."""
        memories_dir = tmp_path / ".serena" / "memories"
        memories_dir.mkdir(parents=True)

        (memories_dir / "no-citations.md").write_text(
            "---\n"
            "id: no-citations\n"
            "subject: No Citations\n"
            "---\n"
            "Content without citations"
        )

        result = call_main(
            "verify", str(memories_dir / "no-citations.md"),
            cwd=tmp_path
        )

        assert result.returncode == 0, f"Expected exit 0, got {result.returncode}"
        assert "VALID" in result.stdout

    def test_verify_all_empty_directory(self, tmp_path, call_main):
        """verify-all handles empty directory."""
        memories_dir = tmp_path / ".serena" / "memories"
        memories_dir.mkdir(parents=True)

        result = call_main("verify-all", "--dir", str(memories_dir), cwd=tmp_path)

        assert result.returncode == 0, f"Expected exit 0, got {result.returncode}"
        # Should report 0 memories verified
        assert "0 memories" in result.stdout.lower()

    def test_graph_root_not_found(self, tmp_path, call_main):
        """graph exits 2 when root memory doesn't exist."""
        memories_dir = tmp_path / ".serena" / "memories"
        memories_dir.mkdir(parents=True)

        # Create one memory but ask for different root
        (memories_dir / "existing.md").write_text(
            "---\n"
            "id: existing\n"
            "---\n"
            "Content"
        )

        result = call_main(
            "graph", "nonexistent-root", "--dir", str(memories_dir),
            cwd=tmp_path
        )

        assert result.returncode == 2, f"Expected exit 2, got {result.returncode}"
        assert "not found" in result.stderr.lower()

    def test_add_citation_dry_run(self, tmp_path, call_main):
        """add-citation --dry-run previews without writing."""
        memories_dir = tmp_path / ".serena" / "memories"
        memories_dir.mkdir(parents=True)

        memory_file = memories_dir / "test-memory.md"
        original_content = (
            "---\n"
            "id: test-memory\n"
            "subject: Test\n"
            "---\n"
            "Content"
        )
        memory_file.write_text(original_content)

        # Create file to cite
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "test.py").write_text("def hello():\n    pass\n")

        result = call_main(
            "add-citation", str(memory_file),
            "--file", "src/test.py",
            "--line", "1",
            "--dry-run",
            cwd=tmp_path
        )

        assert result.returncode == 0
        assert "[DRY RUN]" in result.stdout

        # File should be unchanged
        assert memory_file.read_text() == original_content


# ============================================================================
# Path Resolution Regression Tests (CWE-22 security fix)
# ============================================================================


def test_resolve_memory_path_returns_resolved_absolute_path(tmp_path, monkeypatch):
    """_resolve_memory_path returns a fully resolved absolute path."""
    monkeypatch.chdir(tmp_path)
    memories_dir = tmp_path / ".serena" / "memories"
    memories_dir.mkdir(parents=True)
    (memories_dir / "test-mem.md").write_text("---\nid: test-mem\n---\nContent")

    result = _resolve_memory_path("test-mem")

    assert result.is_absolute()
    assert result == (memories_dir / "test-mem.md").resolve()


def test_resolve_directory_path_returns_resolved_absolute_path(tmp_path, monkeypatch):
    """_resolve_directory_path returns a fully resolved absolute path."""
    monkeypatch.chdir(tmp_path)
    target_dir = tmp_path / "memories"
    target_dir.mkdir()

    result = _resolve_directory_path("memories")

    assert result.is_absolute()
    assert result == (tmp_path / "memories").resolve()


# ============================================================================
# Corrupt YAML Handling Tests
# ============================================================================


def test_verify_returns_1_on_corrupt_yaml(tmp_path, call_main):
    """verify command returns EXIT_VALIDATION_ERROR for corrupt YAML."""
    memories_dir = tmp_path / ".serena" / "memories"
    memories_dir.mkdir(parents=True)
    corrupt_file = memories_dir / "corrupt.md"
    corrupt_file.write_text("---\nid: [unclosed\n---\nContent")

    result = call_main("verify", str(corrupt_file), cwd=tmp_path)
    assert result.returncode == 1
    assert "Failed to parse" in result.stderr or "Error" in result.stderr


def test_list_citations_returns_1_on_corrupt_yaml(tmp_path, call_main):
    """list-citations command returns EXIT_VALIDATION_ERROR for corrupt YAML."""
    memories_dir = tmp_path / ".serena" / "memories"
    memories_dir.mkdir(parents=True)
    corrupt_file = memories_dir / "corrupt.md"
    corrupt_file.write_text("---\nid: [unclosed\n---\nContent")

    result = call_main("list-citations", str(corrupt_file), cwd=tmp_path)
    assert result.returncode == 1
    assert "Error" in result.stderr


def test_update_confidence_returns_1_on_corrupt_yaml(tmp_path, call_main):
    """update-confidence command returns EXIT_VALIDATION_ERROR for corrupt YAML."""
    memories_dir = tmp_path / ".serena" / "memories"
    memories_dir.mkdir(parents=True)
    corrupt_file = memories_dir / "corrupt.md"
    corrupt_file.write_text("---\nid: [unclosed\n---\nContent")

    result = call_main("update-confidence", str(corrupt_file), cwd=tmp_path)
    assert result.returncode == 1
    assert "Error" in result.stderr


def test_add_citation_returns_1_on_corrupt_yaml(tmp_path, call_main):
    """add-citation command returns EXIT_VALIDATION_ERROR for corrupt YAML."""
    memories_dir = tmp_path / ".serena" / "memories"
    memories_dir.mkdir(parents=True)
    corrupt_file = memories_dir / "corrupt.md"
    corrupt_file.write_text("---\nid: [unclosed\n---\nContent")

    result = call_main(
        "add-citation", str(corrupt_file),
        "--file", "some/file.py",
        cwd=tmp_path,
    )
    assert result.returncode == 1
    assert "Validation failed" in result.stderr or "Error" in result.stderr


# ============================================================================
# Happy-Path Coverage Tests
# ============================================================================


class TestGraphTextOutput:
    """Tests for graph command text output (non-JSON)."""

    def test_graph_text_output(self, tmp_path, call_main):
        """graph without --json outputs human-readable text."""
        memories_dir = tmp_path / ".serena" / "memories"
        memories_dir.mkdir(parents=True)

        (memories_dir / "memory-a.md").write_text(
            "---\n"
            "id: memory-a\n"
            "links:\n"
            "  - target: memory-b\n"
            "    type: RELATED\n"
            "---\n"
            "Content"
        )
        (memories_dir / "memory-b.md").write_text(
            "---\n"
            "id: memory-b\n"
            "---\n"
            "Content"
        )

        result = call_main(
            "graph", "memory-a", "--dir", str(memories_dir),
            cwd=tmp_path,
        )

        assert result.returncode == 0
        assert "Graph Traversal" in result.stdout
        assert "Root: memory-a" in result.stdout
        assert "Traversal order:" in result.stdout
        assert "memory-a" in result.stdout

    def test_graph_text_output_with_cycles(self, tmp_path, call_main):
        """graph text output shows cycles section when cycles exist."""
        memories_dir = tmp_path / ".serena" / "memories"
        memories_dir.mkdir(parents=True)

        (memories_dir / "cycle-a.md").write_text(
            "---\n"
            "id: cycle-a\n"
            "links:\n"
            "  - target: cycle-b\n"
            "    type: RELATED\n"
            "---\n"
            "Content"
        )
        (memories_dir / "cycle-b.md").write_text(
            "---\n"
            "id: cycle-b\n"
            "links:\n"
            "  - target: cycle-a\n"
            "    type: RELATED\n"
            "---\n"
            "Content"
        )

        result = call_main(
            "graph", "cycle-a", "--dir", str(memories_dir),
            cwd=tmp_path,
        )

        assert result.returncode == 0
        assert "Cycles:" in result.stdout


class TestUpdateConfidenceHappyPath:
    """Tests for update-confidence command success paths."""

    def test_update_confidence_valid_memory(self, tmp_path, call_main):
        """update-confidence outputs updated confidence for valid memory."""
        memories_dir = tmp_path / ".serena" / "memories"
        memories_dir.mkdir(parents=True)

        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "test.py").write_text("def hello():\n    pass\n")

        (memories_dir / "my-mem.md").write_text(
            "---\n"
            "id: my-mem\n"
            "subject: Test\n"
            "citations:\n"
            "  - path: src/test.py\n"
            "    line: 1\n"
            "    snippet: def hello\n"
            "---\n"
            "Content"
        )

        result = call_main(
            "update-confidence", str(memories_dir / "my-mem.md"),
            cwd=tmp_path,
        )

        assert result.returncode == 0
        assert "Confidence updated:" in result.stdout


class TestListCitationsHappyPath:
    """Tests for list-citations command success paths."""

    def test_list_citations_with_valid_citations(self, tmp_path, call_main):
        """list-citations shows citation status for memory with citations."""
        memories_dir = tmp_path / ".serena" / "memories"
        memories_dir.mkdir(parents=True)

        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "test.py").write_text("def hello():\n    pass\n")

        (memories_dir / "cited-mem.md").write_text(
            "---\n"
            "id: cited-mem\n"
            "subject: Test\n"
            "citations:\n"
            "  - path: src/test.py\n"
            "    line: 1\n"
            "    snippet: def hello\n"
            "---\n"
            "Content"
        )

        result = call_main(
            "list-citations", str(memories_dir / "cited-mem.md"),
            cwd=tmp_path,
        )

        assert result.returncode == 0
        assert "Citations in cited-mem:" in result.stdout
        assert "VALID" in result.stdout

    def test_list_citations_no_citations(self, tmp_path, call_main):
        """list-citations reports no citations for memory without any."""
        memories_dir = tmp_path / ".serena" / "memories"
        memories_dir.mkdir(parents=True)

        (memories_dir / "empty-mem.md").write_text(
            "---\n"
            "id: empty-mem\n"
            "subject: No Citations\n"
            "---\n"
            "Content"
        )

        result = call_main(
            "list-citations", str(memories_dir / "empty-mem.md"),
            cwd=tmp_path,
        )

        assert result.returncode == 0
        assert "No citations" in result.stdout

    def test_list_citations_with_stale_citation(self, tmp_path, call_main):
        """list-citations shows INVALID for stale citation with reason."""
        memories_dir = tmp_path / ".serena" / "memories"
        memories_dir.mkdir(parents=True)

        (memories_dir / "stale-mem.md").write_text(
            "---\n"
            "id: stale-mem\n"
            "subject: Test\n"
            "citations:\n"
            "  - path: nonexistent.py\n"
            "    line: 1\n"
            "---\n"
            "Content"
        )

        result = call_main(
            "list-citations", str(memories_dir / "stale-mem.md"),
            cwd=tmp_path,
        )

        assert result.returncode == 0
        assert "INVALID" in result.stdout
        assert "Reason:" in result.stdout


class TestAddCitationHappyPath:
    """Tests for add-citation command success path."""

    def test_add_citation_success(self, tmp_path, call_main):
        """add-citation adds a citation and reports success."""
        memories_dir = tmp_path / ".serena" / "memories"
        memories_dir.mkdir(parents=True)

        memory_file = memories_dir / "target-mem.md"
        memory_file.write_text(
            "---\n"
            "id: target-mem\n"
            "subject: Test\n"
            "---\n"
            "Content"
        )

        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "test.py").write_text("def hello():\n    pass\n")

        result = call_main(
            "add-citation", str(memory_file),
            "--file", "src/test.py",
            "--line", "1",
            "--snippet", "def hello",
            cwd=tmp_path,
        )

        assert result.returncode == 0
        assert "Citation added" in result.stdout


class TestVerifyAllTextWithParseFailures:
    """Tests for verify-all text output with parse failures."""

    def test_verify_all_text_shows_parse_failures(self, tmp_path, call_main):
        """verify-all text output reports parse failures count."""
        memories_dir = tmp_path / ".serena" / "memories"
        memories_dir.mkdir(parents=True)

        # Create a corrupt memory that will fail parsing
        (memories_dir / "corrupt.md").write_text(
            "---\nid: [unclosed\n---\nContent"
        )
        # Create a valid memory (no citations)
        (memories_dir / "valid.md").write_text(
            "---\nid: valid\nsubject: Test\n---\nContent"
        )

        result = call_main(
            "verify-all", "--dir", str(memories_dir),
            cwd=tmp_path,
        )

        # Should still succeed (parse failures are warnings, not fatal)
        assert "could not be parsed" in result.stderr


class TestDirectoryPathEdgeCases:
    """Tests for _resolve_directory_path edge cases."""

    def test_file_passed_as_directory(self, tmp_path, call_main):
        """Passing a file path where directory expected gives validation error."""
        some_file = tmp_path / "not-a-dir.txt"
        some_file.write_text("I am a file")

        result = call_main(
            "verify-all", "--dir", str(some_file),
            cwd=tmp_path,
        )

        assert result.returncode == 1
        assert "Not a directory" in result.stderr


class TestUpdateConfidenceWithStaleCitations:
    """Tests for update-confidence stale citation warning path."""

    def test_update_confidence_shows_stale_warning(self, tmp_path, call_main):
        """update-confidence warns about stale citations."""
        memories_dir = tmp_path / ".serena" / "memories"
        memories_dir.mkdir(parents=True)

        (memories_dir / "stale-mem.md").write_text(
            "---\n"
            "id: stale-mem\n"
            "subject: Test\n"
            "citations:\n"
            "  - path: nonexistent.py\n"
            "    line: 1\n"
            "---\n"
            "Content"
        )

        result = call_main(
            "update-confidence", str(memories_dir / "stale-mem.md"),
            cwd=tmp_path,
        )

        assert result.returncode == 0
        assert "Confidence updated:" in result.stdout
        assert "stale citations found:" in result.stdout


class TestHandlerErrorPaths:
    """Tests for handler exception branches via monkeypatching."""

    def test_graph_file_not_found_on_init(self, tmp_path, call_main, monkeypatch):
        """graph returns 2 when MemoryGraph init raises FileNotFoundError."""
        memories_dir = tmp_path / ".serena" / "memories"
        memories_dir.mkdir(parents=True)
        (memories_dir / "test.md").write_text("---\nid: test\n---\nContent")

        def _raise_fnf(path):
            raise FileNotFoundError("mocked")

        monkeypatch.setattr(
            "scripts.memory_enhancement.__main__.MemoryGraph", _raise_fnf
        )

        result = call_main(
            "graph", "test", "--dir", str(memories_dir), cwd=tmp_path
        )

        assert result.returncode == 2
        assert "mocked" in result.stderr

    def test_add_citation_file_not_found(self, tmp_path, call_main, monkeypatch):
        """add-citation returns 2 when add_citation_to_memory raises FileNotFoundError."""
        memories_dir = tmp_path / ".serena" / "memories"
        memories_dir.mkdir(parents=True)
        memory_file = memories_dir / "test-mem.md"
        memory_file.write_text("---\nid: test-mem\nsubject: T\n---\nContent")

        def _raise_fnf(**kwargs):
            raise FileNotFoundError("cited file missing")

        monkeypatch.setattr(
            "scripts.memory_enhancement.__main__.add_citation_to_memory", _raise_fnf
        )

        result = call_main(
            "add-citation", str(memory_file),
            "--file", "src/test.py", cwd=tmp_path,
        )

        assert result.returncode == 2
        assert "cited file missing" in result.stderr

    def test_update_confidence_file_not_found(self, tmp_path, call_main, monkeypatch):
        """update-confidence returns 2 when verify/update raises FileNotFoundError."""
        memories_dir = tmp_path / ".serena" / "memories"
        memories_dir.mkdir(parents=True)
        memory_file = memories_dir / "test-mem.md"
        memory_file.write_text(
            "---\nid: test-mem\nsubject: T\n---\nContent"
        )

        def _raise_fnf(memory):
            raise FileNotFoundError("missing file")

        monkeypatch.setattr(
            "scripts.memory_enhancement.__main__.verify_memory", _raise_fnf
        )

        result = call_main(
            "update-confidence", str(memory_file), cwd=tmp_path,
        )

        assert result.returncode == 2
        assert "missing file" in result.stderr

    def test_update_confidence_io_error(self, tmp_path, call_main, monkeypatch):
        """update-confidence returns 3 when update raises OSError."""
        memories_dir = tmp_path / ".serena" / "memories"
        memories_dir.mkdir(parents=True)
        memory_file = memories_dir / "test-mem.md"
        memory_file.write_text(
            "---\nid: test-mem\nsubject: T\n---\nContent"
        )

        def _raise_io(memory, verification):
            raise IOError("write failed")

        monkeypatch.setattr(
            "scripts.memory_enhancement.__main__.update_confidence", _raise_io
        )

        result = call_main(
            "update-confidence", str(memory_file), cwd=tmp_path,
        )

        assert result.returncode == 3
        assert "write failed" in result.stderr

    def test_add_citation_os_error(self, tmp_path, call_main, monkeypatch):
        """add-citation returns 3 when add_citation_to_memory raises OSError."""
        memories_dir = tmp_path / ".serena" / "memories"
        memories_dir.mkdir(parents=True)
        memory_file = memories_dir / "test-mem.md"
        memory_file.write_text("---\nid: test-mem\nsubject: T\n---\nContent")

        def _raise_os(**kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(
            "scripts.memory_enhancement.__main__.add_citation_to_memory", _raise_os
        )

        result = call_main(
            "add-citation", str(memory_file),
            "--file", "src/test.py", cwd=tmp_path,
        )

        assert result.returncode == 3
        assert "disk full" in result.stderr

    def test_list_citations_os_error(self, tmp_path, call_main, monkeypatch):
        """list-citations returns 3 when list_citations_with_status raises OSError."""
        memories_dir = tmp_path / ".serena" / "memories"
        memories_dir.mkdir(parents=True)
        memory_file = memories_dir / "test-mem.md"
        memory_file.write_text("---\nid: test-mem\nsubject: T\n---\nContent")

        def _raise_os(path, **kwargs):
            raise OSError("permission denied")

        monkeypatch.setattr(
            "scripts.memory_enhancement.__main__.list_citations_with_status", _raise_os
        )

        result = call_main(
            "list-citations", str(memory_file), cwd=tmp_path,
        )

        assert result.returncode == 3
        assert "permission denied" in result.stderr

    def test_list_citations_file_not_found(self, tmp_path, call_main, monkeypatch):
        """list-citations returns 2 when list_citations_with_status raises FileNotFoundError."""
        memories_dir = tmp_path / ".serena" / "memories"
        memories_dir.mkdir(parents=True)
        memory_file = memories_dir / "test-mem.md"
        memory_file.write_text(
            "---\nid: test-mem\nsubject: T\n---\nContent"
        )

        def _raise_fnf(path):
            raise FileNotFoundError("gone")

        monkeypatch.setattr(
            "scripts.memory_enhancement.__main__.list_citations_with_status", _raise_fnf
        )

        result = call_main(
            "list-citations", str(memory_file), cwd=tmp_path,
        )

        assert result.returncode == 2
        assert "gone" in result.stderr

class TestResolvePathTraversalExceptionPaths:
    """Tests for path traversal exception branches in resolve functions."""

    def test_resolve_memory_path_traversal_raises_cli_error(self, tmp_path, monkeypatch):
        """_resolve_memory_path raises CLIError on path traversal."""
        monkeypatch.chdir(tmp_path)
        # Create a file outside cwd that is reachable via traversal
        outside = tmp_path.parent / "outside-test-file.md"
        try:
            outside.write_text("---\nid: test\n---\nContent")
            # Use relative path that escapes cwd
            with pytest.raises(CLIError) as exc_info:
                _resolve_memory_path(str(outside))
            assert exc_info.value.exit_code == 4
        finally:
            outside.unlink(missing_ok=True)

    def test_resolve_directory_path_traversal_raises_cli_error(self, tmp_path, monkeypatch):
        """_resolve_directory_path raises CLIError on path traversal."""
        monkeypatch.chdir(tmp_path)
        # Parent directory is outside cwd
        with pytest.raises(CLIError) as exc_info:
            _resolve_directory_path(str(tmp_path.parent))
        assert exc_info.value.exit_code == 4

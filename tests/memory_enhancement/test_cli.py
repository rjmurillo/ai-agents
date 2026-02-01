"""CLI integration tests for memory enhancement layer.

Tests CLI invocation via subprocess to verify:
- Exit codes for various conditions
- JSON output schemas
- Path traversal security (CWE-22)
- Memory path resolution
- Corrupt YAML error handling
- Path resolution regression (CWE-22 fix)
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.memory_enhancement.__main__ import _resolve_directory_path, _resolve_memory_path


def run_cli(*args: str, cwd: Path = None) -> subprocess.CompletedProcess:
    """Run the memory enhancement CLI with the given arguments.

    Args:
        *args: CLI arguments to pass
        cwd: Working directory for the command

    Returns:
        CompletedProcess with returncode, stdout, stderr
    """
    cmd = [sys.executable, "-m", "scripts.memory_enhancement", *args]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=cwd,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent.parent)},
    )


# ============================================================================
# Path Traversal Security Tests (CWE-22)
# ============================================================================


class TestPathTraversalSecurity:
    """Tests for CWE-22 path traversal protection."""

    def test_verify_rejects_path_traversal(self, tmp_path):
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
        result = run_cli("verify", "../../../etc/passwd", cwd=tmp_path)

        # Should exit with non-zero code (1=validation error for not found, or 4=security)
        # The CLI exits with the exit_code parameter (1) when file not found
        assert result.returncode != 0, f"Should reject path traversal, got exit 0"
        # Should NOT contain sensitive file contents in output
        assert "root:" not in result.stdout
        assert "root:" not in result.stderr

    def test_graph_rejects_dir_path_traversal(self, tmp_path):
        """graph --dir rejects ../../../etc style paths."""
        # Create minimal setup
        memories_dir = tmp_path / ".serena" / "memories"
        memories_dir.mkdir(parents=True)
        (memories_dir / "test.md").write_text(
            "---\nid: test\n---\nContent"
        )

        # Attempt path traversal via --dir
        result = run_cli(
            "graph", "test", "--dir", "../../../etc",
            cwd=tmp_path
        )

        # Should exit with security error (4) or not found (2)
        assert result.returncode in (2, 4), f"Expected exit 2 or 4, got {result.returncode}"

    def test_add_citation_rejects_path_traversal_in_file(self, tmp_path):
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
        result = run_cli(
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

    def test_verify_returns_0_on_valid(self, tmp_path):
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

        result = run_cli("verify", str(memory_file), cwd=tmp_path)

        assert result.returncode == 0, f"Expected exit 0, got {result.returncode}: {result.stderr}"
        assert "VALID" in result.stdout

    def test_verify_returns_1_on_stale(self, tmp_path):
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

        result = run_cli("verify", str(memory_file), cwd=tmp_path)

        assert result.returncode == 1, f"Expected exit 1, got {result.returncode}: {result.stderr}"
        assert "STALE" in result.stdout

    def test_verify_returns_nonzero_on_not_found(self, tmp_path):
        """verify exits non-zero for nonexistent memory."""
        result = run_cli("verify", "nonexistent-memory", cwd=tmp_path)

        # CLI uses exit_code param (1 for verify) when memory not found
        assert result.returncode != 0, f"Expected non-zero exit, got {result.returncode}"
        assert "not found" in result.stderr.lower()

    def test_graph_returns_2_on_missing_dir(self, tmp_path):
        """graph exits 2 for nonexistent directory."""
        result = run_cli(
            "graph", "test-root",
            "--dir", "nonexistent/directory",
            cwd=tmp_path
        )

        assert result.returncode == 2, f"Expected exit 2, got {result.returncode}"
        assert "not found" in result.stderr.lower()

    def test_add_citation_returns_1_on_invalid_file(self, tmp_path):
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

        result = run_cli(
            "add-citation", str(memory_file),
            "--file", "nonexistent/file.py",
            cwd=tmp_path
        )

        # Should fail validation (exit 1)
        assert result.returncode == 1, f"Expected exit 1, got {result.returncode}"

    def test_verify_all_returns_0_when_all_valid(self, tmp_path):
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

        result = run_cli("verify-all", "--dir", str(memories_dir), cwd=tmp_path)

        assert result.returncode == 0, f"Expected exit 0, got {result.returncode}: {result.stderr}"

    def test_verify_all_returns_1_when_any_stale(self, tmp_path):
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

        result = run_cli("verify-all", "--dir", str(memories_dir), cwd=tmp_path)

        assert result.returncode == 1, f"Expected exit 1, got {result.returncode}"


# ============================================================================
# CLI JSON Output Schema Tests
# ============================================================================


class TestJsonOutputSchemas:
    """Tests for JSON output format schemas."""

    def test_verify_json_output_schema(self, tmp_path):
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
        result = run_cli("--json", "verify", str(memory_file), cwd=tmp_path)

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

    def test_verify_json_stale_citation_schema(self, tmp_path):
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
        result = run_cli("--json", "verify", str(memory_file), cwd=tmp_path)

        # Will exit 1 due to stale citation, but should still output JSON
        data = json.loads(result.stdout)

        assert not data["valid"]
        assert len(data["stale_citations"]) == 1

        stale = data["stale_citations"][0]
        assert "path" in stale
        assert "line" in stale
        assert "reason" in stale

    def test_verify_all_json_output_schema(self, tmp_path):
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
        result = run_cli(
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

    def test_graph_json_output_schema(self, tmp_path):
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
        result = run_cli(
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

    def test_health_json_output_format(self, tmp_path):
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

        result = run_cli(
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

    def test_health_text_format(self, tmp_path):
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

        result = run_cli(
            "health", "--format", "text", "--dir", str(memories_dir),
            cwd=tmp_path
        )

        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        # Text format produces markdown
        assert "# Memory Health Report" in result.stdout
        assert "## Summary" in result.stdout

    def test_health_markdown_format(self, tmp_path):
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

        result = run_cli(
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

    def test_verify_accepts_memory_id(self, tmp_path):
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

        result = run_cli("verify", "my-memory", cwd=tmp_path)

        assert result.returncode == 0, f"Expected exit 0, got {result.returncode}: {result.stderr}"
        assert "VALID" in result.stdout

    def test_verify_accepts_full_path(self, tmp_path):
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

        result = run_cli("verify", str(memory_file), cwd=tmp_path)

        assert result.returncode == 0, f"Expected exit 0, got {result.returncode}: {result.stderr}"

    def test_verify_prefers_existing_path_over_id_resolution(self, tmp_path):
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
        result = run_cli("--json", "verify", "test-memory.md", cwd=tmp_path)

        data = json.loads(result.stdout)
        # Should use the direct path (file exists), not ID resolution
        assert data["memory_id"] == "direct-memory"


# ============================================================================
# Edge Cases
# ============================================================================


class TestEdgeCases:
    """Edge case tests for CLI behavior."""

    def test_verify_memory_without_citations(self, tmp_path):
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

        result = run_cli(
            "verify", str(memories_dir / "no-citations.md"),
            cwd=tmp_path
        )

        assert result.returncode == 0, f"Expected exit 0, got {result.returncode}"
        assert "VALID" in result.stdout

    def test_verify_all_empty_directory(self, tmp_path):
        """verify-all handles empty directory."""
        memories_dir = tmp_path / ".serena" / "memories"
        memories_dir.mkdir(parents=True)

        result = run_cli("verify-all", "--dir", str(memories_dir), cwd=tmp_path)

        assert result.returncode == 0, f"Expected exit 0, got {result.returncode}"
        # Should report 0 memories verified
        assert "0 memories" in result.stdout.lower()

    def test_graph_root_not_found(self, tmp_path):
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

        result = run_cli(
            "graph", "nonexistent-root", "--dir", str(memories_dir),
            cwd=tmp_path
        )

        assert result.returncode == 2, f"Expected exit 2, got {result.returncode}"
        assert "not found" in result.stderr.lower()

    def test_add_citation_dry_run(self, tmp_path):
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

        result = run_cli(
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


def test_verify_returns_1_on_corrupt_yaml(tmp_path):
    """verify command returns EXIT_VALIDATION_ERROR for corrupt YAML."""
    memories_dir = tmp_path / ".serena" / "memories"
    memories_dir.mkdir(parents=True)
    corrupt_file = memories_dir / "corrupt.md"
    corrupt_file.write_text("---\nid: [unclosed\n---\nContent")

    result = run_cli("verify", str(corrupt_file), cwd=tmp_path)
    assert result.returncode == 1
    assert "Failed to parse" in result.stderr or "Error" in result.stderr


def test_list_citations_returns_1_on_corrupt_yaml(tmp_path):
    """list-citations command returns EXIT_VALIDATION_ERROR for corrupt YAML."""
    memories_dir = tmp_path / ".serena" / "memories"
    memories_dir.mkdir(parents=True)
    corrupt_file = memories_dir / "corrupt.md"
    corrupt_file.write_text("---\nid: [unclosed\n---\nContent")

    result = run_cli("list-citations", str(corrupt_file), cwd=tmp_path)
    assert result.returncode == 1
    assert "Error" in result.stderr


def test_update_confidence_returns_1_on_corrupt_yaml(tmp_path):
    """update-confidence command returns EXIT_VALIDATION_ERROR for corrupt YAML."""
    memories_dir = tmp_path / ".serena" / "memories"
    memories_dir.mkdir(parents=True)
    corrupt_file = memories_dir / "corrupt.md"
    corrupt_file.write_text("---\nid: [unclosed\n---\nContent")

    result = run_cli("update-confidence", str(corrupt_file), cwd=tmp_path)
    assert result.returncode == 1
    assert "Error" in result.stderr


def test_add_citation_returns_1_on_corrupt_yaml(tmp_path):
    """add-citation command returns EXIT_VALIDATION_ERROR for corrupt YAML."""
    memories_dir = tmp_path / ".serena" / "memories"
    memories_dir.mkdir(parents=True)
    corrupt_file = memories_dir / "corrupt.md"
    corrupt_file.write_text("---\nid: [unclosed\n---\nContent")

    result = run_cli(
        "add-citation", str(corrupt_file),
        "--file", "some/file.py",
        cwd=tmp_path,
    )
    assert result.returncode == 1
    assert "Validation failed" in result.stderr or "Error" in result.stderr

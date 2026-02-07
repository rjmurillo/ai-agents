"""Tests for memory_enhancement CLI (__main__.py)."""

import json
import subprocess
import sys
from pathlib import Path


def run_cli(*args: str, cwd: str | Path | None = None) -> subprocess.CompletedProcess:
    """Run the memory_enhancement CLI as a subprocess."""
    return subprocess.run(
        [sys.executable, "-m", "memory_enhancement", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
    )


class TestVerifyCommand:
    """Tests for the verify subcommand."""

    def test_verify_valid_memory(self, tmp_path):
        (tmp_path / "src.py").write_text("import os\ndef main():\n    pass\n")
        mem_dir = tmp_path / ".serena" / "memories"
        mem_dir.mkdir(parents=True)
        (mem_dir / "test-mem.md").write_text(
            "---\n"
            "id: test-mem\n"
            "citations:\n"
            "  - path: src.py\n"
            "    line: 2\n"
            "    snippet: 'def main():'\n"
            "---\n"
            "\n"
            "Test memory.\n"
        )

        result = run_cli(
            "verify", "test-mem",
            "--dir", str(mem_dir),
            "--repo-root", str(tmp_path),
        )

        assert result.returncode == 0
        assert "[PASS]" in result.stdout

    def test_verify_stale_memory(self, tmp_path):
        mem_dir = tmp_path / ".serena" / "memories"
        mem_dir.mkdir(parents=True)
        (mem_dir / "stale-mem.md").write_text(
            "---\n"
            "id: stale-mem\n"
            "citations:\n"
            "  - path: nonexistent.py\n"
            "    line: 1\n"
            "---\n"
            "\n"
            "Test memory.\n"
        )

        result = run_cli(
            "verify", "stale-mem",
            "--dir", str(mem_dir),
            "--repo-root", str(tmp_path),
        )

        assert result.returncode == 1
        assert "[FAIL]" in result.stdout

    def test_verify_json_output(self, tmp_path):
        (tmp_path / "code.py").write_text("hello\n")
        mem_dir = tmp_path / ".serena" / "memories"
        mem_dir.mkdir(parents=True)
        (mem_dir / "json-mem.md").write_text(
            "---\n"
            "id: json-mem\n"
            "citations:\n"
            "  - path: code.py\n"
            "---\n"
            "\n"
            "Test.\n"
        )

        result = run_cli(
            "verify", "json-mem",
            "--dir", str(mem_dir),
            "--repo-root", str(tmp_path),
            "--json",
        )

        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["valid"] is True
        assert data["memory_id"] == "json-mem"

    def test_verify_no_citations(self, tmp_path):
        mem_dir = tmp_path / ".serena" / "memories"
        mem_dir.mkdir(parents=True)
        (mem_dir / "no-cite.md").write_text(
            "---\n"
            "id: no-cite\n"
            "---\n"
            "\n"
            "No citations.\n"
        )

        result = run_cli(
            "verify", "no-cite",
            "--dir", str(mem_dir),
            "--repo-root", str(tmp_path),
        )

        assert result.returncode == 0
        assert "No citations" in result.stdout

    def test_verify_no_citations_json(self, tmp_path):
        mem_dir = tmp_path / ".serena" / "memories"
        mem_dir.mkdir(parents=True)
        (mem_dir / "no-cite.md").write_text(
            "---\n"
            "id: no-cite\n"
            "---\n"
            "\n"
            "No citations.\n"
        )

        result = run_cli(
            "verify", "no-cite",
            "--dir", str(mem_dir),
            "--repo-root", str(tmp_path),
            "--json",
        )

        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["memory_id"] == "no-cite"
        assert data["valid"] is True
        assert data["total_citations"] == 0

    def test_verify_memory_not_found(self, tmp_path):
        mem_dir = tmp_path / ".serena" / "memories"
        mem_dir.mkdir(parents=True)

        result = run_cli(
            "verify", "does-not-exist",
            "--dir", str(mem_dir),
            "--repo-root", str(tmp_path),
        )

        assert result.returncode == 2

    def test_verify_path_traversal_blocked(self, tmp_path):
        mem_dir = tmp_path / ".serena" / "memories"
        mem_dir.mkdir(parents=True)

        result = run_cli(
            "verify", "../../../etc/passwd",
            "--dir", str(mem_dir),
            "--repo-root", str(tmp_path),
        )

        # Should fail to find memory (path outside repo root is ignored)
        assert result.returncode == 2

    def test_verify_by_file_path(self, tmp_path):
        (tmp_path / "code.py").write_text("content\n")
        mem_file = tmp_path / "direct-path.md"
        mem_file.write_text(
            "---\n"
            "id: direct\n"
            "citations:\n"
            "  - path: code.py\n"
            "---\n"
            "\n"
            "Content.\n"
        )

        result = run_cli(
            "verify", str(mem_file),
            "--repo-root", str(tmp_path),
        )

        assert result.returncode == 0


class TestVerifyAllCommand:
    """Tests for the verify-all subcommand."""

    def test_verify_all_empty_dir(self, tmp_path):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()

        result = run_cli(
            "verify-all",
            "--dir", str(mem_dir),
            "--repo-root", str(tmp_path),
        )

        assert result.returncode == 0
        assert "No memories with citations" in result.stdout

    def test_verify_all_mixed_results(self, tmp_path):
        (tmp_path / "exists.py").write_text("code\n")
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()

        (mem_dir / "good.md").write_text(
            "---\n"
            "id: good\n"
            "citations:\n"
            "  - path: exists.py\n"
            "---\n"
            "\n"
            "Good.\n"
        )
        (mem_dir / "bad.md").write_text(
            "---\n"
            "id: bad\n"
            "citations:\n"
            "  - path: missing.py\n"
            "---\n"
            "\n"
            "Bad.\n"
        )

        result = run_cli(
            "verify-all",
            "--dir", str(mem_dir),
            "--repo-root", str(tmp_path),
        )

        assert result.returncode == 1
        assert "1" in result.stdout  # stale count

    def test_verify_all_json_output(self, tmp_path):
        (tmp_path / "exists.py").write_text("code\n")
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()

        (mem_dir / "mem.md").write_text(
            "---\n"
            "id: mem-json\n"
            "citations:\n"
            "  - path: exists.py\n"
            "---\n"
            "\n"
            "Content.\n"
        )

        result = run_cli(
            "verify-all",
            "--dir", str(mem_dir),
            "--repo-root", str(tmp_path),
            "--json",
        )

        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["valid"] is True

    def test_verify_all_json_mixed_results(self, tmp_path):
        (tmp_path / "exists.py").write_text("code\n")
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()

        (mem_dir / "good.md").write_text(
            "---\n"
            "id: good\n"
            "citations:\n"
            "  - path: exists.py\n"
            "---\n"
            "\n"
            "Good.\n"
        )
        (mem_dir / "bad.md").write_text(
            "---\n"
            "id: bad\n"
            "citations:\n"
            "  - path: missing.py\n"
            "---\n"
            "\n"
            "Bad.\n"
        )

        result = run_cli(
            "verify-all",
            "--dir", str(mem_dir),
            "--repo-root", str(tmp_path),
            "--json",
        )

        assert result.returncode == 1
        data = json.loads(result.stdout)
        assert isinstance(data, list)
        assert len(data) == 2
        valid_ids = [d["memory_id"] for d in data if d["valid"]]
        stale_ids = [d["memory_id"] for d in data if not d["valid"]]
        assert "good" in valid_ids
        assert "bad" in stale_ids
        # Verify confidence field is present and numeric
        for entry in data:
            assert "confidence" in entry
            assert isinstance(entry["confidence"], (int, float))

    def test_verify_all_missing_dir(self, tmp_path):
        result = run_cli(
            "verify-all",
            "--dir", str(tmp_path / "nonexistent"),
            "--repo-root", str(tmp_path),
        )

        assert result.returncode == 2

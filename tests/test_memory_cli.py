"""Tests for the CLI entry point (__main__.py)."""

from __future__ import annotations

import pytest

from memory_enhancement.__main__ import main


class TestCLIVerify:
    """CLI verify command tests."""

    @pytest.mark.unit
    def test_verify_no_memories(self, tmp_path):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        exit_code = main([
            "--repo-root", str(tmp_path),
            "--memories-dir", str(mem_dir),
            "verify",
        ])
        assert exit_code == 0

    @pytest.mark.unit
    def test_verify_with_valid_citation(self, tmp_path):
        (tmp_path / "exists.py").write_text("content\n")
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        (mem_dir / "m1.md").write_text(
            "# M1 (2026-01-01)\n\n[cite:file](exists.py) - ref\n"
        )
        exit_code = main([
            "--repo-root", str(tmp_path),
            "--memories-dir", str(mem_dir),
            "verify",
        ])
        assert exit_code == 0

    @pytest.mark.unit
    def test_verify_with_broken_citation(self, tmp_path):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        (mem_dir / "m1.md").write_text(
            "# M1 (2026-01-01)\n\n[cite:file](missing.py) - ref\n"
        )
        exit_code = main([
            "--repo-root", str(tmp_path),
            "--memories-dir", str(mem_dir),
            "verify",
        ])
        assert exit_code == 1

    @pytest.mark.unit
    def test_verify_specific_memory(self, tmp_path):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        (mem_dir / "target.md").write_text("# Target (2026-01-01)\n\nContent\n")
        exit_code = main([
            "--repo-root", str(tmp_path),
            "--memories-dir", str(mem_dir),
            "verify", "--memory-id", "target",
        ])
        assert exit_code == 0

    @pytest.mark.unit
    def test_verify_nonexistent_memory_id(self, tmp_path):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        exit_code = main([
            "--repo-root", str(tmp_path),
            "--memories-dir", str(mem_dir),
            "verify", "--memory-id", "nonexistent",
        ])
        assert exit_code == 1


class TestCLIHealth:
    """CLI health command tests."""

    @pytest.mark.unit
    def test_health_empty(self, tmp_path, capsys):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        exit_code = main([
            "--repo-root", str(tmp_path),
            "--memories-dir", str(mem_dir),
            "health",
        ])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Health Score" in captured.out

    @pytest.mark.unit
    def test_health_with_memories(self, tmp_path, capsys):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        (mem_dir / "m1.md").write_text("# M1 (2026-01-01)\n\nContent\n")
        exit_code = main([
            "--repo-root", str(tmp_path),
            "--memories-dir", str(mem_dir),
            "health",
        ])
        # Old memory (>30 days) is flagged as stale, exit code 1 for CI gating
        assert exit_code == 1


class TestCLIGraph:
    """CLI graph command tests."""

    @pytest.mark.unit
    def test_graph_nonexistent_start(self, tmp_path):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        exit_code = main([
            "--repo-root", str(tmp_path),
            "--memories-dir", str(mem_dir),
            "graph", "--start", "nonexistent",
        ])
        assert exit_code == 1

    @pytest.mark.unit
    def test_graph_no_links(self, tmp_path, capsys):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        (mem_dir / "solo.md").write_text("# Solo (2026-01-01)\n\nContent\n")
        exit_code = main([
            "--repo-root", str(tmp_path),
            "--memories-dir", str(mem_dir),
            "graph", "--start", "solo",
        ])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "No linked memories" in captured.out

    @pytest.mark.unit
    def test_graph_with_links(self, tmp_path, capsys):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        (mem_dir / "a.md").write_text(
            "# A (2026-01-01)\n\n[link:depends_on](b) - needs b\n"
        )
        (mem_dir / "b.md").write_text("# B (2026-01-01)\n\nContent\n")
        exit_code = main([
            "--repo-root", str(tmp_path),
            "--memories-dir", str(mem_dir),
            "graph", "--start", "a",
        ])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "b" in captured.out


class TestCLIConfidence:
    """CLI confidence command tests."""

    @pytest.mark.unit
    def test_confidence_empty(self, tmp_path, capsys):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        exit_code = main([
            "--repo-root", str(tmp_path),
            "--memories-dir", str(mem_dir),
            "confidence",
        ])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "No memories found" in captured.out

    @pytest.mark.unit
    def test_confidence_with_memories(self, tmp_path, capsys):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        (mem_dir / "m1.md").write_text("# M1 (2026-01-01)\n\nContent\n")
        exit_code = main([
            "--repo-root", str(tmp_path),
            "--memories-dir", str(mem_dir),
            "confidence",
        ])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "m1" in captured.out


class TestCLISearch:
    """CLI search command tests."""

    @pytest.mark.unit
    def test_search_no_results(self, tmp_path, capsys):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        exit_code = main([
            "--repo-root", str(tmp_path),
            "--memories-dir", str(mem_dir),
            "search", "nonexistent",
        ])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "No results found" in captured.out

    @pytest.mark.unit
    def test_search_with_results(self, tmp_path, capsys):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        (mem_dir / "m1.md").write_text("# M1 (2026-01-01)\n\nSome test content\n")
        exit_code = main([
            "--repo-root", str(tmp_path),
            "--memories-dir", str(mem_dir),
            "search", "test",
        ])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "m1" in captured.out

    @pytest.mark.unit
    def test_search_json_output(self, tmp_path, capsys):
        import json
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        (mem_dir / "m1.md").write_text("# M1 (2026-01-01)\n\nSome test content\n")
        exit_code = main([
            "--repo-root", str(tmp_path),
            "--memories-dir", str(mem_dir),
            "search", "test", "--json",
        ])
        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert isinstance(data, list)
        assert len(data) >= 1
        assert "memory_id" in data[0]
        assert "confidence" in data[0]

    @pytest.mark.unit
    def test_search_top_limit(self, tmp_path, capsys):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        for i in range(5):
            (mem_dir / f"m{i}.md").write_text(f"# M{i} (2026-01-01)\n\nTest content {i}\n")
        exit_code = main([
            "--repo-root", str(tmp_path),
            "--memories-dir", str(mem_dir),
            "search", "test", "--top", "2",
        ])
        assert exit_code == 0
        captured = capsys.readouterr()
        lines = [l for l in captured.out.strip().splitlines() if l.strip()]
        assert len(lines) <= 2

    @pytest.mark.unit
    def test_search_plain_output_format(self, tmp_path, capsys):
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        (mem_dir / "m1.md").write_text("# M1 (2026-01-01)\n\nSome test content\n")
        exit_code = main([
            "--repo-root", str(tmp_path),
            "--memories-dir", str(mem_dir),
            "search", "test",
        ])
        assert exit_code == 0
        captured = capsys.readouterr()
        # Format: {memory_id} ({confidence:.0%}, {citation_status}) - {title}
        assert "%" in captured.out
        assert " - " in captured.out


class TestCLINoCommand:
    """CLI with no command prints help and returns 1."""

    @pytest.mark.unit
    def test_no_command(self):
        exit_code = main([])
        assert exit_code == 1


class TestCLIDefaultMemoriesDir:
    """CLI uses default .serena/memories when --memories-dir not provided."""

    @pytest.mark.unit
    def test_default_memories_dir(self, tmp_path):
        mem_dir = tmp_path / ".serena" / "memories"
        mem_dir.mkdir(parents=True)
        (mem_dir / "m1.md").write_text("# M1 (2026-01-01)\n\nContent\n")
        exit_code = main([
            "--repo-root", str(tmp_path),
            "verify",
        ])
        assert exit_code == 0

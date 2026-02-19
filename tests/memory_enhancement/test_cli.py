"""Tests for memory_enhancement.__main__ (CLI)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from memory_enhancement.__main__ import (
    _find_memory,
    _print_result,
    _result_to_dict,
    cmd_graph,
    cmd_verify,
    cmd_verify_all,
    main,
)
from memory_enhancement.citations import VerificationResult
from memory_enhancement.models import Citation


class TestFindMemory:
    """Tests for _find_memory function."""

    @pytest.mark.unit
    def test_direct_path(
        self, repo_root: Path, memories_dir: Path, sample_memory_file: Path
    ) -> None:
        result = _find_memory(str(sample_memory_file), memories_dir, repo_root)
        assert result == sample_memory_file

    @pytest.mark.unit
    def test_memory_id_with_md_appended(
        self, repo_root: Path, memories_dir: Path, sample_memory_file: Path
    ) -> None:
        result = _find_memory("test-memory", memories_dir, repo_root)
        assert result == memories_dir / "test-memory.md"

    @pytest.mark.unit
    def test_bare_filename(
        self, repo_root: Path, memories_dir: Path, sample_memory_file: Path
    ) -> None:
        result = _find_memory("test-memory.md", memories_dir, repo_root)
        assert result == memories_dir / "test-memory.md"

    @pytest.mark.unit
    def test_nonexistent_memory(
        self, repo_root: Path, memories_dir: Path
    ) -> None:
        with pytest.raises(FileNotFoundError, match="Memory not found"):
            _find_memory("does-not-exist", memories_dir, repo_root)

    @pytest.mark.unit
    def test_nonexistent_absolute_path_raises(
        self, repo_root: Path, memories_dir: Path
    ) -> None:
        with pytest.raises(FileNotFoundError, match="Memory not found"):
            _find_memory("/nonexistent/path/to/memory.md", memories_dir, repo_root)


class TestResultToDict:
    """Tests for _result_to_dict function."""

    @pytest.mark.unit
    def test_valid_result(self) -> None:
        r = VerificationResult(
            memory_id="mem-1",
            valid=True,
            total_citations=2,
            valid_count=2,
            stale_citations=[],
            confidence=1.0,
        )
        d = _result_to_dict(r)
        assert d["memory_id"] == "mem-1"
        assert d["valid"] is True
        assert d["total_citations"] == 2
        assert d["valid_count"] == 2
        assert d["confidence"] == 1.0
        assert d["stale_citations"] == []

    @pytest.mark.unit
    def test_stale_citations_serialized(self) -> None:
        stale = Citation(
            path="src/gone.py",
            line=5,
            snippet="old code",
            mismatch_reason="File not found: src/gone.py",
        )
        r = VerificationResult(
            memory_id="mem-2",
            valid=False,
            total_citations=1,
            valid_count=0,
            stale_citations=[stale],
            confidence=0.0,
        )
        d = _result_to_dict(r)
        assert len(d["stale_citations"]) == 1
        sc = d["stale_citations"][0]
        assert sc["path"] == "src/gone.py"
        assert sc["line"] == 5
        assert sc["snippet"] == "old code"
        assert sc["mismatch_reason"] == "File not found: src/gone.py"

    @pytest.mark.unit
    def test_confidence_rounded(self) -> None:
        r = VerificationResult(
            memory_id="x",
            valid=True,
            total_citations=3,
            valid_count=2,
            stale_citations=[],
            confidence=0.6666666,
        )
        d = _result_to_dict(r)
        assert d["confidence"] == 0.67


class TestPrintResult:
    """Tests for _print_result function."""

    @pytest.mark.unit
    def test_valid_result_output(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        r = VerificationResult(
            memory_id="good",
            valid=True,
            total_citations=2,
            valid_count=2,
            stale_citations=[],
            confidence=1.0,
        )
        _print_result(r)
        captured = capsys.readouterr()
        assert "[PASS]" in captured.out
        assert "VALID" in captured.out
        assert "2/2 valid" in captured.out

    @pytest.mark.unit
    def test_stale_result_output(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        stale = Citation(
            path="src/gone.py",
            line=10,
            mismatch_reason="File not found",
        )
        r = VerificationResult(
            memory_id="bad",
            valid=False,
            total_citations=1,
            valid_count=0,
            stale_citations=[stale],
            confidence=0.0,
        )
        _print_result(r)
        captured = capsys.readouterr()
        assert "[FAIL]" in captured.out
        assert "STALE" in captured.out
        assert "[STALE] src/gone.py:10" in captured.out
        assert "File not found" in captured.out

    @pytest.mark.unit
    def test_stale_citation_no_line(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        stale = Citation(
            path="src/gone.py",
            mismatch_reason="File not found",
        )
        r = VerificationResult(
            memory_id="bad",
            valid=False,
            total_citations=1,
            valid_count=0,
            stale_citations=[stale],
            confidence=0.0,
        )
        _print_result(r)
        captured = capsys.readouterr()
        assert "[STALE] src/gone.py" in captured.out
        assert ":None" not in captured.out


def _make_args(**kwargs: object) -> argparse.Namespace:
    """Build an argparse.Namespace with sensible defaults."""
    defaults = {
        "dir": ".",
        "repo_root": ".",
        "json": False,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


class TestCmdVerify:
    """Tests for cmd_verify function."""

    @pytest.mark.unit
    def test_valid_memory(
        self,
        repo_root: Path,
        memories_dir: Path,
        sample_memory_file: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        args = _make_args(
            memory_id=str(sample_memory_file),
            dir=str(memories_dir),
            repo_root=str(repo_root),
        )
        exit_code = cmd_verify(args)
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "[PASS]" in captured.out

    @pytest.mark.unit
    def test_no_citations(
        self,
        repo_root: Path,
        memories_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        bare = memories_dir / "bare.md"
        bare.write_text(
            "---\nid: bare\nsubject: Bare\n---\nBody.\n",
            encoding="utf-8",
        )
        args = _make_args(
            memory_id=str(bare),
            dir=str(memories_dir),
            repo_root=str(repo_root),
        )
        exit_code = cmd_verify(args)
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "No citations to verify" in captured.out

    @pytest.mark.unit
    def test_no_citations_json(
        self,
        repo_root: Path,
        memories_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        bare = memories_dir / "bare.md"
        bare.write_text(
            "---\nid: bare\nsubject: Bare\n---\nBody.\n",
            encoding="utf-8",
        )
        args = _make_args(
            memory_id=str(bare),
            dir=str(memories_dir),
            repo_root=str(repo_root),
            json=True,
        )
        exit_code = cmd_verify(args)
        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["valid"] is True
        assert data["total_citations"] == 0

    @pytest.mark.unit
    def test_json_output(
        self,
        repo_root: Path,
        memories_dir: Path,
        sample_memory_file: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        args = _make_args(
            memory_id=str(sample_memory_file),
            dir=str(memories_dir),
            repo_root=str(repo_root),
            json=True,
        )
        exit_code = cmd_verify(args)
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "memory_id" in data
        assert "valid" in data
        assert exit_code == 0

    @pytest.mark.unit
    def test_nonexistent_memory(
        self,
        repo_root: Path,
        memories_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        args = _make_args(
            memory_id="does-not-exist",
            dir=str(memories_dir),
            repo_root=str(repo_root),
        )
        exit_code = cmd_verify(args)
        assert exit_code == 2
        captured = capsys.readouterr()
        assert "Error" in captured.err

    @pytest.mark.unit
    def test_malformed_yaml_returns_2(
        self,
        repo_root: Path,
        memories_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        bad = memories_dir / "malformed.md"
        bad.write_text(
            "---\n: invalid: yaml: [[[\n---\nBody.\n",
            encoding="utf-8",
        )
        args = _make_args(
            memory_id=str(bad),
            dir=str(memories_dir),
            repo_root=str(repo_root),
        )
        exit_code = cmd_verify(args)
        assert exit_code == 2
        captured = capsys.readouterr()
        assert "Error" in captured.err

    @pytest.mark.unit
    def test_stale_citation_returns_1(
        self,
        repo_root: Path,
        memories_dir: Path,
    ) -> None:
        stale = memories_dir / "stale.md"
        stale.write_text(
            "---\n"
            "id: stale\n"
            "subject: Stale\n"
            "citations:\n"
            "  - path: src/nonexistent.py\n"
            "---\n"
            "Body.\n",
            encoding="utf-8",
        )
        args = _make_args(
            memory_id=str(stale),
            dir=str(memories_dir),
            repo_root=str(repo_root),
        )
        exit_code = cmd_verify(args)
        assert exit_code == 1

    @pytest.mark.unit
    def test_path_traversal_protection(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test that cmd_verify rejects directories outside repo_root (CWE-22)."""
        repo_root = tmp_path / "repo"
        outside_dir = tmp_path / "outside"
        repo_root.mkdir()
        outside_dir.mkdir()

        args = _make_args(
            memory_id="test",
            dir=str(outside_dir),
            repo_root=str(repo_root),
        )
        exit_code = cmd_verify(args)
        assert exit_code == 2
        captured = capsys.readouterr()
        assert "outside the repository" in captured.err


class TestCmdVerifyAll:
    """Tests for cmd_verify_all function."""

    @pytest.mark.unit
    def test_with_results(
        self,
        repo_root: Path,
        memories_dir: Path,
        sample_memory_file: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        args = _make_args(
            dir=str(memories_dir),
            repo_root=str(repo_root),
        )
        exit_code = cmd_verify_all(args)
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Summary" in captured.out

    @pytest.mark.unit
    def test_json_output(
        self,
        repo_root: Path,
        memories_dir: Path,
        sample_memory_file: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        args = _make_args(
            dir=str(memories_dir),
            repo_root=str(repo_root),
            json=True,
        )
        cmd_verify_all(args)
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert isinstance(data, list)

    @pytest.mark.unit
    def test_missing_directory(
        self,
        repo_root: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        args = _make_args(
            dir=str(repo_root / "nonexistent"),
            repo_root=str(repo_root),
        )
        exit_code = cmd_verify_all(args)
        assert exit_code == 2
        captured = capsys.readouterr()
        assert "not found" in captured.err

    @pytest.mark.unit
    def test_no_memories_with_citations(
        self,
        repo_root: Path,
        memories_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        (memories_dir / "bare.md").write_text(
            "---\nid: bare\nsubject: Bare\n---\nBody.\n",
            encoding="utf-8",
        )
        args = _make_args(
            dir=str(memories_dir),
            repo_root=str(repo_root),
        )
        exit_code = cmd_verify_all(args)
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "No memories with citations found" in captured.out

    @pytest.mark.unit
    def test_stale_returns_1(
        self,
        repo_root: Path,
        memories_dir: Path,
    ) -> None:
        (memories_dir / "stale.md").write_text(
            "---\n"
            "id: stale\n"
            "subject: Stale\n"
            "citations:\n"
            "  - path: src/nonexistent.py\n"
            "---\n"
            "Body.\n",
            encoding="utf-8",
        )
        args = _make_args(
            dir=str(memories_dir),
            repo_root=str(repo_root),
        )
        exit_code = cmd_verify_all(args)
        assert exit_code == 1

    @pytest.mark.unit
    def test_path_traversal_protection(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test that cmd_verify_all rejects directories outside repo_root (CWE-22)."""
        repo_root = tmp_path / "repo"
        outside_dir = tmp_path / "outside"
        repo_root.mkdir()
        outside_dir.mkdir()

        args = _make_args(
            dir=str(outside_dir),
            repo_root=str(repo_root),
        )
        exit_code = cmd_verify_all(args)
        assert exit_code == 2
        captured = capsys.readouterr()
        assert "outside the repository" in captured.err


class TestMain:
    """Tests for main() CLI entry point."""

    @pytest.mark.unit
    def test_verify_subcommand(
        self,
        repo_root: Path,
        memories_dir: Path,
        sample_memory_file: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "sys.argv",
            [
                "memory_enhancement",
                "verify",
                str(sample_memory_file),
                "--repo-root",
                str(repo_root),
                "--dir",
                str(memories_dir),
            ],
        )
        exit_code = main()
        assert exit_code == 0

    @pytest.mark.unit
    def test_verify_all_subcommand(
        self,
        repo_root: Path,
        memories_dir: Path,
        sample_memory_file: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "sys.argv",
            [
                "memory_enhancement",
                "verify-all",
                "--repo-root",
                str(repo_root),
                "--dir",
                str(memories_dir),
            ],
        )
        exit_code = main()
        assert exit_code == 0

    @pytest.mark.unit
    def test_missing_subcommand(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("sys.argv", ["memory_enhancement"])
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 2

    @pytest.mark.unit
    def test_graph_subcommand(
        self,
        repo_root: Path,
        graph_memories_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "sys.argv",
            [
                "memory_enhancement",
                "graph",
                "memory-a",
                "--dir",
                str(graph_memories_dir),
                "--repo-root",
                str(repo_root),
            ],
        )
        exit_code = main()
        assert exit_code == 0


def _make_graph_args(**kwargs: object) -> argparse.Namespace:
    """Build argparse.Namespace for graph commands with sensible defaults."""
    defaults: dict[str, object] = {
        "dir": ".",
        "repo_root": ".",
        "json": False,
        "memory_id": None,
        "mode": "bfs",
        "max_depth": None,
        "cycles": False,
        "score": False,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


class TestCmdGraphTraverse:
    """Tests for cmd_graph traversal mode."""

    @pytest.mark.unit
    def test_bfs_traverse(
        self,
        repo_root: Path,
        graph_memories_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        args = _make_graph_args(
            memory_id="memory-a",
            dir=str(graph_memories_dir),
            repo_root=str(repo_root),
        )
        exit_code = cmd_graph(args)
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Graph traversal" in captured.out
        assert "memory-a" in captured.out
        assert "Nodes visited:" in captured.out

    @pytest.mark.unit
    def test_dfs_traverse(
        self,
        repo_root: Path,
        graph_memories_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        args = _make_graph_args(
            memory_id="memory-a",
            mode="dfs",
            dir=str(graph_memories_dir),
            repo_root=str(repo_root),
        )
        exit_code = cmd_graph(args)
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "DFS" in captured.out

    @pytest.mark.unit
    def test_traverse_json(
        self,
        repo_root: Path,
        graph_memories_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        args = _make_graph_args(
            memory_id="memory-a",
            dir=str(graph_memories_dir),
            repo_root=str(repo_root),
            json=True,
        )
        exit_code = cmd_graph(args)
        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["start"] == "memory-a"
        assert data["mode"] == "bfs"
        assert isinstance(data["nodes"], list)

    @pytest.mark.unit
    def test_traverse_with_max_depth(
        self,
        repo_root: Path,
        graph_memories_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        args = _make_graph_args(
            memory_id="memory-a",
            max_depth=1,
            dir=str(graph_memories_dir),
            repo_root=str(repo_root),
        )
        exit_code = cmd_graph(args)
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "max_depth=1" in captured.out

    @pytest.mark.unit
    def test_traverse_missing_memory_id(
        self,
        repo_root: Path,
        graph_memories_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        args = _make_graph_args(
            dir=str(graph_memories_dir),
            repo_root=str(repo_root),
        )
        exit_code = cmd_graph(args)
        assert exit_code == 2
        captured = capsys.readouterr()
        assert "memory_id is required" in captured.err

    @pytest.mark.unit
    def test_traverse_unknown_memory(
        self,
        repo_root: Path,
        graph_memories_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        args = _make_graph_args(
            memory_id="nonexistent-memory",
            dir=str(graph_memories_dir),
            repo_root=str(repo_root),
        )
        exit_code = cmd_graph(args)
        assert exit_code == 2
        captured = capsys.readouterr()
        assert "Error" in captured.err


class TestCmdGraphCycles:
    """Tests for cmd_graph --cycles mode."""

    @pytest.mark.unit
    def test_no_cycles(
        self,
        repo_root: Path,
        graph_memories_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        args = _make_graph_args(
            cycles=True,
            dir=str(graph_memories_dir),
            repo_root=str(repo_root),
        )
        exit_code = cmd_graph(args)
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "No cycles found" in captured.out

    @pytest.mark.unit
    def test_cycles_found(
        self,
        repo_root: Path,
        cyclic_memories_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        args = _make_graph_args(
            cycles=True,
            dir=str(cyclic_memories_dir),
            repo_root=str(repo_root),
        )
        exit_code = cmd_graph(args)
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "Cycle" in captured.out

    @pytest.mark.unit
    def test_cycles_json(
        self,
        repo_root: Path,
        graph_memories_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        args = _make_graph_args(
            cycles=True,
            dir=str(graph_memories_dir),
            repo_root=str(repo_root),
            json=True,
        )
        exit_code = cmd_graph(args)
        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "cycles" in data
        assert "count" in data


class TestCmdGraphScore:
    """Tests for cmd_graph --score mode."""

    @pytest.mark.unit
    def test_score_relationships(
        self,
        repo_root: Path,
        graph_memories_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        args = _make_graph_args(
            memory_id="memory-a",
            score=True,
            dir=str(graph_memories_dir),
            repo_root=str(repo_root),
        )
        exit_code = cmd_graph(args)
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Relationship scores" in captured.out
        assert "Total relationships:" in captured.out

    @pytest.mark.unit
    def test_score_json(
        self,
        repo_root: Path,
        graph_memories_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        args = _make_graph_args(
            memory_id="memory-a",
            score=True,
            dir=str(graph_memories_dir),
            repo_root=str(repo_root),
            json=True,
        )
        exit_code = cmd_graph(args)
        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["memory_id"] == "memory-a"
        assert "relationships" in data

    @pytest.mark.unit
    def test_score_missing_memory_id(
        self,
        repo_root: Path,
        graph_memories_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        args = _make_graph_args(
            score=True,
            dir=str(graph_memories_dir),
            repo_root=str(repo_root),
        )
        exit_code = cmd_graph(args)
        assert exit_code == 2
        captured = capsys.readouterr()
        assert "memory_id is required" in captured.err

    @pytest.mark.unit
    def test_score_unknown_memory(
        self,
        repo_root: Path,
        graph_memories_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        args = _make_graph_args(
            memory_id="nonexistent-memory",
            score=True,
            dir=str(graph_memories_dir),
            repo_root=str(repo_root),
        )
        exit_code = cmd_graph(args)
        assert exit_code == 2


class TestCmdGraphErrors:
    """Tests for cmd_graph error handling."""

    @pytest.mark.unit
    def test_missing_directory(
        self,
        repo_root: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        args = _make_graph_args(
            dir="nonexistent",
            repo_root=str(repo_root),
        )
        exit_code = cmd_graph(args)
        assert exit_code == 2
        captured = capsys.readouterr()
        assert "not found" in captured.err

    @pytest.mark.security
    def test_path_traversal_blocked(
        self,
        repo_root: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        args = _make_graph_args(
            dir="../../../../etc",
            repo_root=str(repo_root),
        )
        exit_code = cmd_graph(args)
        assert exit_code == 2
        captured = capsys.readouterr()
        assert "outside the repository" in captured.err

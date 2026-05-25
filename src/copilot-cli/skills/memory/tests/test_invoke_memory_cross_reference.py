"""Tests for invoke_memory_cross_reference.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent / "scripts")
)

from invoke_memory_cross_reference import main


@pytest.fixture()
def memories_dir(tmp_path: Path) -> Path:
    """Create a memories directory with files for all three sub-scripts."""
    mem_dir = tmp_path / "memories"
    mem_dir.mkdir()
    # Memory files for backtick and graph density tests
    (mem_dir / "security-001.md").write_text("# Security\nSee `git-hooks`.\n")
    (mem_dir / "security-002.md").write_text("# Security 2\nContent.\n")
    (mem_dir / "git-hooks.md").write_text("# Git Hooks\nContent.\n")
    # Index file for index table links test
    (mem_dir / "testing-index.md").write_text(
        "| Topic | Memory |\n|---|---|\n| hooks | git-hooks |\n"
    )
    return mem_dir


class TestMainOrchestration:
    def test_always_exits_zero(self, memories_dir: Path) -> None:
        exit_code = main([
            "--memories-path", str(memories_dir),
            "--skip-path-validation",
        ])
        assert exit_code == 0

    def test_json_output_has_all_fields(
        self, memories_dir: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        exit_code = main([
            "--memories-path", str(memories_dir),
            "--output-json",
            "--skip-path-validation",
        ])
        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "IndexLinksAdded" in data
        assert "BacktickLinksAdded" in data
        assert "RelatedSectionsAdded" in data
        assert "FilesModified" in data
        assert "Errors" in data
        assert "Success" in data

    def test_success_true_when_no_errors(
        self, memories_dir: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        main([
            "--memories-path", str(memories_dir),
            "--output-json",
            "--skip-path-validation",
        ])
        data = json.loads(capsys.readouterr().out)
        assert data["Success"] is True
        assert data["Errors"] == []

    def test_runs_all_three_scripts(
        self, memories_dir: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        main([
            "--memories-path", str(memories_dir),
            "--output-json",
            "--skip-path-validation",
        ])
        data = json.loads(capsys.readouterr().out)
        # Index table links: testing-index.md has a convertible reference
        assert data["IndexLinksAdded"] >= 1
        # Backtick refs: security-001.md references `git-hooks`
        assert data["BacktickLinksAdded"] >= 1
        # Graph density: security-001 and security-002 are in the same domain
        assert data["RelatedSectionsAdded"] >= 1

    def test_files_modified_is_aggregate(
        self, memories_dir: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        main([
            "--memories-path", str(memories_dir),
            "--output-json",
            "--skip-path-validation",
        ])
        data = json.loads(capsys.readouterr().out)
        assert data["FilesModified"] >= 1

    def test_human_output_format(
        self, memories_dir: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        main([
            "--memories-path", str(memories_dir),
            "--skip-path-validation",
        ])
        out = capsys.readouterr().out
        assert "Step 1/3" in out
        assert "Step 2/3" in out
        assert "Step 3/3" in out
        assert "=== Summary ===" in out

    def test_specific_files_filter(
        self, memories_dir: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = str(memories_dir / "security-001.md")
        exit_code = main([
            "--memories-path", str(memories_dir),
            "--files", target,
            "--output-json",
            "--skip-path-validation",
        ])
        assert exit_code == 0

    def test_empty_directory(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        exit_code = main([
            "--memories-path", str(empty_dir),
            "--output-json",
            "--skip-path-validation",
        ])
        assert exit_code == 0
        data = json.loads(capsys.readouterr().out)
        assert data["Success"] is True
        assert data["FilesModified"] == 0

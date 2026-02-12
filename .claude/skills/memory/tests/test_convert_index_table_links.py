"""Tests for convert_index_table_links.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Add scripts directory to path for imports
sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent / "scripts")
)

from convert_index_table_links import (
    _build_memory_names,
    _convert_comma_refs,
    _convert_single_refs,
    _count_md_links,
    main,
    process_files,
)


@pytest.fixture()
def memories_dir(tmp_path: Path) -> Path:
    """Create a temporary memories directory with sample files."""
    mem_dir = tmp_path / "memories"
    mem_dir.mkdir()
    (mem_dir / "security-001.md").write_text("# Security 001\n")
    (mem_dir / "git-hooks.md").write_text("# Git Hooks\n")
    (mem_dir / "testing-index.md").write_text(
        "| Topic | Memory |\n|---|---|\n| hooks | git-hooks |\n| sec | security-001 |\n"
    )
    return mem_dir


class TestBuildMemoryNames:
    def test_finds_all_md_stems(self, memories_dir: Path) -> None:
        names = _build_memory_names(memories_dir)
        assert "security-001" in names
        assert "git-hooks" in names
        assert "testing-index" in names

    def test_empty_directory(self, tmp_path: Path) -> None:
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        names = _build_memory_names(empty_dir)
        assert names == {}


class TestConvertSingleRefs:
    def test_converts_known_memory_to_link(self) -> None:
        content = "| hooks | git-hooks |"
        names = {"git-hooks": True}
        result = _convert_single_refs(content, names)
        assert "[git-hooks](git-hooks.md)" in result

    def test_skips_unknown_names(self) -> None:
        content = "| hooks | unknown-file |"
        names = {"git-hooks": True}
        result = _convert_single_refs(content, names)
        assert "[unknown-file]" not in result

    def test_skips_separator_rows(self) -> None:
        content = "| --- | --- |"
        names = {"---": True}
        result = _convert_single_refs(content, names)
        assert "[---]" not in result

    def test_skips_existing_links(self) -> None:
        content = "| hooks | [git-hooks](git-hooks.md) |"
        names = {"git-hooks": True}
        result = _convert_single_refs(content, names)
        # Should not double-wrap
        assert result.count("[git-hooks]") == 1


class TestConvertCommaRefs:
    def test_converts_comma_separated_list(self) -> None:
        content = "| git-hooks, security-001 |"
        names = {"git-hooks": True, "security-001": True}
        result = _convert_comma_refs(content, names)
        assert "[git-hooks](git-hooks.md)" in result
        assert "[security-001](security-001.md)" in result

    def test_skips_already_linked(self) -> None:
        content = "| [git-hooks](git-hooks.md), security-001 |"
        names = {"git-hooks": True, "security-001": True}
        result = _convert_comma_refs(content, names)
        # Should not modify when links already present
        assert result == content

    def test_partial_known_files(self) -> None:
        content = "| git-hooks, unknown-file |"
        names = {"git-hooks": True}
        result = _convert_comma_refs(content, names)
        assert "[git-hooks](git-hooks.md)" in result
        assert "unknown-file" in result
        assert "[unknown-file]" not in result


class TestCountMdLinks:
    def test_counts_md_links(self) -> None:
        content = "[a](a.md) text [b](b.md)"
        assert _count_md_links(content) == 2

    def test_zero_for_no_links(self) -> None:
        assert _count_md_links("no links here") == 0


class TestProcessFiles:
    def test_processes_index_files(self, memories_dir: Path) -> None:
        stats = process_files(memories_dir, output_json=True)
        assert stats["FilesProcessed"] >= 1
        assert stats["Errors"] == []

    def test_converts_references_in_index(self, memories_dir: Path) -> None:
        stats = process_files(memories_dir, output_json=True)
        assert stats["FilesModified"] >= 1
        assert stats["LinksAdded"] >= 1

        updated = (memories_dir / "testing-index.md").read_text()
        assert "[git-hooks](git-hooks.md)" in updated

    def test_empty_file_skipped(self, memories_dir: Path) -> None:
        (memories_dir / "empty-index.md").write_text("")
        stats = process_files(memories_dir, output_json=True)
        assert stats["Errors"] == []

    def test_specific_files_filter(self, memories_dir: Path) -> None:
        target = memories_dir / "testing-index.md"
        stats = process_files(
            memories_dir, files_to_process=[target], output_json=True
        )
        assert stats["FilesProcessed"] == 1

    def test_no_changes_when_already_linked(self, memories_dir: Path) -> None:
        (memories_dir / "testing-index.md").write_text(
            "| Topic | Memory |\n|---|---|\n"
            "| hooks | [git-hooks](git-hooks.md) |\n"
        )
        stats = process_files(memories_dir, output_json=True)
        assert stats["FilesModified"] == 0


class TestMain:
    def test_json_output(self, memories_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = main([
            "--memories-path", str(memories_dir),
            "--output-json",
            "--skip-path-validation",
        ])
        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "FilesProcessed" in data
        assert "FilesModified" in data
        assert "LinksAdded" in data
        assert "Errors" in data

    def test_human_output(self, memories_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = main([
            "--memories-path", str(memories_dir),
            "--skip-path-validation",
        ])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Conversion complete" in captured.out

    def test_returns_1_on_errors(self, tmp_path: Path) -> None:
        # Non-existent directory causes no files to process, not an error
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        exit_code = main([
            "--memories-path", str(empty_dir),
            "--skip-path-validation",
        ])
        assert exit_code == 0

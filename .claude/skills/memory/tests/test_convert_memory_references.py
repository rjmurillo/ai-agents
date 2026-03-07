"""Tests for convert_memory_references.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent / "scripts")
)

from convert_memory_references import (
    _build_memory_names,
    _convert_backtick_refs,
    _count_md_links,
    main,
    process_files,
)


@pytest.fixture()
def memories_dir(tmp_path: Path) -> Path:
    """Create a temporary memories directory with sample files."""
    mem_dir = tmp_path / "memories"
    mem_dir.mkdir()
    (mem_dir / "security-001.md").write_text("# Security\nSee `git-hooks` for details.\n")
    (mem_dir / "git-hooks.md").write_text("# Git Hooks\nRelated to `security-001`.\n")
    (mem_dir / "no-refs.md").write_text("# No References\nPlain text.\n")
    return mem_dir


class TestBuildMemoryNames:
    def test_finds_all_md_stems(self, memories_dir: Path) -> None:
        names = _build_memory_names(memories_dir)
        assert "security-001" in names
        assert "git-hooks" in names
        assert "no-refs" in names

    def test_empty_directory(self, tmp_path: Path) -> None:
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        assert _build_memory_names(empty_dir) == {}


class TestConvertBacktickRefs:
    def test_converts_known_memory(self) -> None:
        content = "See `git-hooks` for details."
        names = {"git-hooks": True}
        result = _convert_backtick_refs(content, names)
        assert result == "See [git-hooks](git-hooks.md) for details."

    def test_preserves_unknown_backtick(self) -> None:
        content = "Use `unknown-thing` here."
        names = {"git-hooks": True}
        result = _convert_backtick_refs(content, names)
        assert result == "Use `unknown-thing` here."

    def test_skips_already_linked(self) -> None:
        content = "See [`git-hooks`](git-hooks.md) for details."
        names = {"git-hooks": True}
        result = _convert_backtick_refs(content, names)
        # Should not double-convert (backtick preceded by [ is excluded)
        assert "`git-hooks`" in result

    def test_skips_code_paths(self) -> None:
        content = "Use `some/path/file` here."
        names: dict[str, bool] = {}
        result = _convert_backtick_refs(content, names)
        # Pattern only matches hyphenated lowercase names, not paths
        assert result == content

    def test_multiple_refs_in_same_line(self) -> None:
        content = "Both `git-hooks` and `security-001` are important."
        names = {"git-hooks": True, "security-001": True}
        result = _convert_backtick_refs(content, names)
        assert "[git-hooks](git-hooks.md)" in result
        assert "[security-001](security-001.md)" in result

    def test_single_word_memory_name(self) -> None:
        content = "See `resilience` for patterns."
        names = {"resilience": True}
        result = _convert_backtick_refs(content, names)
        assert result == "See [resilience](resilience.md) for patterns."


class TestCountMdLinks:
    def test_counts_links(self) -> None:
        assert _count_md_links("[a](a.md) and [b](b.md)") == 2

    def test_zero_for_no_links(self) -> None:
        assert _count_md_links("no links") == 0


class TestProcessFiles:
    def test_converts_backtick_refs(self, memories_dir: Path) -> None:
        stats = process_files(memories_dir, output_json=True)
        assert stats["FilesModified"] >= 1
        assert stats["LinksAdded"] >= 1
        assert stats["Errors"] == []

        updated = (memories_dir / "security-001.md").read_text()
        assert "[git-hooks](git-hooks.md)" in updated

    def test_empty_file_skipped(self, memories_dir: Path) -> None:
        (memories_dir / "empty.md").write_text("")
        stats = process_files(memories_dir, output_json=True)
        assert stats["Errors"] == []

    def test_specific_files_filter(self, memories_dir: Path) -> None:
        target = memories_dir / "security-001.md"
        stats = process_files(
            memories_dir, files_to_process=[target], output_json=True
        )
        assert stats["FilesProcessed"] == 1

    def test_no_changes_for_plain_text(self, memories_dir: Path) -> None:
        # "no-refs.md" has no backtick references to known memory names
        target = memories_dir / "no-refs.md"
        stats = process_files(
            memories_dir, files_to_process=[target], output_json=True
        )
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
        assert "LinksAdded" in data

    def test_human_output(self, memories_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = main([
            "--memories-path", str(memories_dir),
            "--skip-path-validation",
        ])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Conversion complete" in captured.out

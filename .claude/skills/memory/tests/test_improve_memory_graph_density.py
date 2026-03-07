"""Tests for improve_memory_graph_density.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent / "scripts")
)

from improve_memory_graph_density import (
    DOMAIN_PATTERNS,
    _find_related_files,
    main,
    process_files,
)


@pytest.fixture()
def memories_dir(tmp_path: Path) -> Path:
    """Create a temporary memories directory with domain-grouped files."""
    mem_dir = tmp_path / "memories"
    mem_dir.mkdir()
    (mem_dir / "security-001.md").write_text("# Security 001\nContent.\n")
    (mem_dir / "security-002.md").write_text("# Security 002\nContent.\n")
    (mem_dir / "security-003.md").write_text("# Security 003\nContent.\n")
    (mem_dir / "git-hooks.md").write_text("# Git Hooks\nContent.\n")
    (mem_dir / "git-branch.md").write_text("# Git Branch\nContent.\n")
    (mem_dir / "gits-index.md").write_text("# Git Index\n| Name | File |\n")
    (mem_dir / "testing-index.md").write_text("# Testing Index\n| Name | File |\n")
    (mem_dir / "standalone.md").write_text("# Standalone\nNo domain prefix.\n")
    return mem_dir


class TestDomainPatterns:
    def test_more_specific_before_general(self) -> None:
        """Verify git-hooks- comes before git- in the ordered dict."""
        keys = list(DOMAIN_PATTERNS.keys())
        git_hooks_idx = keys.index("git-hooks-")
        git_idx = keys.index("git-")
        assert git_hooks_idx < git_idx

    def test_pr_comment_before_pr(self) -> None:
        keys = list(DOMAIN_PATTERNS.keys())
        pr_comment_idx = keys.index("pr-comment-")
        pr_idx = keys.index("pr-")
        assert pr_comment_idx < pr_idx

    def test_session_init_before_session(self) -> None:
        keys = list(DOMAIN_PATTERNS.keys())
        session_init_idx = keys.index("session-init-")
        session_idx = keys.index("session-")
        assert session_init_idx < session_idx


class TestFindRelatedFiles:
    def test_finds_same_domain_files(self, memories_dir: Path) -> None:
        all_files = sorted(memories_dir.glob("*.md"))
        names = {f.stem: str(f) for f in all_files}
        related = _find_related_files("security-001", all_files, names)
        assert "security-002" in related
        assert "security-003" in related

    def test_finds_index_file(self, memories_dir: Path) -> None:
        all_files = sorted(memories_dir.glob("*.md"))
        names = {f.stem: str(f) for f in all_files}
        related = _find_related_files("git-hooks", all_files, names)
        assert "gits-index" in related

    def test_limits_to_five(self, tmp_path: Path) -> None:
        mem_dir = tmp_path / "mem"
        mem_dir.mkdir()
        for i in range(10):
            (mem_dir / f"security-{i:03d}.md").write_text(f"# S{i}\n")
        all_files = sorted(mem_dir.glob("*.md"))
        names = {f.stem: str(f) for f in all_files}
        related = _find_related_files("security-000", all_files, names)
        assert len(related) <= 5

    def test_no_self_reference(self, memories_dir: Path) -> None:
        all_files = sorted(memories_dir.glob("*.md"))
        names = {f.stem: str(f) for f in all_files}
        related = _find_related_files("security-001", all_files, names)
        assert "security-001" not in related

    def test_standalone_file_no_domain(self, memories_dir: Path) -> None:
        all_files = sorted(memories_dir.glob("*.md"))
        names = {f.stem: str(f) for f in all_files}
        related = _find_related_files("standalone", all_files, names)
        # standalone doesn't match any domain prefix
        assert len(related) == 0


class TestProcessFiles:
    def test_adds_related_sections(self, memories_dir: Path) -> None:
        stats = process_files(memories_dir, output_json=True)
        assert stats["FilesModified"] >= 1
        assert stats["RelationshipsAdded"] >= 1
        assert stats["Errors"] == []

        updated = (memories_dir / "security-001.md").read_text()
        assert "## Related" in updated
        assert "[security-002](security-002.md)" in updated

    def test_skips_index_files(self, memories_dir: Path) -> None:
        process_files(memories_dir, output_json=True)
        testing_idx = (memories_dir / "testing-index.md").read_text()
        assert "## Related" not in testing_idx

    def test_skips_files_with_existing_related(self, memories_dir: Path) -> None:
        (memories_dir / "security-001.md").write_text(
            "# Security 001\n\n## Related\n\n- existing\n"
        )
        stats = process_files(
            memories_dir,
            files_to_process=[memories_dir / "security-001.md"],
            output_json=True,
        )
        assert stats["FilesModified"] == 0

    def test_dry_run_no_writes(self, memories_dir: Path) -> None:
        original = (memories_dir / "security-001.md").read_text()
        stats = process_files(memories_dir, dry_run=True, output_json=True)
        assert stats["FilesModified"] >= 1
        after = (memories_dir / "security-001.md").read_text()
        assert after == original

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
        assert "RelationshipsAdded" in data

    def test_human_output(self, memories_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = main([
            "--memories-path", str(memories_dir),
            "--skip-path-validation",
        ])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "=== Summary ===" in captured.out
        assert "Files updated:" in captured.out

    def test_dry_run_message(self, memories_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = main([
            "--memories-path", str(memories_dir),
            "--dry-run",
            "--skip-path-validation",
        ])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "dry run" in captured.out.lower()

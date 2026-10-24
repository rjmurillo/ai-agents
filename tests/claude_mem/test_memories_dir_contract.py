"""Contract for .claude-mem/memories/ after the import procedure was retired.

Issue #5583, owner decision D21 (2026-10-24): the 9.2 MiB full-database export
and the manual import procedure are gone. These tests keep them gone and keep
the README Directory Structure block honest.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MEMORIES_REL = ".claude-mem/memories"
_MEMORIES_DIR = _REPO_ROOT / _MEMORIES_REL
_FILE_NAME = re.compile(r"[A-Za-z0-9._-]+\.(?:json|md)")
_TEXT_BLOCK = re.compile(r"```text\n(.*?)```", re.DOTALL)

_needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def block_file_names(readme_text: str) -> set[str]:
    """Return the file names listed in the first fenced text block."""
    match = _TEXT_BLOCK.search(readme_text)
    if match is None:
        return set()
    return {m.group(0) for m in _FILE_NAME.finditer(match.group(1))}


class TestBlockFileNames:
    def test_lists_names_in_the_text_block(self) -> None:
        text = "intro\n\n```text\ndir/\n├── AGENTS.md  # guide\n└── README.md\n```\n"
        assert block_file_names(text) == {"AGENTS.md", "README.md"}

    def test_ignores_names_outside_the_text_block(self) -> None:
        text = "See OTHER.md\n\n```text\n└── README.md\n```\n\nand LATER.json\n"
        assert block_file_names(text) == {"README.md"}

    def test_returns_empty_set_without_a_text_block(self) -> None:
        assert block_file_names("# Title\n\nNo fenced block here: README.md\n") == set()

    def test_reads_only_the_first_text_block(self) -> None:
        text = "```text\nFIRST.md\n```\n\n```text\nSECOND.md\n```\n"
        assert block_file_names(text) == {"FIRST.md"}


class TestReadmeDirectoryBlock:
    def test_every_listed_file_exists(self) -> None:
        names = block_file_names((_MEMORIES_DIR / "README.md").read_text(encoding="utf-8"))
        missing = sorted(n for n in names if not (_MEMORIES_DIR / n).is_file())
        assert missing == []

    def test_block_detects_a_listed_file_that_does_not_exist(self, tmp_path: Path) -> None:
        names = block_file_names("```text\n├── GHOST.json\n```\n")
        missing = sorted(n for n in names if not (tmp_path / n).is_file())
        assert missing == ["GHOST.json"]

    @_needs_git
    def test_every_tracked_file_is_listed(self) -> None:
        result = _git("ls-files", "--", _MEMORIES_REL)
        assert result.returncode == 0, result.stderr
        tracked = {Path(line).name for line in result.stdout.splitlines()}
        listed = block_file_names((_MEMORIES_DIR / "README.md").read_text(encoding="utf-8"))
        assert tracked - listed == set()


class TestRetiredArtifacts:
    @_needs_git
    def test_no_full_database_export_is_tracked(self) -> None:
        result = _git("ls-files", "--", f"{_MEMORIES_REL}/direct-backup-*.json")
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == ""

    def test_importer_script_is_removed(self) -> None:
        script = _REPO_ROOT / ".claude-mem" / "scripts" / "import_claude_mem_memories.py"
        assert not script.exists()

    @pytest.mark.parametrize(
        "relative_path",
        [
            f"{_MEMORIES_REL}/README.md",
            f"{_MEMORIES_REL}/AGENTS.md",
            ".agents/governance/MEMORY-MANAGEMENT.md",
        ],
    )
    def test_live_docs_do_not_name_the_removed_importer(self, relative_path: str) -> None:
        text = (_REPO_ROOT / relative_path).read_text(encoding="utf-8")
        assert "import_claude_mem_memories" not in text


@_needs_git
class TestGitignoreRules:
    def test_future_full_database_export_is_ignored(self) -> None:
        name = f"{_MEMORIES_REL}/direct-backup-2099-01-01-0000-ai-agents.json"
        result = _git("check-ignore", "-v", name)
        assert result.returncode == 0, result.stderr
        assert ".claude-mem/.gitignore" in result.stdout

    def test_topic_scoped_export_stays_committable(self) -> None:
        name = f"{_MEMORIES_REL}/2099-01-01-session-999-topic.json"
        result = _git("check-ignore", name)
        assert result.returncode == 1
        assert result.stdout.strip() == ""

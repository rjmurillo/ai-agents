"""Tests for init_project module.

Verifies the project scaffolding functionality for initializing
ai-agents directory structure in new projects.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from scripts.init_project import (
    _AGENTS_DIRS,
    _AGENTS_DIRS_MINIMAL,
    _AGENTS_MD_TEMPLATE,
    _CLAUDE_MD_TEMPLATE,
    _COPILOT_INSTRUCTIONS_TEMPLATE,
    _GITIGNORE_ENTRIES,
    ProjectInitializer,
    main,
)

if TYPE_CHECKING:
    from _pytest.monkeypatch import MonkeyPatch


class TestProjectInitializerValidation:
    """Tests for target directory validation."""

    def test_valid_target_directory(self, tmp_path: Path) -> None:
        init = ProjectInitializer(target_dir=tmp_path)
        assert init.validate_target() is True

    def test_nonexistent_target_directory(self, tmp_path: Path) -> None:
        init = ProjectInitializer(target_dir=tmp_path / "nonexistent")
        assert init.validate_target() is False

    def test_target_is_file_not_directory(self, tmp_path: Path) -> None:
        file_path = tmp_path / "somefile.txt"
        file_path.write_text("content")
        init = ProjectInitializer(target_dir=file_path)
        assert init.validate_target() is False


class TestScaffoldAgentsDirs:
    """Tests for .agents/ directory creation."""

    def test_creates_full_directory_structure(self, tmp_path: Path) -> None:
        init = ProjectInitializer(target_dir=tmp_path)
        assert init.scaffold_agents_dirs() is True

        for dir_name in _AGENTS_DIRS:
            assert (tmp_path / ".agents" / dir_name).is_dir()

    def test_creates_minimal_directory_structure(self, tmp_path: Path) -> None:
        init = ProjectInitializer(target_dir=tmp_path, minimal=True)
        assert init.scaffold_agents_dirs() is True

        for dir_name in _AGENTS_DIRS_MINIMAL:
            assert (tmp_path / ".agents" / dir_name).is_dir()

        extra_dirs = set(_AGENTS_DIRS) - set(_AGENTS_DIRS_MINIMAL)
        for dir_name in extra_dirs:
            assert not (tmp_path / ".agents" / dir_name).exists()

    def test_idempotent_directory_creation(self, tmp_path: Path) -> None:
        init = ProjectInitializer(target_dir=tmp_path)
        init.scaffold_agents_dirs()
        assert init.scaffold_agents_dirs() is True


class TestScaffoldFiles:
    """Tests for file creation."""

    def test_creates_claude_md(self, tmp_path: Path) -> None:
        init = ProjectInitializer(target_dir=tmp_path)
        assert init.scaffold_claude_md() is True

        content = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
        assert content == _CLAUDE_MD_TEMPLATE

    def test_creates_agents_md(self, tmp_path: Path) -> None:
        init = ProjectInitializer(target_dir=tmp_path)
        assert init.scaffold_agents_md() is True

        content = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
        assert content == _AGENTS_MD_TEMPLATE

    def test_creates_copilot_instructions(self, tmp_path: Path) -> None:
        init = ProjectInitializer(target_dir=tmp_path)
        assert init.scaffold_copilot_instructions() is True

        path = tmp_path / ".github" / "copilot-instructions.md"
        assert path.exists()
        assert path.read_text(encoding="utf-8") == _COPILOT_INSTRUCTIONS_TEMPLATE

    def test_minimal_skips_copilot_instructions(self, tmp_path: Path) -> None:
        init = ProjectInitializer(target_dir=tmp_path, minimal=True)
        assert init.scaffold_copilot_instructions() is True

        assert not (tmp_path / ".github" / "copilot-instructions.md").exists()

    def test_skips_existing_files_without_force(self, tmp_path: Path) -> None:
        existing_content = "# My Custom CLAUDE.md"
        (tmp_path / "CLAUDE.md").write_text(existing_content)

        init = ProjectInitializer(target_dir=tmp_path)
        init.scaffold_claude_md()

        content = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
        assert content == existing_content
        assert len(init.skipped_files) == 1

    def test_overwrites_existing_files_with_force(self, tmp_path: Path) -> None:
        (tmp_path / "CLAUDE.md").write_text("# Old content")

        init = ProjectInitializer(target_dir=tmp_path, force=True)
        init.scaffold_claude_md()

        content = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
        assert content == _CLAUDE_MD_TEMPLATE


class TestDryRun:
    """Tests for --dry-run mode."""

    def test_dry_run_creates_no_files(self, tmp_path: Path) -> None:
        init = ProjectInitializer(target_dir=tmp_path, dry_run=True)
        result = init.run()

        assert result == 0
        assert not (tmp_path / "CLAUDE.md").exists()
        assert not (tmp_path / "AGENTS.md").exists()
        assert not (tmp_path / ".agents").exists()

    def test_dry_run_tracks_would_create(self, tmp_path: Path) -> None:
        init = ProjectInitializer(target_dir=tmp_path, dry_run=True)
        init.run()

        assert len(init.created_files) > 0
        assert len(init.created_dirs) > 0


class TestGitignoreUpdate:
    """Tests for .gitignore management."""

    def test_creates_gitignore_entries_when_no_file(self, tmp_path: Path) -> None:
        init = ProjectInitializer(target_dir=tmp_path)
        init.update_gitignore()

        content = (tmp_path / ".gitignore").read_text(encoding="utf-8")
        for entry in _GITIGNORE_ENTRIES:
            assert entry in content

    def test_appends_to_existing_gitignore(self, tmp_path: Path) -> None:
        (tmp_path / ".gitignore").write_text("node_modules/\n")

        init = ProjectInitializer(target_dir=tmp_path)
        init.update_gitignore()

        content = (tmp_path / ".gitignore").read_text(encoding="utf-8")
        assert "node_modules/" in content
        for entry in _GITIGNORE_ENTRIES:
            assert entry in content

    def test_skips_when_entries_already_present(self, tmp_path: Path) -> None:
        existing = "\n".join(_GITIGNORE_ENTRIES) + "\n"
        (tmp_path / ".gitignore").write_text(existing)

        init = ProjectInitializer(target_dir=tmp_path)
        init.update_gitignore()

        content = (tmp_path / ".gitignore").read_text(encoding="utf-8")
        assert content == existing


class TestFullRun:
    """Tests for the complete scaffolding workflow."""

    def test_full_run_succeeds(self, tmp_path: Path) -> None:
        init = ProjectInitializer(target_dir=tmp_path)
        result = init.run()

        assert result == 0
        assert (tmp_path / "CLAUDE.md").exists()
        assert (tmp_path / "AGENTS.md").exists()
        assert (tmp_path / ".agents" / "architecture").is_dir()
        assert (tmp_path / ".agents" / "sessions").is_dir()
        assert (tmp_path / ".github" / "copilot-instructions.md").exists()

    def test_minimal_run_succeeds(self, tmp_path: Path) -> None:
        init = ProjectInitializer(target_dir=tmp_path, minimal=True)
        result = init.run()

        assert result == 0
        assert (tmp_path / "CLAUDE.md").exists()
        assert (tmp_path / "AGENTS.md").exists()
        assert (tmp_path / ".agents" / "architecture").is_dir()
        assert not (tmp_path / ".agents" / "governance").exists()
        assert not (tmp_path / ".github" / "copilot-instructions.md").exists()

    def test_invalid_target_returns_exit_code_2(self, tmp_path: Path) -> None:
        init = ProjectInitializer(target_dir=tmp_path / "nonexistent")
        result = init.run()
        assert result == 2


class TestMainEntryPoint:
    """Tests for the main() CLI entry point."""

    def test_main_with_target_dir(self, tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.setattr(
            "sys.argv",
            ["init_project.py", "--target-dir", str(tmp_path)],
        )
        result = main()
        assert result == 0
        assert (tmp_path / "CLAUDE.md").exists()

    def test_main_dry_run(self, tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.setattr(
            "sys.argv",
            ["init_project.py", "--target-dir", str(tmp_path), "--dry-run"],
        )
        result = main()
        assert result == 0
        assert not (tmp_path / "CLAUDE.md").exists()

    def test_main_minimal(self, tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.setattr(
            "sys.argv",
            ["init_project.py", "--target-dir", str(tmp_path), "--minimal"],
        )
        result = main()
        assert result == 0
        assert not (tmp_path / ".agents" / "governance").exists()

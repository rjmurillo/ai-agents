"""Tests for init_project module."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.init_project import (
    _AGENTS_DIRS,
    _AGENTS_DIRS_MINIMAL,
    _AGENTS_MD_TEMPLATE,
    _CLAUDE_MD_TEMPLATE,
    _COPILOT_INSTRUCTIONS_TEMPLATE,
    _GETTING_STARTED_TEMPLATE,
    _GITIGNORE_ENTRIES,
    _VERSION_FILE,
    ProjectInitializer,
    _parse_only,
    _read_version_file,
    _scan_directory,
    main,
)


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

    def test_rejects_project_name_with_yaml_special_chars(self, tmp_path: Path) -> None:
        bad_dir = tmp_path / "my project: {inject}"
        bad_dir.mkdir()
        init = ProjectInitializer(target_dir=bad_dir)
        assert init.validate_target() is False

    def test_accepts_valid_project_name(self, tmp_path: Path) -> None:
        good_dir = tmp_path / "my-project_01"
        good_dir.mkdir()
        init = ProjectInitializer(target_dir=good_dir)
        assert init.validate_target() is True


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


class TestScaffoldTeamManifest:
    """Tests for .agents/team.yaml creation."""

    def test_creates_team_yaml(self, tmp_path: Path) -> None:
        init = ProjectInitializer(target_dir=tmp_path)
        init.scaffold_agents_dirs()
        assert init.scaffold_team_manifest() is True

        path = tmp_path / ".agents" / "team.yaml"
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "orchestrator" in content
        assert "implementer" in content

    def test_minimal_skips_team_yaml(self, tmp_path: Path) -> None:
        init = ProjectInitializer(target_dir=tmp_path, minimal=True)
        assert init.scaffold_team_manifest() is True
        assert not (tmp_path / ".agents" / "team.yaml").exists()

    def test_skips_existing_team_yaml_without_force(self, tmp_path: Path) -> None:
        agents_dir = tmp_path / ".agents"
        agents_dir.mkdir()
        existing = "# my team"
        (agents_dir / "team.yaml").write_text(existing)

        init = ProjectInitializer(target_dir=tmp_path)
        init.scaffold_team_manifest()

        content = (agents_dir / "team.yaml").read_text(encoding="utf-8")
        assert content == existing


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
        assert (tmp_path / ".agents" / "team.yaml").exists()
        assert (tmp_path / ".github" / "copilot-instructions.md").exists()

    def test_minimal_run_succeeds(self, tmp_path: Path) -> None:
        init = ProjectInitializer(target_dir=tmp_path, minimal=True)
        result = init.run()

        assert result == 0
        assert (tmp_path / "CLAUDE.md").exists()
        assert (tmp_path / "AGENTS.md").exists()
        assert (tmp_path / ".agents" / "architecture").is_dir()
        assert not (tmp_path / ".agents" / "governance").exists()
        assert not (tmp_path / ".agents" / "team.yaml").exists()
        assert not (tmp_path / ".github" / "copilot-instructions.md").exists()

    def test_invalid_target_returns_exit_code_2(self, tmp_path: Path) -> None:
        init = ProjectInitializer(target_dir=tmp_path / "nonexistent")
        result = init.run()
        assert result == 2


class TestMainEntryPoint:
    """Tests for the main() CLI entry point."""

    def test_main_with_init_subcommand(self, tmp_path: Path) -> None:
        result = main(["init", "--target-dir", str(tmp_path)])
        assert result == 0
        assert (tmp_path / "CLAUDE.md").exists()

    def test_main_no_args_shows_help(self, capsys: object) -> None:
        """No subcommand prints help and exits 0 without scaffolding."""
        result = main([])
        assert result == 0

    def test_main_dry_run(self, tmp_path: Path) -> None:
        result = main(["init", "--target-dir", str(tmp_path), "--dry-run"])
        assert result == 0
        assert not (tmp_path / "CLAUDE.md").exists()

    def test_main_minimal(self, tmp_path: Path) -> None:
        result = main(["init", "--target-dir", str(tmp_path), "--minimal"])
        assert result == 0
        assert not (tmp_path / ".agents" / "governance").exists()


class TestGettingStarted:
    """Tests for GETTING-STARTED.md creation (REQ-1.15)."""

    def test_init_creates_getting_started(self, tmp_path: Path) -> None:
        init = ProjectInitializer(target_dir=tmp_path)
        result = init.run()
        assert result == 0
        path = tmp_path / "GETTING-STARTED.md"
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "What you just got" in content
        assert "First 5 things to try" in content
        assert "If something looks broken" in content
        assert "Where to ask for help" in content

    def test_getting_started_content_is_one_page(self, tmp_path: Path) -> None:
        init = ProjectInitializer(target_dir=tmp_path)
        init.run()
        content = (tmp_path / "GETTING-STARTED.md").read_text(encoding="utf-8")
        assert len(content.splitlines()) <= 50

    def test_getting_started_matches_template(self, tmp_path: Path) -> None:
        init = ProjectInitializer(target_dir=tmp_path)
        assert init.scaffold_getting_started() is True
        content = (tmp_path / "GETTING-STARTED.md").read_text(encoding="utf-8")
        assert content == _GETTING_STARTED_TEMPLATE


class TestVersionFile:
    """Tests for .ai-agents-version.json (REQ-1.14 support)."""

    def test_init_writes_version_file(self, tmp_path: Path) -> None:
        init = ProjectInitializer(target_dir=tmp_path)
        init.run()
        version_path = tmp_path / _VERSION_FILE
        assert version_path.exists()
        data = json.loads(version_path.read_text(encoding="utf-8"))
        assert "version" in data
        assert "manifestHash" in data
        assert "installedAt" in data
        assert "source" in data

    def test_dry_run_does_not_write_version_file(self, tmp_path: Path) -> None:
        init = ProjectInitializer(target_dir=tmp_path, dry_run=True)
        init.run()
        assert not (tmp_path / _VERSION_FILE).exists()

    def test_read_version_file_returns_none_when_missing(self, tmp_path: Path) -> None:
        assert _read_version_file(tmp_path) is None

    def test_read_version_file_returns_data(self, tmp_path: Path) -> None:
        init = ProjectInitializer(target_dir=tmp_path)
        init.run()
        data = _read_version_file(tmp_path)
        assert data is not None
        assert data["version"] == "0.1.0"


class TestOnlyFlag:
    """Tests for --only flag (REQ-1.17)."""

    def test_only_agents_skips_claude_md(self, tmp_path: Path) -> None:
        init = ProjectInitializer(target_dir=tmp_path, only=frozenset({"agents"}))
        result = init.run()
        assert result == 0
        assert (tmp_path / "AGENTS.md").exists()
        assert (tmp_path / ".agents" / "team.yaml").exists()
        assert not (tmp_path / "CLAUDE.md").exists()
        assert not (tmp_path / "GETTING-STARTED.md").exists()

    def test_only_commands_skips_agents(self, tmp_path: Path) -> None:
        init = ProjectInitializer(target_dir=tmp_path, only=frozenset({"commands"}))
        result = init.run()
        assert result == 0
        assert (tmp_path / "CLAUDE.md").exists()
        assert (tmp_path / "GETTING-STARTED.md").exists()
        assert not (tmp_path / "AGENTS.md").exists()
        assert not (tmp_path / ".agents" / "team.yaml").exists()

    def test_only_multiple_categories(self, tmp_path: Path) -> None:
        init = ProjectInitializer(
            target_dir=tmp_path, only=frozenset({"commands", "agents"})
        )
        result = init.run()
        assert result == 0
        assert (tmp_path / "CLAUDE.md").exists()
        assert (tmp_path / "AGENTS.md").exists()

    def test_no_only_flag_scaffolds_everything(self, tmp_path: Path) -> None:
        init = ProjectInitializer(target_dir=tmp_path)
        result = init.run()
        assert result == 0
        assert (tmp_path / "CLAUDE.md").exists()
        assert (tmp_path / "AGENTS.md").exists()
        assert (tmp_path / "GETTING-STARTED.md").exists()

    def test_parse_only_valid(self) -> None:
        assert _parse_only("commands,agents") == frozenset({"commands", "agents"})

    def test_parse_only_none(self) -> None:
        assert _parse_only(None) is None

    def test_parse_only_invalid_returns_empty(self) -> None:
        result = _parse_only("invalid,stuff")
        assert result == frozenset()

    def test_main_with_only_flag(self, tmp_path: Path) -> None:
        result = main(["init", "--target-dir", str(tmp_path), "--only", "agents"])
        assert result == 0
        assert (tmp_path / "AGENTS.md").exists()
        assert not (tmp_path / "CLAUDE.md").exists()

    def test_main_with_invalid_only_returns_error(self, tmp_path: Path) -> None:
        result = main(["init", "--target-dir", str(tmp_path), "--only", "bogus"])
        assert result == 2


class TestListCommand:
    """Tests for the list subcommand (REQ-1.16)."""

    def test_list_no_content_returns_1(self, tmp_path: Path) -> None:
        result = main(["list", "--target-dir", str(tmp_path)])
        assert result == 1

    def test_list_with_commands(self, tmp_path: Path) -> None:
        commands_dir = tmp_path / ".claude" / "commands"
        commands_dir.mkdir(parents=True)
        (commands_dir / "build.md").write_text("# Build\nRun the build pipeline.\n")
        (commands_dir / "test.md").write_text("# Test\nRun tests.\n")

        result = main(["list", "--target-dir", str(tmp_path)])
        assert result == 0

    def test_list_filter_commands(self, tmp_path: Path) -> None:
        commands_dir = tmp_path / ".claude" / "commands"
        commands_dir.mkdir(parents=True)
        (commands_dir / "build.md").write_text("# Build\nRun the build pipeline.\n")

        agents_dir = tmp_path / ".claude" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "analyst.md").write_text("# Analyst\nResearch agent.\n")

        result = main(["list", "commands", "--target-dir", str(tmp_path)])
        assert result == 0

    def test_list_filter_agents(self, tmp_path: Path) -> None:
        agents_dir = tmp_path / ".claude" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "analyst.md").write_text("# Analyst\nResearch agent.\n")

        result = main(["list", "agents", "--target-dir", str(tmp_path)])
        assert result == 0

    def test_list_filter_skills(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / ".claude" / "skills" / "analyze"
        skills_dir.mkdir(parents=True)
        (skills_dir / "SKILL.md").write_text("# Analyze\nCode analysis skill.\n")

        result = main(["list", "skills", "--target-dir", str(tmp_path)])
        assert result == 0


class TestScanDirectory:
    """Tests for _scan_directory helper."""

    def test_scan_empty_directory(self, tmp_path: Path) -> None:
        result = _scan_directory(tmp_path / "nonexistent")
        assert result == []

    def test_scan_directory_with_files(self, tmp_path: Path) -> None:
        (tmp_path / "build.md").write_text("# Build\nRun the build pipeline.\n")
        (tmp_path / "test.md").write_text("# Test\nRun tests.\n")
        result = _scan_directory(tmp_path)
        assert len(result) == 2
        names = {item["name"] for item in result}
        assert names == {"build", "test"}

    def test_scan_directory_skips_hidden(self, tmp_path: Path) -> None:
        (tmp_path / ".hidden.md").write_text("hidden")
        (tmp_path / "visible.md").write_text("# Visible\nA visible file.\n")
        result = _scan_directory(tmp_path)
        assert len(result) == 1
        assert result[0]["name"] == "visible"

    def test_scan_directory_with_subdirs(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "analyze"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Analyze\nCode analysis skill.\n")
        result = _scan_directory(tmp_path)
        assert len(result) == 1
        assert result[0]["name"] == "analyze"
        assert result[0]["description"] == "Code analysis skill."


class TestUpdateCommand:
    """Tests for the update subcommand (REQ-1.13)."""

    def test_update_no_version_file_returns_2(self, tmp_path: Path) -> None:
        result = main(["update", "--target-dir", str(tmp_path)])
        assert result == 2

    def test_update_with_version_file_succeeds(self, tmp_path: Path) -> None:
        result = main(["init", "--target-dir", str(tmp_path)])
        assert result == 0
        result = main(["update", "--target-dir", str(tmp_path)])
        assert result == 0

    def test_update_refreshes_version_file(self, tmp_path: Path) -> None:
        main(["init", "--target-dir", str(tmp_path)])
        old_data = _read_version_file(tmp_path)
        assert old_data is not None
        main(["update", "--target-dir", str(tmp_path)])
        new_data = _read_version_file(tmp_path)
        assert new_data is not None
        assert new_data["version"] == old_data["version"]

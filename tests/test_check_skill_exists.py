"""Tests for check_skill_exists module.

These tests verify the skill discovery functionality used by the Phase 1.5
BLOCKING gate. This is a pilot migration from Check-SkillExists.ps1 per ADR-042.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from scripts.check_skill_exists import (
    VALID_OPERATIONS,
    check_skill_exists,
    get_skill_base_path,
    list_available_skills,
)

if TYPE_CHECKING:
    from _pytest.capture import CaptureFixture


class TestGetSkillBasePath:
    """Tests for get_skill_base_path function."""

    def test_returns_correct_path(self, tmp_path: Path) -> None:
        """Returns correct path relative to project root."""
        result = get_skill_base_path(tmp_path)

        expected = tmp_path / ".claude" / "skills" / "github" / "scripts"
        assert result == expected

    def test_handles_path_object(self, tmp_path: Path) -> None:
        """Accepts Path object as input."""
        result = get_skill_base_path(Path(str(tmp_path)))

        assert isinstance(result, Path)


class TestCheckSkillExists:
    """Tests for check_skill_exists function."""

    @pytest.fixture
    def skill_dir(self, tmp_path: Path) -> Path:
        """Create a mock skill directory structure."""
        skill_base = tmp_path / ".claude" / "skills" / "github" / "scripts"

        # Create pr directory with scripts
        pr_dir = skill_base / "pr"
        pr_dir.mkdir(parents=True)
        (pr_dir / "Get-PRContext.ps1").touch()
        (pr_dir / "Post-PRCommentReply.ps1").touch()
        (pr_dir / "Get-PRReviewers.ps1").touch()

        # Create issue directory with scripts
        issue_dir = skill_base / "issue"
        issue_dir.mkdir()
        (issue_dir / "Get-IssueContext.ps1").touch()
        (issue_dir / "Post-IssueComment.ps1").touch()

        # Create empty reactions directory
        reactions_dir = skill_base / "reactions"
        reactions_dir.mkdir()
        (reactions_dir / "Add-CommentReaction.ps1").touch()

        return skill_base

    def test_finds_existing_skill_exact_match(self, skill_dir: Path) -> None:
        """Returns True when skill with exact name exists."""
        result = check_skill_exists(skill_dir, "pr", "PRContext")

        assert result is True

    def test_finds_existing_skill_substring_match(self, skill_dir: Path) -> None:
        """Returns True when skill with substring match exists."""
        result = check_skill_exists(skill_dir, "pr", "Comment")

        assert result is True

    def test_finds_skill_case_sensitive(self, skill_dir: Path) -> None:
        """Substring matching is case-sensitive."""
        result = check_skill_exists(skill_dir, "pr", "prcontext")

        assert result is False

    def test_returns_false_for_missing_skill(self, skill_dir: Path) -> None:
        """Returns False when no matching skill exists."""
        result = check_skill_exists(skill_dir, "pr", "NonExistent")

        assert result is False

    def test_returns_false_for_missing_operation_dir(self, skill_dir: Path) -> None:
        """Returns False when operation directory does not exist."""
        result = check_skill_exists(skill_dir, "milestone", "Create")

        assert result is False

    def test_returns_false_for_invalid_operation(
        self,
        skill_dir: Path,
        capsys: CaptureFixture[str],
    ) -> None:
        """Returns False and prints error for invalid operation."""
        result = check_skill_exists(skill_dir, "invalid", "Action")

        assert result is False
        captured = capsys.readouterr()
        assert "Invalid operation" in captured.err

    def test_valid_operations_constant(self) -> None:
        """VALID_OPERATIONS contains expected values."""
        expected = {"pr", "issue", "reactions", "label", "milestone"}

        assert VALID_OPERATIONS == expected

    def test_finds_skill_in_issue_directory(self, skill_dir: Path) -> None:
        """Can find skills in issue directory."""
        result = check_skill_exists(skill_dir, "issue", "IssueContext")

        assert result is True

    def test_finds_skill_in_reactions_directory(self, skill_dir: Path) -> None:
        """Can find skills in reactions directory."""
        result = check_skill_exists(skill_dir, "reactions", "Reaction")

        assert result is True


class TestListAvailableSkills:
    """Tests for list_available_skills function."""

    @pytest.fixture
    def skill_dir(self, tmp_path: Path) -> Path:
        """Create a mock skill directory structure."""
        skill_base = tmp_path / ".claude" / "skills" / "github" / "scripts"

        # Create pr directory with scripts
        pr_dir = skill_base / "pr"
        pr_dir.mkdir(parents=True)
        (pr_dir / "Get-PRContext.ps1").touch()
        (pr_dir / "Post-PRCommentReply.ps1").touch()

        # Create issue directory with scripts
        issue_dir = skill_base / "issue"
        issue_dir.mkdir()
        (issue_dir / "Get-IssueContext.ps1").touch()

        return skill_base

    def test_lists_all_operations(
        self,
        skill_dir: Path,
        capsys: CaptureFixture[str],
    ) -> None:
        """Lists skills from all operation directories."""
        list_available_skills(skill_dir)

        captured = capsys.readouterr()
        assert "=== pr ===" in captured.out
        assert "=== issue ===" in captured.out
        assert "Get-PRContext" in captured.out
        assert "Get-IssueContext" in captured.out

    def test_skips_nonexistent_directories(
        self,
        skill_dir: Path,
        capsys: CaptureFixture[str],
    ) -> None:
        """Skips operation directories that do not exist."""
        list_available_skills(skill_dir)

        captured = capsys.readouterr()
        # milestone directory was not created
        assert "=== milestone ===" not in captured.out

    def test_handles_empty_directory(self, tmp_path: Path) -> None:
        """Handles empty skill base directory without error."""
        empty_base = tmp_path / "empty"
        empty_base.mkdir()

        # Should not raise
        list_available_skills(empty_base)


class TestScriptIntegration:
    """Integration tests for the script as a CLI tool."""

    @pytest.fixture
    def script_path(self, project_root: Path) -> Path:
        """Return path to the script."""
        return project_root / "scripts" / "check_skill_exists.py"

    def test_list_available_flag(self, script_path: Path) -> None:
        """--list-available flag works without error."""
        result = subprocess.run(
            [sys.executable, str(script_path), "--list-available"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        # Should succeed (exit 0)
        assert result.returncode == 0
        # Should have some output (at least the operation headers)
        assert "===" in result.stdout or result.stdout == ""

    def test_check_existing_skill(self, script_path: Path, project_root: Path) -> None:
        """Checking for existing skill returns true."""
        # This assumes the real skill directory exists
        skill_path = project_root / ".claude" / "skills" / "github" / "scripts" / "pr"
        if not skill_path.exists():
            pytest.skip("Skill directory does not exist in test environment")

        result = subprocess.run(
            [sys.executable, str(script_path), "--operation", "pr", "--action", "PRContext"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0
        assert "true" in result.stdout

    def test_check_missing_skill(self, script_path: Path) -> None:
        """Checking for missing skill returns false with exit code 1."""
        result = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--operation",
                "pr",
                "--action",
                "NonExistentSkillXYZ123",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 1
        assert "false" in result.stdout

    def test_missing_action_argument(self, script_path: Path) -> None:
        """--operation without --action returns error."""
        result = subprocess.run(
            [sys.executable, str(script_path), "--operation", "pr"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 1
        assert "ERROR" in result.stderr or "action" in result.stderr.lower()

    def test_mutual_exclusion(self, script_path: Path) -> None:
        """--list-available and --operation are mutually exclusive."""
        result = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--list-available",
                "--operation",
                "pr",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        # argparse should reject this
        assert result.returncode != 0

    def test_help_flag(self, script_path: Path) -> None:
        """--help flag shows usage information."""
        result = subprocess.run(
            [sys.executable, str(script_path), "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0
        assert "usage" in result.stdout.lower()
        assert "--operation" in result.stdout
        assert "--action" in result.stdout
        assert "--list-available" in result.stdout


class TestMainFunction:
    """Tests for main() function via monkeypatching."""

    @pytest.fixture
    def skill_dir(self, tmp_path: Path) -> Path:
        """Create a mock skill directory structure."""
        skill_base = tmp_path / ".claude" / "skills" / "github" / "scripts"

        pr_dir = skill_base / "pr"
        pr_dir.mkdir(parents=True)
        (pr_dir / "Get-PRContext.ps1").touch()

        return tmp_path

    def test_main_list_available(
        self,
        skill_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: CaptureFixture[str],
    ) -> None:
        """main() with --list-available returns 0."""
        from scripts import check_skill_exists

        monkeypatch.setattr(check_skill_exists, "_PROJECT_ROOT", skill_dir)
        monkeypatch.setattr(
            "sys.argv",
            ["check_skill_exists.py", "--list-available"],
        )

        result = check_skill_exists.main()

        assert result == 0
        captured = capsys.readouterr()
        assert "=== pr ===" in captured.out

    def test_main_check_existing_skill(
        self,
        skill_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: CaptureFixture[str],
    ) -> None:
        """main() with existing skill returns 0 and prints true."""
        from scripts import check_skill_exists

        monkeypatch.setattr(check_skill_exists, "_PROJECT_ROOT", skill_dir)
        monkeypatch.setattr(
            "sys.argv",
            ["check_skill_exists.py", "--operation", "pr", "--action", "PRContext"],
        )

        result = check_skill_exists.main()

        assert result == 0
        captured = capsys.readouterr()
        assert "true" in captured.out

    def test_main_check_missing_skill(
        self,
        skill_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: CaptureFixture[str],
    ) -> None:
        """main() with missing skill returns 1 and prints false."""
        from scripts import check_skill_exists

        monkeypatch.setattr(check_skill_exists, "_PROJECT_ROOT", skill_dir)
        monkeypatch.setattr(
            "sys.argv",
            ["check_skill_exists.py", "--operation", "pr", "--action", "NonExistent"],
        )

        result = check_skill_exists.main()

        assert result == 1
        captured = capsys.readouterr()
        assert "false" in captured.out

    def test_main_missing_action(
        self,
        skill_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: CaptureFixture[str],
    ) -> None:
        """main() without --action returns 1 with error."""
        from scripts import check_skill_exists

        monkeypatch.setattr(check_skill_exists, "_PROJECT_ROOT", skill_dir)
        monkeypatch.setattr(
            "sys.argv",
            ["check_skill_exists.py", "--operation", "pr"],
        )

        result = check_skill_exists.main()

        assert result == 1
        captured = capsys.readouterr()
        assert "ERROR" in captured.err

    def test_main_nonexistent_project_root(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: CaptureFixture[str],
    ) -> None:
        """main() with nonexistent project root returns 1."""
        from scripts import check_skill_exists

        fake_root = tmp_path / "nonexistent"
        monkeypatch.setattr(check_skill_exists, "_PROJECT_ROOT", fake_root)
        monkeypatch.setattr(
            "sys.argv",
            ["check_skill_exists.py", "--list-available"],
        )

        result = check_skill_exists.main()

        assert result == 1
        captured = capsys.readouterr()
        assert "does not exist" in captured.err

    def test_main_nonexistent_skill_path(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: CaptureFixture[str],
    ) -> None:
        """main() with existing project but no skill path returns 1."""
        from scripts import check_skill_exists

        # tmp_path exists but has no .claude directory
        monkeypatch.setattr(check_skill_exists, "_PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(
            "sys.argv",
            ["check_skill_exists.py", "--list-available"],
        )

        result = check_skill_exists.main()

        assert result == 1
        captured = capsys.readouterr()
        assert "Skill path does not exist" in captured.err

    def test_main_with_project_root_arg(
        self,
        skill_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: CaptureFixture[str],
    ) -> None:
        """main() accepts --project-root argument."""
        from scripts import check_skill_exists

        monkeypatch.setattr(
            "sys.argv",
            [
                "check_skill_exists.py",
                "--operation",
                "pr",
                "--action",
                "PRContext",
                "--project-root",
                str(skill_dir),
            ],
        )

        result = check_skill_exists.main()

        assert result == 0


class TestEdgeCases:
    """Edge case and boundary tests."""

    def test_empty_action_string(self, tmp_path: Path) -> None:
        """Empty action string raises ValueError."""
        skill_base = tmp_path / ".claude" / "skills" / "github" / "scripts"
        pr_dir = skill_base / "pr"
        pr_dir.mkdir(parents=True)
        (pr_dir / "Script.ps1").touch()

        # Empty action is explicitly rejected
        with pytest.raises(ValueError, match="Action cannot be empty"):
            check_skill_exists(skill_base, "pr", "")

    def test_action_with_special_chars(self, tmp_path: Path) -> None:
        """Action with glob special characters is handled safely."""
        skill_base = tmp_path / ".claude" / "skills" / "github" / "scripts"
        pr_dir = skill_base / "pr"
        pr_dir.mkdir(parents=True)
        (pr_dir / "Get-PRContext.ps1").touch()

        # Special chars should not cause issues (they just will not match)
        result = check_skill_exists(skill_base, "pr", "[*?]")

        assert result is False

    def test_deeply_nested_skill_not_found(self, tmp_path: Path) -> None:
        """Skills in subdirectories are not found (only direct children)."""
        skill_base = tmp_path / ".claude" / "skills" / "github" / "scripts"
        pr_dir = skill_base / "pr" / "nested"
        pr_dir.mkdir(parents=True)
        (pr_dir / "Hidden-Script.ps1").touch()

        result = check_skill_exists(skill_base, "pr", "Hidden")

        assert result is False

    def test_non_ps1_files_ignored(self, tmp_path: Path) -> None:
        """Only .ps1 files are considered as skills."""
        skill_base = tmp_path / ".claude" / "skills" / "github" / "scripts"
        pr_dir = skill_base / "pr"
        pr_dir.mkdir(parents=True)
        (pr_dir / "Script.py").touch()
        (pr_dir / "Script.txt").touch()
        (pr_dir / "Script.md").touch()

        result = check_skill_exists(skill_base, "pr", "Script")

        assert result is False

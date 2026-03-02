#!/usr/bin/env python3
"""Tests for validate_slash_command module."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(".claude/skills/slashcommandcreator/scripts/validate_slash_command.py")
validate_slash_command = mod.validate_slash_command
main = mod.main


class TestValidateSlashCommand:
    """Tests for validate_slash_command function."""

    def test_passes_valid_command(self, tmp_path: Path) -> None:
        cmd = tmp_path / "test.md"
        cmd.write_text(
            "---\n"
            "description: Use when testing validation\n"
            "argument-hint: <arg>\n"
            "allowed-tools: []\n"
            "---\n\n"
            "# Test Command\n\n"
            "Use $ARGUMENTS for input.\n"
        )
        result = validate_slash_command(str(cmd), skip_lint=True)
        assert result == 0

    def test_fails_missing_file(self, tmp_path: Path) -> None:
        result = validate_slash_command(str(tmp_path / "nonexistent.md"), skip_lint=True)
        assert result == 1

    def test_fails_missing_frontmatter(self, tmp_path: Path) -> None:
        cmd = tmp_path / "test.md"
        cmd.write_text("# No frontmatter\nSome content\n")
        result = validate_slash_command(str(cmd), skip_lint=True)
        assert result == 1

    def test_fails_missing_description(self, tmp_path: Path) -> None:
        cmd = tmp_path / "test.md"
        cmd.write_text("---\nargument-hint: <arg>\n---\n# Test\n")
        result = validate_slash_command(str(cmd), skip_lint=True)
        assert result == 1

    def test_warns_bad_description_verb(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        cmd = tmp_path / "test.md"
        cmd.write_text(
            "---\n"
            "description: This command does something\n"
            "---\n\n"
            "# Test\n"
        )
        result = validate_slash_command(str(cmd), skip_lint=True)
        # Should pass with warning (not blocking)
        assert result == 0
        captured = capsys.readouterr()
        assert "WARNING" in captured.out

    def test_fails_arguments_without_hint(self, tmp_path: Path) -> None:
        cmd = tmp_path / "test.md"
        cmd.write_text(
            "---\n"
            "description: Use when testing\n"
            "---\n\n"
            "Use $ARGUMENTS here\n"
        )
        result = validate_slash_command(str(cmd), skip_lint=True)
        assert result == 1

    def test_warns_hint_without_arguments(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        cmd = tmp_path / "test.md"
        cmd.write_text(
            "---\n"
            "description: Use when testing\n"
            "argument-hint: <arg>\n"
            "---\n\n"
            "No arguments used.\n"
        )
        result = validate_slash_command(str(cmd), skip_lint=True)
        assert result == 0
        captured = capsys.readouterr()
        assert "WARNING" in captured.out

    def test_fails_bash_without_allowed_tools(self, tmp_path: Path) -> None:
        cmd = tmp_path / "test.md"
        cmd.write_text(
            "---\n"
            "description: Use when testing\n"
            "---\n\n"
            "Run ! git status\n"
        )
        result = validate_slash_command(str(cmd), skip_lint=True)
        assert result == 1

    def test_fails_overly_permissive_wildcard(self, tmp_path: Path) -> None:
        cmd = tmp_path / "test.md"
        cmd.write_text(
            "---\n"
            "description: Use when testing\n"
            "allowed-tools: [*]\n"
            "---\n\n"
            "Run ! git status\n"
        )
        result = validate_slash_command(str(cmd), skip_lint=True)
        assert result == 1

    def test_passes_mcp_scoped_wildcard(self, tmp_path: Path) -> None:
        cmd = tmp_path / "test.md"
        cmd.write_text(
            "---\n"
            "description: Use when testing\n"
            "allowed-tools: [mcp__serena__*]\n"
            "---\n\n"
            "Run ! git status\n"
        )
        result = validate_slash_command(str(cmd), skip_lint=True)
        assert result == 0

    def test_warns_long_file(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        cmd = tmp_path / "test.md"
        lines = ["---", "description: Use when testing", "---", ""]
        lines.extend(["# Line"] * 200)
        cmd.write_text("\n".join(lines))
        result = validate_slash_command(str(cmd), skip_lint=True)
        assert result == 0
        captured = capsys.readouterr()
        assert "WARNING" in captured.out
        assert ">200" in captured.out


class TestMain:
    """Tests for main entry point."""

    def test_validates_file(self, tmp_path: Path) -> None:
        cmd = tmp_path / "test.md"
        cmd.write_text(
            "---\n"
            "description: Use when testing\n"
            "---\n\n"
            "# Test\n"
        )
        with patch("sys.argv", ["validate_slash_command.py", "--path", str(cmd), "--skip-lint"]):
            result = main()
        assert result == 0

    def test_fails_invalid_file(self, tmp_path: Path) -> None:
        argv = [
            "validate_slash_command.py", "--path",
            str(tmp_path / "nope.md"), "--skip-lint",
        ]
        with patch("sys.argv", argv):
            result = main()
        assert result == 1

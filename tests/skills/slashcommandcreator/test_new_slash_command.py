#!/usr/bin/env python3
"""Tests for new_slash_command module."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(".claude/skills/slashcommandcreator/scripts/new_slash_command.py")
_validate_name = mod._validate_name
main = mod.main


class TestValidateName:
    """Tests for _validate_name function."""

    def test_valid_names(self) -> None:
        assert _validate_name("security-audit") is True
        assert _validate_name("test_command") is True
        assert _validate_name("cmd123") is True
        assert _validate_name("A-B-C") is True

    def test_rejects_empty(self) -> None:
        assert _validate_name("") is False

    def test_rejects_spaces(self) -> None:
        assert _validate_name("has space") is False

    def test_rejects_path_traversal(self) -> None:
        assert _validate_name("../evil") is False
        assert _validate_name("../../etc/passwd") is False

    def test_rejects_special_chars(self) -> None:
        assert _validate_name("cmd;rm") is False
        assert _validate_name("cmd|pipe") is False
        assert _validate_name("cmd$var") is False


class TestMain:
    """Tests for main entry point."""

    def test_creates_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = main(["--name", "test-cmd"])
        assert result == 0
        assert (tmp_path / ".claude" / "commands" / "test-cmd.md").exists()

    def test_creates_namespaced_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        result = main(["--name", "status", "--namespace", "git"])
        assert result == 0
        assert (tmp_path / ".claude" / "commands" / "git" / "status.md").exists()

    def test_file_contains_frontmatter(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        main(["--name", "test-cmd"])
        content = (tmp_path / ".claude" / "commands" / "test-cmd.md").read_text()
        assert "---" in content
        assert "description:" in content
        assert "argument-hint:" in content
        assert "allowed-tools:" in content

    def test_file_contains_command_name(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        main(["--name", "my-cmd"])
        content = (tmp_path / ".claude" / "commands" / "my-cmd.md").read_text()
        assert "my-cmd" in content

    def test_rejects_existing_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        cmd_dir = tmp_path / ".claude" / "commands"
        cmd_dir.mkdir(parents=True)
        (cmd_dir / "existing.md").write_text("already here")
        result = main(["--name", "existing"])
        assert result == 1

    def test_rejects_invalid_name(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        result = main(["--name", "../evil"])
        assert result == 1

    def test_rejects_invalid_namespace(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        result = main(["--name", "test", "--namespace", "../evil"])
        assert result == 1

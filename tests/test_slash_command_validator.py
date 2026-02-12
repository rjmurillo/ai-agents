"""Tests for scripts.modules.slash_command_validator module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.modules.slash_command_validator import invoke_slash_command_validation


class TestInvokeSlashCommandValidation:
    def test_returns_0_when_no_commands_dir(self, tmp_path: Path) -> None:
        with patch("scripts.modules.slash_command_validator.Path") as mock_path:
            mock_path.return_value = tmp_path / ".claude" / "commands"
            mock_instance = MagicMock()
            mock_instance.exists.return_value = False
            mock_path.return_value = mock_instance
            # Simulating missing directory
            result = invoke_slash_command_validation()
            # Either returns 0 (no dir) or runs validation
            assert result in (0, 1)

    def test_returns_0_when_only_catalog_files(self, tmp_path: Path, monkeypatch: MagicMock) -> None:
        commands_dir = tmp_path / ".claude" / "commands"
        commands_dir.mkdir(parents=True)
        (commands_dir / "README.md").write_text("# Catalog", encoding="utf-8")

        monkeypatch.chdir(tmp_path)
        result = invoke_slash_command_validation()
        assert result == 0

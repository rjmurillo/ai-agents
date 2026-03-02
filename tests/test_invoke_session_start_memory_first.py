#!/usr/bin/env python3
"""Tests for hooks/invoke_session_start_memory_first.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Add hook directory to path for import
sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent / ".claude" / "hooks"),
)

import invoke_session_start_memory_first as hook


class TestReadForgetfulConfig:
    """Tests for read_forgetful_config()."""

    def test_returns_defaults_when_no_config(self, tmp_path: Path) -> None:
        host, port = hook.read_forgetful_config(str(tmp_path / "nonexistent.json"))
        assert host == "localhost"
        assert port == 8020

    def test_reads_valid_config(self, tmp_path: Path) -> None:
        config: dict[str, object] = {"mcpServers": {"forgetful": {"url": "http://myhost:9090/api"}}}
        config_file = tmp_path / ".mcp.json"
        config_file.write_text(json.dumps(config), encoding="utf-8")

        host, port = hook.read_forgetful_config(str(config_file))
        assert host == "myhost"
        assert port == 9090

    def test_falls_back_on_missing_forgetful_key(self, tmp_path: Path) -> None:
        config: dict[str, object] = {"mcpServers": {}}
        config_file = tmp_path / ".mcp.json"
        config_file.write_text(json.dumps(config), encoding="utf-8")

        host, port = hook.read_forgetful_config(str(config_file))
        assert host == "localhost"
        assert port == 8020

    def test_falls_back_on_invalid_json(self, tmp_path: Path) -> None:
        config_file = tmp_path / ".mcp.json"
        config_file.write_text("not valid json", encoding="utf-8")

        host, port = hook.read_forgetful_config(str(config_file))
        assert host == "localhost"
        assert port == 8020

    def test_falls_back_on_empty_url(self, tmp_path: Path) -> None:
        config: dict[str, object] = {"mcpServers": {"forgetful": {"url": ""}}}
        config_file = tmp_path / ".mcp.json"
        config_file.write_text(json.dumps(config), encoding="utf-8")

        host, port = hook.read_forgetful_config(str(config_file))
        assert host == "localhost"
        assert port == 8020


class TestMain:
    """Tests for main() entry point."""

    def test_outputs_adr_007_status(self, capsys: pytest.CaptureFixture[str]) -> None:
        result = hook.main()
        assert result == 0
        captured = capsys.readouterr()
        assert "ADR-007 active" in captured.out
        assert "Forgetful" in captured.out
        # AGENTS.md reference is now conditional on file existence

    def test_always_exits_zero(self) -> None:
        assert hook.main() == 0

#!/usr/bin/env python3
"""Tests for the invoke_session_start_memory_first hook.

Covers: MCP config parsing, fallback defaults, main entry point.
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

HOOK_DIR = str(Path(__file__).resolve().parents[2] / ".claude" / "hooks")
sys.path.insert(0, HOOK_DIR)

import invoke_session_start_memory_first  # noqa: E402

# ---------------------------------------------------------------------------
# Unit tests for read_forgetful_config
# ---------------------------------------------------------------------------


class TestReadForgetfulConfig:
    """Tests for read_forgetful_config function."""

    def test_returns_defaults_when_file_missing(self):
        host, port = invoke_session_start_memory_first.read_forgetful_config(
            "/nonexistent/.mcp.json"
        )
        assert host == "localhost"
        assert port == 8020

    def test_parses_valid_config(self, tmp_path):
        config = {
            "mcpServers": {
                "forgetful": {
                    "url": "http://myhost:9090/api"
                }
            }
        }
        config_file = tmp_path / ".mcp.json"
        config_file.write_text(json.dumps(config))
        host, port = invoke_session_start_memory_first.read_forgetful_config(
            str(config_file)
        )
        assert host == "myhost"
        assert port == 9090

    def test_returns_defaults_on_invalid_json(self, tmp_path):
        config_file = tmp_path / ".mcp.json"
        config_file.write_text("not json")
        host, port = invoke_session_start_memory_first.read_forgetful_config(
            str(config_file)
        )
        assert host == "localhost"
        assert port == 8020

    def test_returns_defaults_when_no_forgetful_key(self, tmp_path):
        config = {"mcpServers": {"other": {"url": "http://other:1234"}}}
        config_file = tmp_path / ".mcp.json"
        config_file.write_text(json.dumps(config))
        host, port = invoke_session_start_memory_first.read_forgetful_config(
            str(config_file)
        )
        assert host == "localhost"
        assert port == 8020

    def test_returns_defaults_when_no_url(self, tmp_path):
        config = {"mcpServers": {"forgetful": {"name": "forgetful"}}}
        config_file = tmp_path / ".mcp.json"
        config_file.write_text(json.dumps(config))
        host, port = invoke_session_start_memory_first.read_forgetful_config(
            str(config_file)
        )
        assert host == "localhost"
        assert port == 8020

    def test_returns_defaults_when_empty_url(self, tmp_path):
        config = {"mcpServers": {"forgetful": {"url": ""}}}
        config_file = tmp_path / ".mcp.json"
        config_file.write_text(json.dumps(config))
        host, port = invoke_session_start_memory_first.read_forgetful_config(
            str(config_file)
        )
        assert host == "localhost"
        assert port == 8020

    def test_returns_defaults_when_mcp_servers_missing(self, tmp_path):
        config = {"other": "value"}
        config_file = tmp_path / ".mcp.json"
        config_file.write_text(json.dumps(config))
        host, port = invoke_session_start_memory_first.read_forgetful_config(
            str(config_file)
        )
        assert host == "localhost"
        assert port == 8020


# ---------------------------------------------------------------------------
# Unit tests for main
# ---------------------------------------------------------------------------


class TestMain:
    """Tests for the main entry point."""

    @pytest.fixture(autouse=True)
    def _no_consumer_repo_skip(self):
        with patch("invoke_session_start_memory_first.skip_if_consumer_repo", return_value=False):
            yield

    def test_returns_0_and_produces_output(self, capsys):
        result = invoke_session_start_memory_first.main()
        assert result == 0
        captured = capsys.readouterr()
        assert "ADR-007 active" in captured.out

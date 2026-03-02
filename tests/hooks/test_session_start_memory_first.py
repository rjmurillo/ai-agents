#!/usr/bin/env python3
"""Tests for the session start memory-first hook.

Covers: MCP config parsing, fallback defaults, output generation
with/without Forgetful available.
"""

import json
import sys
from pathlib import Path

import pytest

HOOK_DIR = str(Path(__file__).resolve().parents[2] / ".claude" / "hooks")
sys.path.insert(0, HOOK_DIR)

import session_start_memory_first  # noqa: E402

# ---------------------------------------------------------------------------
# Unit tests for read_forgetful_config
# ---------------------------------------------------------------------------


class TestReadForgetfulConfig:
    """Tests for read_forgetful_config function."""

    def test_returns_defaults_when_file_missing(self):
        host, port = session_start_memory_first.read_forgetful_config(
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
        host, port = session_start_memory_first.read_forgetful_config(
            str(config_file)
        )
        assert host == "myhost"
        assert port == 9090

    def test_returns_defaults_on_invalid_json(self, tmp_path):
        config_file = tmp_path / ".mcp.json"
        config_file.write_text("not json")
        host, port = session_start_memory_first.read_forgetful_config(
            str(config_file)
        )
        assert host == "localhost"
        assert port == 8020

    def test_returns_defaults_when_no_forgetful_key(self, tmp_path):
        config = {"mcpServers": {"other": {"url": "http://other:1234"}}}
        config_file = tmp_path / ".mcp.json"
        config_file.write_text(json.dumps(config))
        host, port = session_start_memory_first.read_forgetful_config(
            str(config_file)
        )
        assert host == "localhost"
        assert port == 8020

    def test_returns_defaults_when_no_url(self, tmp_path):
        config = {"mcpServers": {"forgetful": {"name": "forgetful"}}}
        config_file = tmp_path / ".mcp.json"
        config_file.write_text(json.dumps(config))
        host, port = session_start_memory_first.read_forgetful_config(
            str(config_file)
        )
        assert host == "localhost"
        assert port == 8020

    def test_returns_defaults_when_empty_url(self, tmp_path):
        config = {"mcpServers": {"forgetful": {"url": ""}}}
        config_file = tmp_path / ".mcp.json"
        config_file.write_text(json.dumps(config))
        host, port = session_start_memory_first.read_forgetful_config(
            str(config_file)
        )
        assert host == "localhost"
        assert port == 8020

    def test_returns_defaults_when_mcp_servers_missing(self, tmp_path):
        config = {"other": "value"}
        config_file = tmp_path / ".mcp.json"
        config_file.write_text(json.dumps(config))
        host, port = session_start_memory_first.read_forgetful_config(
            str(config_file)
        )
        assert host == "localhost"
        assert port == 8020


# ---------------------------------------------------------------------------
# Unit tests for build_output
# ---------------------------------------------------------------------------


class TestBuildOutput:
    """Tests for build_output function."""

    def test_includes_blocking_gate(self):
        output = session_start_memory_first.build_output(
            forgetful_available=False
        )
        assert "BLOCKING GATE" in output

    def test_includes_memory_index_table(self):
        output = session_start_memory_first.build_output(
            forgetful_available=False
        )
        assert "memory-index" in output
        assert "GitHub PR operations" in output

    def test_includes_serena_initialization(self):
        output = session_start_memory_first.build_output(
            forgetful_available=False
        )
        assert "mcp__serena__activate_project" in output
        assert "mcp__serena__initial_instructions" in output

    def test_includes_fallback_when_unavailable(self):
        output = session_start_memory_first.build_output(
            forgetful_available=False
        )
        assert "Fallback Mode" in output

    def test_excludes_fallback_when_available(self):
        output = session_start_memory_first.build_output(
            forgetful_available=True
        )
        assert "Fallback Mode" not in output

    def test_includes_optional_step_when_available(self):
        output = session_start_memory_first.build_output(
            forgetful_available=True
        )
        assert "(Optional) Query Forgetful" in output

    def test_excludes_optional_step_when_unavailable(self):
        output = session_start_memory_first.build_output(
            forgetful_available=False
        )
        assert "(Optional) Query Forgetful" not in output

    def test_includes_verification_section(self):
        output = session_start_memory_first.build_output(
            forgetful_available=False
        )
        assert "Verification" in output
        assert "SESSION-PROTOCOL" in output


# ---------------------------------------------------------------------------
# Unit tests for main
# ---------------------------------------------------------------------------


class TestMain:
    """Tests for the main entry point."""

    def test_exits_0_and_produces_output(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            session_start_memory_first.main()
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "ADR-007" in captured.out
        assert "BLOCKING GATE" in captured.out

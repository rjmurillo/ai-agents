"""Tests for scripts.mcp_cli.wrapper module.

Tests the MCPorter CLI wrapper that provides direct MCP tool invocation
from Python scripts and hooks without LLM inference overhead.

See: Issue #1484
"""

from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from scripts.mcp_cli.wrapper import (
    McpCliError,
    _find_mcporter,
    mcp_call,
    mcp_list_tools,
)


class TestFindMcporter:
    def test_finds_local_mcporter(self) -> None:
        def which_mcporter(cmd: str) -> str | None:
            return "/usr/bin/mcporter" if cmd == "mcporter" else None

        with patch("shutil.which", side_effect=which_mcporter):
            assert _find_mcporter() == ["mcporter"]

    def test_falls_back_to_npx(self) -> None:
        def which_side_effect(cmd: str) -> str | None:
            if cmd == "npx":
                return "/usr/bin/npx"
            return None

        with patch("shutil.which", side_effect=which_side_effect):
            assert _find_mcporter() == ["npx", "mcporter"]

    def test_raises_when_neither_available(self) -> None:
        with patch("shutil.which", return_value=None):
            with pytest.raises(McpCliError, match="mcporter not found"):
                _find_mcporter()


class TestMcpCall:
    def _make_result(
        self,
        stdout: str = "{}",
        stderr: str = "",
        returncode: int = 0,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=["mcporter", "call", "serena.list_memories", "--json"],
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
        )

    @patch("shutil.which", return_value="/usr/bin/mcporter")
    @patch("subprocess.run")
    def test_basic_call_no_args(self, mock_run: MagicMock, _which: MagicMock) -> None:
        mock_run.return_value = self._make_result(stdout='{"memories": []}')
        result = mcp_call("serena", "list_memories")
        assert result == {"memories": []}

        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert cmd == ["mcporter", "call", "serena.list_memories", "--json"]

    @patch("shutil.which", return_value="/usr/bin/mcporter")
    @patch("subprocess.run")
    def test_call_with_string_args(self, mock_run: MagicMock, _which: MagicMock) -> None:
        mock_run.return_value = self._make_result(stdout='{"content": "hello"}')
        mcp_call("serena", "read_memory", name="test-mem")

        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert "name:test-mem" in cmd

    @patch("shutil.which", return_value="/usr/bin/mcporter")
    @patch("subprocess.run")
    def test_call_with_bool_args(self, mock_run: MagicMock, _which: MagicMock) -> None:
        mock_run.return_value = self._make_result()
        mcp_call("serena", "find_symbol", include_body=True)

        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert "include_body:true" in cmd

    @patch("shutil.which", return_value="/usr/bin/mcporter")
    @patch("subprocess.run")
    def test_call_with_dict_args(self, mock_run: MagicMock, _which: MagicMock) -> None:
        mock_run.return_value = self._make_result()
        mcp_call("serena", "write_memory", content={"key": "value"})

        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert 'content:{"key": "value"}' in cmd

    @patch("shutil.which", return_value="/usr/bin/mcporter")
    @patch("subprocess.run")
    def test_call_with_cwd(self, mock_run: MagicMock, _which: MagicMock) -> None:
        mock_run.return_value = self._make_result()
        mcp_call("serena", "list_memories", cwd="/some/path")

        call_args = mock_run.call_args
        assert call_args[1]["cwd"] == "/some/path"

    @patch("shutil.which", return_value="/usr/bin/mcporter")
    @patch("subprocess.run")
    def test_raises_on_nonzero_exit(self, mock_run: MagicMock, _which: MagicMock) -> None:
        mock_run.return_value = self._make_result(
            returncode=1, stderr="Error: server not found"
        )
        with pytest.raises(McpCliError, match="mcporter call failed"):
            mcp_call("serena", "list_memories")

    @patch("shutil.which", return_value="/usr/bin/mcporter")
    @patch("subprocess.run")
    def test_raises_on_timeout(self, mock_run: MagicMock, _which: MagicMock) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="mcporter", timeout=30)
        with pytest.raises(McpCliError, match="timed out"):
            mcp_call("serena", "list_memories")

    @patch("shutil.which", return_value="/usr/bin/mcporter")
    @patch("subprocess.run")
    def test_returns_empty_on_empty_stdout(self, mock_run: MagicMock, _which: MagicMock) -> None:
        mock_run.return_value = self._make_result(stdout="")
        assert mcp_call("serena", "list_memories") == {}

    @patch("shutil.which", return_value="/usr/bin/mcporter")
    @patch("subprocess.run")
    def test_returns_raw_on_non_json_stdout(self, mock_run: MagicMock, _which: MagicMock) -> None:
        mock_run.return_value = self._make_result(stdout="not json")
        result = mcp_call("serena", "list_memories")
        assert result == {"raw": "not json"}

    @patch("shutil.which", return_value=None)
    def test_raises_when_mcporter_unavailable(self, _which: MagicMock) -> None:
        with pytest.raises(McpCliError, match="mcporter not found"):
            mcp_call("serena", "list_memories")


class TestMcpListTools:
    @patch("shutil.which", return_value="/usr/bin/mcporter")
    @patch("subprocess.run")
    def test_returns_tools_for_server(self, mock_run: MagicMock, _which: MagicMock) -> None:
        server_data = {
            "servers": [{
                "name": "serena",
                "tools": [
                    {"name": "list_memories", "description": "List memories"},
                    {"name": "read_memory", "description": "Read a memory"},
                ],
            }],
        }
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json.dumps(server_data), stderr=""
        )
        tools = mcp_list_tools("serena")
        assert len(tools) == 2
        assert tools[0]["name"] == "list_memories"

    @patch("shutil.which", return_value="/usr/bin/mcporter")
    @patch("subprocess.run")
    def test_returns_empty_for_unknown_server(self, mock_run: MagicMock, _which: MagicMock) -> None:
        server_data = {"servers": [{"name": "other", "tools": []}]}
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json.dumps(server_data), stderr=""
        )
        assert mcp_list_tools("serena") == []

    @patch("shutil.which", return_value="/usr/bin/mcporter")
    @patch("subprocess.run")
    def test_raises_on_failure(self, mock_run: MagicMock, _which: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="failed"
        )
        with pytest.raises(McpCliError, match="mcporter list failed"):
            mcp_list_tools("serena")

    @patch("shutil.which", return_value="/usr/bin/mcporter")
    @patch("subprocess.run")
    def test_returns_empty_on_empty_stdout(self, mock_run: MagicMock, _which: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        assert mcp_list_tools("serena") == []

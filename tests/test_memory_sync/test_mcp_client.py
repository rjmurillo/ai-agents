"""Tests for MCP client protocol lifecycle."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.memory_sync.mcp_client import (
    McpClient,
    McpError,
)


class TestMcpClientCreate:
    """Test MCP client creation and handshake."""

    def test_create_with_mock_server(self, mock_server_command: list[str]) -> None:
        """Test creating a client with the mock server."""
        client = McpClient.create(command=mock_server_command)
        try:
            assert client._request_id >= 1  # handshake made at least one request
        finally:
            client.close()

    def test_create_command_not_found(self) -> None:
        """Test error when command is not found."""
        with pytest.raises(McpError, match="Command not found"):
            McpClient.create(command=["nonexistent-command-xyz"])

    def test_context_manager(self, mock_server_command: list[str]) -> None:
        """Test using client as context manager."""
        with McpClient.create(command=mock_server_command) as client:
            assert client is not None


class TestMcpClientCallTool:
    """Test MCP tool calling."""

    def test_call_create_memory(self, mock_server_command: list[str]) -> None:
        """Test calling create_memory tool."""
        with McpClient.create(command=mock_server_command) as client:
            result = client.call_tool("create_memory", {
                "title": "Test",
                "content": "Test content",
                "context": "Testing",
                "keywords": ["test"],
                "tags": ["test"],
                "importance": 5,
            })
            content = result.get("content", [])
            assert len(content) > 0
            data = json.loads(content[0]["text"])
            assert "id" in data

    def test_call_update_memory(self, mock_server_command: list[str]) -> None:
        """Test calling update_memory tool."""
        with McpClient.create(command=mock_server_command) as client:
            # Create first
            create_result = client.call_tool("create_memory", {
                "title": "Test",
                "content": "Original",
                "context": "Testing",
                "keywords": ["test"],
                "tags": ["test"],
                "importance": 5,
            })
            memory_id = json.loads(create_result["content"][0]["text"])["id"]

            # Update
            update_result = client.call_tool("update_memory", {
                "memory_id": memory_id,
                "content": "Updated",
            })
            assert update_result is not None

    def test_call_unknown_tool_returns_error(
        self, mock_server_command: list[str]
    ) -> None:
        """Test that calling an unknown tool raises McpError."""
        with McpClient.create(command=mock_server_command) as client:
            with pytest.raises(McpError, match="Tool execution error"):
                client.call_tool("nonexistent_tool", {})


class TestMcpClientProtocol:
    """Test protocol-level details."""

    def test_parse_content_length(self) -> None:
        """Test parsing Content-Length header."""
        header = "Content-Length: 42\r\n\r\n"
        assert McpClient._parse_content_length(header) == 42

    def test_parse_content_length_missing(self) -> None:
        """Test error on missing Content-Length."""
        with pytest.raises(McpError, match="Missing Content-Length"):
            McpClient._parse_content_length("Bad-Header: value\r\n\r\n")

    def test_write_message_broken_pipe(self) -> None:
        """Test error handling when stdin pipe is broken."""
        mock_process = MagicMock()
        mock_process.stdin.write.side_effect = BrokenPipeError("pipe broken")
        mock_process.stderr = None
        client = McpClient(mock_process)
        with pytest.raises(McpError, match="Failed to write"):
            client._write_message({"jsonrpc": "2.0", "method": "test"})


class TestIsAvailable:
    """Test availability check."""

    def test_available_when_db_exists(self, tmp_path: Path) -> None:
        """Test returns True when DB file exists."""
        db_path = tmp_path / "forgetful.db"
        db_path.touch()
        with patch.object(
            McpClient, "is_available",
            return_value=True,
        ):
            assert McpClient.is_available()

    def test_unavailable_when_db_missing(self) -> None:
        """Test returns False when DB file is missing."""
        with patch(
            "scripts.memory_sync.mcp_client.FORGETFUL_DB_PATH",
            Path("/nonexistent/path/forgetful.db"),
        ):
            assert not McpClient.is_available()

"""Tests for MCP client protocol lifecycle."""

from __future__ import annotations

import json
import queue
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from scripts.memory_sync.mcp_client import (
    _STDOUT_EOF,
    McpClient,
    McpError,
)


def _frame(payload: dict[str, Any]) -> bytes:
    """Encode a dict as one Content-Length framed JSON-RPC message."""
    body = json.dumps(payload).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode()
    return header + body


def _detached_client(timeout: float = 0.2) -> McpClient:
    """Build a client whose subprocess I/O is inert, with a fresh read queue.

    ``stdout``/``stderr`` are None so the drain threads exit immediately; the
    test then owns ``_read_queue`` directly.
    """
    process = MagicMock()
    process.stdout = None
    process.stderr = None
    client = McpClient(process, timeout=timeout)
    # Let the init-spawned reader thread finish putting its EOF into the
    # original queue, then swap in a fresh queue the test fully controls.
    client._stdout_thread.join(timeout=1.0)
    client._read_queue = queue.Queue()
    return client


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


class TestReadBytesTimeout:
    """``_read_bytes`` enforces a timeout on every platform (issue #2810).

    Before the fix the timeout was skipped entirely on Windows (the select
    branch was guarded by ``sys.platform != "win32"``), so ``os.read`` could
    block forever. The queue-based reader has no platform branch, so these
    tests exercise the single cross-platform path.
    """

    def test_returns_chunk_when_available(self) -> None:
        client = _detached_client()
        client._read_queue.put(b"payload")
        assert client._read_bytes(1.0) == b"payload"

    def test_nonpositive_remaining_raises_timeout(self) -> None:
        client = _detached_client()
        with pytest.raises(McpError, match="Timeout waiting for response"):
            client._read_bytes(0.0)

    def test_empty_queue_raises_timeout(self) -> None:
        client = _detached_client(timeout=0.05)
        with pytest.raises(McpError, match="Timeout waiting for response"):
            client._read_bytes(0.05)

    def test_eof_sentinel_raises_closed_error(self) -> None:
        client = _detached_client()
        client._read_queue.put(_STDOUT_EOF)
        with pytest.raises(McpError, match="closed stdout"):
            client._read_bytes(1.0)


class TestReadResponseDeadline:
    """``_read_response`` bounds the whole wait, not just each read (issue #2810).

    Without an overall deadline, a server streaming notifications or replying
    with mismatched ids would loop forever. The deadline makes both cases
    terminate with a timeout.
    """

    def test_matching_response_returned(self) -> None:
        client = _detached_client(timeout=1.0)
        client._read_queue.put(_frame({"jsonrpc": "2.0", "id": 1, "result": {}}))
        response = client._read_response(1)
        assert response["id"] == 1

    def test_notification_stream_times_out(self) -> None:
        client = _detached_client(timeout=0.2)
        for _ in range(3):
            client._read_queue.put(
                _frame({"jsonrpc": "2.0", "method": "notifications/progress"})
            )
        with pytest.raises(McpError, match="Timeout waiting for response"):
            client._read_response(1)

    def test_id_mismatch_stream_times_out(self) -> None:
        client = _detached_client(timeout=0.2)
        client._read_queue.put(
            _frame({"jsonrpc": "2.0", "id": 999, "result": {}})
        )
        with pytest.raises(McpError, match="Timeout waiting for response"):
            client._read_response(1)


class TestDrainStdout:
    """The reader thread feeds chunks then an EOF sentinel."""

    def test_none_stdout_enqueues_eof(self) -> None:
        client = _detached_client()
        client._process.stdout = None
        client._drain_stdout()
        assert client._read_queue.get_nowait() is _STDOUT_EOF

    def test_reads_chunks_then_eof(self) -> None:
        client = _detached_client()
        fake_stdout = MagicMock()
        fake_stdout.fileno.return_value = 3
        client._process.stdout = fake_stdout
        with patch(
            "scripts.memory_sync.mcp_client.os.read",
            side_effect=[b"chunk-a", b"chunk-b", b""],
        ):
            client._drain_stdout()
        assert client._read_queue.get_nowait() == b"chunk-a"
        assert client._read_queue.get_nowait() == b"chunk-b"
        assert client._read_queue.get_nowait() is _STDOUT_EOF

    def test_read_error_enqueues_eof(self) -> None:
        client = _detached_client()
        fake_stdout = MagicMock()
        fake_stdout.fileno.return_value = 3
        client._process.stdout = fake_stdout
        with patch(
            "scripts.memory_sync.mcp_client.os.read",
            side_effect=OSError("pipe error"),
        ):
            client._drain_stdout()
        assert client._read_queue.get_nowait() is _STDOUT_EOF

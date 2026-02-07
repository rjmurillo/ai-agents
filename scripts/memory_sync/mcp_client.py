"""MCP stdio JSON-RPC client for Forgetful.

Spawns `uvx forgetful-ai` as a subprocess and communicates
via JSON-RPC 2.0 over stdin/stdout.

See: ADR-037, Issue #747
"""

from __future__ import annotations

import json
import logging
import os
import select
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)

FORGETFUL_DB_PATH = Path.home() / ".local" / "share" / "forgetful" / "forgetful.db"
DEFAULT_TIMEOUT = 10.0
MCP_COMMAND = ["uvx", "forgetful-ai"]


class McpError(Exception):
    """Error from MCP protocol communication."""


class McpClient:
    """JSON-RPC 2.0 client over MCP stdio transport.

    Spawns ``uvx forgetful-ai`` as a subprocess and sends
    JSON-RPC requests over stdin, reading responses from stdout.

    Usage::

        with McpClient.create() as client:
            result = client.call_tool("create_memory", {"title": "..."})
    """

    def __init__(
        self,
        process: subprocess.Popen[bytes],
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._process = process
        self._timeout = timeout
        self._request_id = 0
        self._stderr_lines: list[str] = []
        self._stderr_thread = threading.Thread(
            target=self._drain_stderr, daemon=True
        )
        self._stderr_thread.start()

    @classmethod
    def create(
        cls,
        command: list[str] | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> McpClient:
        """Create and initialize an MCP client.

        Spawns the subprocess and performs the MCP handshake
        (initialize request + initialized notification).

        Raises:
            McpError: If the subprocess fails to start or handshake fails.
            FileNotFoundError: If the command is not found.
        """
        cmd = command or MCP_COMMAND
        _logger.debug("Spawning MCP server: %s", cmd)
        try:
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise McpError(f"Command not found: {cmd[0]}") from exc

        client = cls(process, timeout=timeout)
        try:
            client._handshake()
        except Exception:
            client.close()
            raise
        return client

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Call a Forgetful tool via MCP tools/call.

        Args:
            name: Tool name (e.g. "create_memory").
            arguments: Tool arguments dict.

        Returns:
            The tool result content.

        Raises:
            McpError: On protocol or tool errors.
        """
        response = self._send_request("tools/call", {
            "name": f"execute_forgetful_tool-forgetful-tool-{name}",
            "arguments": {"tool_name": name, "arguments": arguments},
        })
        if "error" in response:
            raise McpError(
                f"Tool error: {response['error'].get('message', response['error'])}"
            )
        result = response.get("result", {})
        if result.get("isError"):
            content = result.get("content", [{}])
            text = content[0].get("text", "Unknown error") if content else "Unknown error"
            raise McpError(f"Tool execution error: {text}")
        return result

    def close(self) -> None:
        """Terminate the MCP subprocess."""
        if self._process.stdin:
            try:
                self._process.stdin.close()
            except OSError:
                pass
        if self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
        _logger.debug("MCP server closed")

    def __enter__(self) -> McpClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _handshake(self) -> None:
        """Perform MCP initialize handshake."""
        response = self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "memory-sync", "version": "0.1.0"},
        })
        if "error" in response:
            raise McpError(
                f"Handshake failed: {response['error'].get('message', response['error'])}"
            )
        _logger.debug("MCP handshake complete: %s", response.get("result", {}))
        self._send_notification("notifications/initialized", {})

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _send_request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send a JSON-RPC request and read the response."""
        request_id = self._next_id()
        message = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }
        self._write_message(message)
        return self._read_response(request_id)

    def _send_notification(self, method: str, params: dict[str, Any]) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        self._write_message(message)

    def _write_message(self, message: dict[str, Any]) -> None:
        """Write a JSON-RPC message to the subprocess stdin."""
        stdin = self._process.stdin
        if stdin is None:
            raise McpError("Process stdin is not available")
        data = json.dumps(message).encode("utf-8")
        header = f"Content-Length: {len(data)}\r\n\r\n".encode()
        try:
            stdin.write(header + data)
            stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise McpError(f"Failed to write to MCP server: {exc}") from exc

    def _read_response(self, expected_id: int) -> dict[str, Any]:
        """Read a JSON-RPC response matching the expected ID.

        Uses os.read on the raw file descriptor with select for timeouts.
        This avoids the buffered I/O + select incompatibility where
        BufferedReader consumes data from the fd into its internal buffer,
        making subsequent select calls miss available data.
        """
        stdout = self._process.stdout
        if stdout is None:
            raise McpError("Process stdout is not available")
        fd = stdout.fileno()

        buf = b""
        while True:
            header_end = buf.find(b"\r\n\r\n")
            while header_end == -1:
                buf += self._read_bytes(fd)
                header_end = buf.find(b"\r\n\r\n")

            header = buf[:header_end + 4].decode("utf-8")
            content_length = self._parse_content_length(header)
            body_start = header_end + 4

            while len(buf) - body_start < content_length:
                buf += self._read_bytes(fd)

            body = buf[body_start:body_start + content_length]
            buf = buf[body_start + content_length:]

            response: dict[str, Any] = json.loads(body.decode("utf-8"))

            if "id" not in response:
                _logger.debug("Skipping notification: %s", response.get("method"))
                continue

            if response["id"] != expected_id:
                _logger.warning(
                    "Unexpected response id %s, expected %s",
                    response["id"],
                    expected_id,
                )
                continue

            return response

    def _read_bytes(self, fd: int) -> bytes:
        """Read available bytes from fd with timeout."""
        if sys.platform != "win32":
            ready, _, _ = select.select([fd], [], [], self._timeout)
            if not ready:
                raise McpError(
                    f"Timeout waiting for response (>{self._timeout}s)"
                )
        chunk = os.read(fd, 4096)
        if not chunk:
            stderr_output = "\n".join(self._stderr_lines[-10:])
            raise McpError(
                f"MCP server closed stdout. stderr: {stderr_output}"
            )
        return chunk

    @staticmethod
    def _parse_content_length(header: str) -> int:
        """Parse Content-Length from HTTP-style header."""
        for line in header.strip().split("\r\n"):
            if line.lower().startswith("content-length:"):
                return int(line.split(":", 1)[1].strip())
        raise McpError(f"Missing Content-Length in header: {header!r}")

    def _drain_stderr(self) -> None:
        """Read stderr in background thread to prevent blocking."""
        stderr = self._process.stderr
        if stderr is None:
            return
        try:
            for line in iter(stderr.readline, b""):
                decoded = line.decode("utf-8", errors="replace").rstrip()
                self._stderr_lines.append(decoded)
                _logger.debug("MCP stderr: %s", decoded)
        except (OSError, ValueError):
            pass

    @staticmethod
    def is_available() -> bool:
        """Check if Forgetful is available (DB file exists)."""
        return FORGETFUL_DB_PATH.exists()

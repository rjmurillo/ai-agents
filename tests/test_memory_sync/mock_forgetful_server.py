"""Mock Forgetful MCP server for testing.

Reads JSON-RPC 2.0 messages from stdin and returns canned responses
via stdout. Used by integration tests to validate the MCP client
without requiring a real Forgetful instance.

Usage::

    python -m tests.test_memory_sync.mock_forgetful_server

See: ADR-037, Issue #747
"""

from __future__ import annotations

import json
import sys

# In-memory store for testing
_memories: dict[int, dict] = {}
_next_id = 1


def main() -> None:
    """Run the mock MCP server."""
    while True:
        try:
            header = _read_header()
            if header is None:
                break
            content_length = _parse_content_length(header)
            body = sys.stdin.buffer.read(content_length)
            if len(body) < content_length:
                break
            message = json.loads(body.decode("utf-8"))
            response = _handle_message(message)
            if response is not None:
                _write_response(response)
        except (json.JSONDecodeError, KeyboardInterrupt):
            break


def _read_header() -> str | None:
    """Read HTTP-style header from stdin."""
    header = b""
    while True:
        byte = sys.stdin.buffer.read(1)
        if not byte:
            return None
        header += byte
        if header.endswith(b"\r\n\r\n"):
            return header.decode("utf-8")


def _parse_content_length(header: str) -> int:
    """Extract Content-Length from header."""
    for line in header.strip().split("\r\n"):
        if line.lower().startswith("content-length:"):
            return int(line.split(":", 1)[1].strip())
    raise ValueError(f"No Content-Length in header: {header!r}")


def _handle_message(message: dict) -> dict | None:
    """Route a JSON-RPC message to the appropriate handler."""
    method = message.get("method", "")
    msg_id = message.get("id")

    # Notifications have no id, no response expected
    if msg_id is None:
        return None

    if method == "initialize":
        return _response(msg_id, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "mock-forgetful", "version": "0.0.1"},
        })

    if method == "tools/call":
        return _handle_tool_call(msg_id, message.get("params", {}))

    return _error_response(msg_id, -32601, f"Unknown method: {method}")


def _handle_tool_call(msg_id: int, params: dict) -> dict:
    """Handle a tools/call request."""
    global _next_id
    arguments = params.get("arguments", {})
    tool_name = arguments.get("tool_name", "")
    tool_args = arguments.get("arguments", {})

    if tool_name == "create_memory":
        memory_id = _next_id
        _next_id += 1
        _memories[memory_id] = {
            "id": memory_id,
            "title": tool_args.get("title", ""),
            "content": tool_args.get("content", ""),
        }
        return _response(msg_id, {
            "content": [{"type": "text", "text": json.dumps({"id": memory_id})}],
        })

    if tool_name == "update_memory":
        memory_id = tool_args.get("memory_id")
        if memory_id in _memories:
            _memories[memory_id].update({
                k: v for k, v in tool_args.items() if k != "memory_id"
            })
        return _response(msg_id, {
            "content": [{"type": "text", "text": json.dumps({"ok": True})}],
        })

    if tool_name == "mark_memory_obsolete":
        memory_id = tool_args.get("memory_id")
        if memory_id in _memories:
            del _memories[memory_id]
        return _response(msg_id, {
            "content": [{"type": "text", "text": json.dumps({"ok": True})}],
        })

    if tool_name == "query_memory":
        return _response(msg_id, {
            "content": [{"type": "text", "text": json.dumps({"results": []})}],
        })

    return _response(msg_id, {
        "isError": True,
        "content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}],
    })


def _response(msg_id: int, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _error_response(msg_id: int, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def _write_response(response: dict) -> None:
    """Write a JSON-RPC response to stdout."""
    data = json.dumps(response).encode("utf-8")
    header = f"Content-Length: {len(data)}\r\n\r\n".encode()
    sys.stdout.buffer.write(header + data)
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()

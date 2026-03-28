"""Thin wrapper around ``npx mcporter call`` for direct MCP tool invocation.

Replaces hand-rolled JSON-RPC clients with a single subprocess call to MCPorter,
which handles server lifecycle, protocol negotiation, and argument serialization.

Usage::

    from scripts.mcp_cli import mcp_call

    # Call a Serena memory tool
    result = mcp_call("serena", "list_memories")

    # Call with arguments
    result = mcp_call("serena", "read_memory", name="my-memory")

    # Call a Forgetful tool
    result = mcp_call("forgetful", "discover_forgetful_tools")

See: Issue #1484
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from pathlib import Path

_logger = logging.getLogger(__name__)

_MCPORTER_CMD = "mcporter"
_NPX_CMD = "npx"
_DEFAULT_TIMEOUT = 30

# Allow-list: any content except NUL bytes.  Realistic MCP payloads include
# newlines, Unicode, punctuation, and escaped JSON.  Argument-injection is
# blocked separately by the dash-prefix check in _validate_arg_value.
_SAFE_VALUE_PATTERN = re.compile(r"^[^\x00]+$", re.DOTALL)


class McpCliError(Exception):
    """Raised when an mcporter call fails."""


def _validate_arg_value(key: str, value: str) -> None:
    """Validate a CLI argument value against injection attacks.

    Raises:
        McpCliError: If the value starts with a dash or contains unsafe characters.
    """
    str_value = str(value)
    if str_value.startswith("-"):
        raise McpCliError(
            f"Argument value for '{key}' must not start with '-': {str_value}"
        )
    if str_value and not _SAFE_VALUE_PATTERN.match(str_value):
        raise McpCliError(
            f"Argument value for '{key}' contains unsafe characters: {str_value}"
        )


def _find_mcporter() -> list[str]:
    """Return the command prefix for invoking mcporter.

    Prefers a locally installed ``mcporter`` binary. Falls back to ``npx mcporter``.

    Raises:
        McpCliError: If neither mcporter nor npx is available.
    """
    if shutil.which(_MCPORTER_CMD):
        return [_MCPORTER_CMD]
    if shutil.which(_NPX_CMD):
        return [_NPX_CMD, _MCPORTER_CMD]
    raise McpCliError(
        "mcporter not found. Install via: npm install -g mcporter"
    )


def mcp_call(
    server: str,
    tool: str,
    *,
    timeout: int = _DEFAULT_TIMEOUT,
    cwd: Path | str | None = None,
    **kwargs: str | int | float | bool | dict[str, object] | list[object],
) -> dict[str, object]:
    """Call an MCP tool via mcporter.

    Args:
        server: MCP server name (e.g. "serena", "forgetful", "deepwiki").
        tool: Tool name on that server (e.g. "list_memories", "read_memory").
        timeout: Subprocess timeout in seconds.
        cwd: Working directory for mcporter (affects server config discovery).
        **kwargs: Tool arguments as key=value pairs.

    Returns:
        Parsed JSON result from the tool.

    Raises:
        McpCliError: On subprocess failure, timeout, or JSON parse error.
    """
    cmd = _find_mcporter()
    selector = f"{server}.{tool}"
    cmd.extend(["call", selector, "--output", "json/raw"])

    for key, value in kwargs.items():
        if isinstance(value, bool):
            serialized = str(value).lower()
        elif isinstance(value, (dict, list)):
            serialized = json.dumps(value)
        else:
            serialized = str(value)
        _validate_arg_value(key, serialized)
        cmd.append(f"{key}:{serialized}")

    _logger.debug(
        "mcporter call: selector=%s arg_keys=%s",
        selector,
        sorted(kwargs),
    )

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(cwd) if cwd else None,
        )
    except subprocess.TimeoutExpired as exc:
        raise McpCliError(
            f"mcporter call timed out after {timeout}s: {selector}"
        ) from exc
    except FileNotFoundError as exc:
        raise McpCliError(f"Command not found: {cmd[0]}") from exc

    if result.returncode != 0:
        raise McpCliError(
            f"mcporter call failed (exit {result.returncode}): "
            f"{selector}\n{result.stderr.strip()}"
        )

    stdout = result.stdout.strip()
    if not stdout:
        return {}

    try:
        parsed: dict[str, object] = json.loads(stdout)
        return parsed
    except json.JSONDecodeError:
        return {"raw": stdout}


def mcp_list_tools(
    server: str,
    *,
    timeout: int = _DEFAULT_TIMEOUT,
    cwd: Path | str | None = None,
) -> list[dict[str, str]]:
    """List available tools on an MCP server.

    Args:
        server: MCP server name.
        timeout: Subprocess timeout in seconds.
        cwd: Working directory for mcporter.

    Returns:
        List of tool dicts with "name" and "description" keys.

    Raises:
        McpCliError: On subprocess failure.
    """
    cmd = _find_mcporter()
    cmd.extend(["list", server, "--schema", "--json"])

    _logger.debug("mcporter list: %s", " ".join(cmd))

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(cwd) if cwd else None,
        )
    except subprocess.TimeoutExpired as exc:
        raise McpCliError(
            f"mcporter list timed out after {timeout}s: {server}"
        ) from exc

    if result.returncode != 0:
        raise McpCliError(
            f"mcporter list failed (exit {result.returncode}): {server}"
        )

    stdout = result.stdout.strip()
    if not stdout:
        return []

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return []

    servers: list[dict[str, object]] = data.get("servers", [])
    for srv in servers:
        if srv.get("name") == server:
            raw_tools: object = srv.get("tools", [])
            if not isinstance(raw_tools, list):
                return []
            return [t for t in raw_tools if isinstance(t, dict)]
    return []

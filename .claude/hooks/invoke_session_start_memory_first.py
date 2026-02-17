#!/usr/bin/env python3
"""Enforce ADR-007 Memory-First Architecture at session start.

Claude Code hook that injects memory-first requirements into the session context.
Outputs blocking gate requirements that Claude receives before processing any user prompts.
Reads MCP configuration but does not verify server connectivity.
Part of the ADR-007 enforcement mechanism (Issue #729).

Hook Type: SessionStart
Exit Codes:
    0 = Success, stdout added to Claude's context
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlparse

# Default Forgetful MCP configuration
FORGETFUL_HOST = "localhost"
FORGETFUL_PORT = 8020


def read_forgetful_config(mcp_config_path: str) -> tuple[str, int]:
    """Read Forgetful MCP connection info from .mcp.json.

    Returns (host, port) tuple. Falls back to defaults on any error.
    """
    host = FORGETFUL_HOST
    port = FORGETFUL_PORT

    config_path = Path(mcp_config_path)
    if not config_path.exists():
        return host, port

    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        servers = config.get("mcpServers", {})
        forgetful = servers.get("forgetful", {})
        url_str = forgetful.get("url", "")
        if url_str:
            parsed = urlparse(url_str)
            if parsed.hostname:
                host = parsed.hostname
            if parsed.port:
                port = parsed.port
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        print(
            f"Failed to parse MCP config from {mcp_config_path}: {exc}. Using defaults.",
            file=sys.stderr,
        )

    return host, port


def main() -> int:
    """Main hook entry point. Returns exit code."""
    # Determine .mcp.json path relative to this script
    script_dir = Path(__file__).resolve().parent
    mcp_config_path = str(script_dir / ".." / ".mcp.json")

    _host, _port = read_forgetful_config(mcp_config_path)

    # TCP connection check disabled to prevent issues in async handling.
    # This is informational only, so disabling doesn't affect functionality.
    forgetful_status = "Forgetful: unavailable (use Serena)"

    agents_ref = ""
    project_root = script_dir.parent.parent
    if (project_root / "AGENTS.md").is_file():
        agents_ref = " Protocol: AGENTS.md > Session Protocol Gates."
    print(f"ADR-007 active. {forgetful_status}.{agents_ref}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

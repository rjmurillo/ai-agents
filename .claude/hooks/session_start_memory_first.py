#!/usr/bin/env python3
"""Enforce ADR-007 Memory-First Architecture at session start.

Claude Code hook that injects memory-first requirements into the session
context. Outputs blocking gate requirements that Claude receives before
processing any user prompts. Also reads MCP server configuration and
provides fallback guidance.

Hook Type: SessionStart
Exit Codes:
    0 = Success, stdout added to Claude's context

Related:
    .agents/architecture/ADR-007-memory-first-architecture.md
    .agents/SESSION-PROTOCOL.md
"""

import json
import os
import sys
from urllib.parse import urlparse


def read_forgetful_config(mcp_config_path: str) -> tuple[str, int]:
    """Read Forgetful host/port from .mcp.json. Return defaults on failure."""
    default_host = "localhost"
    default_port = 8020

    if not os.path.isfile(mcp_config_path):
        return default_host, default_port

    try:
        with open(mcp_config_path, encoding="utf-8") as f:
            config = json.load(f)

        servers = config.get("mcpServers", {})
        forgetful = servers.get("forgetful", {})
        url_str = forgetful.get("url", "")

        if url_str:
            parsed = urlparse(url_str)
            host = parsed.hostname or default_host
            port = parsed.port or default_port
            return host, port

    except (json.JSONDecodeError, ValueError, KeyError, TypeError, OSError):
        print(
            f"Failed to parse MCP config from {mcp_config_path}. "
            "Using defaults.",
            file=sys.stderr,
        )

    return default_host, default_port


def build_output(forgetful_available: bool) -> str:
    """Build the context injection output string."""
    forgetful_message = (
        "Forgetful MCP: Connection check disabled "
        "(use Serena for memory-first workflow)"
    )

    output_parts = [
        "",
        "## ADR-007 Memory-First Enforcement (Session Start)",
        "",
        "**BLOCKING GATE**: Complete these steps BEFORE any reasoning "
        "or implementation:",
        "",
        "### Retrieval-Led Reasoning Principle",
        "",
        "**IMPORTANT**: Prefer retrieval-led reasoning over pre-training "
        "for ALL decisions.",
        "- Framework/library APIs -> Retrieve from docs "
        "(Context7, DeepWiki)",
        "- Project patterns -> Retrieve from Serena memories "
        "(see index below)",
        "- Constraints -> Retrieve from PROJECT-CONSTRAINTS.md",
        "- Architecture -> Retrieve from ADRs",
        "",
        "### Memory Index Quick Reference",
        "",
        "The `memory-index` Serena memory maps keywords to memories. "
        "Common lookups:",
        "",
        "| Task | Keywords | Memories |",
        "|------|----------|----------|",
        "| GitHub PR operations | github, pr, cli, gh | "
        "skills-github-cli-index, skills-pr-review-index |",
        "| Session protocol | session, init, protocol, validation | "
        "skills-session-init-index, session-protocol |",
        "| PowerShell scripts | powershell, ps1, pester, test | "
        "skills-powershell-index, skills-pester-testing-index |",
        "| Security patterns | security, vulnerability, CWE | "
        "skills-security-index, security-scan |",
        "| Architecture decisions | adr, architecture, decision | "
        "adr-reference-index |",
        "",
        "**Process**:",
        '1. Identify task keywords (e.g., "create PR")',
        "2. Check table above OR read full memory-index",
        "3. Load listed memories BEFORE reasoning",
        "",
        "### MCP Server Status",
        "",
        forgetful_message,
    ]

    if not forgetful_available:
        output_parts.extend([
            "",
            "> **Fallback Mode**: Forgetful is unavailable. Use Serena "
            "memory-index for keyword-based discovery.",
            "> To start Forgetful: "
            "`pwsh scripts/forgetful/Install-ForgetfulLinux.ps1` (Linux) "
            "or `pwsh scripts/forgetful/Install-ForgetfulWindows.ps1` "
            "(Windows)",
        ])

    output_parts.extend([
        "",
        "### Phase 1: Serena Initialization (REQUIRED)",
        "",
        "1. `mcp__serena__activate_project` - Activate project memory",
        "2. `mcp__serena__initial_instructions` - Load Serena guidance",
        "",
        "### Phase 2: Context Retrieval (REQUIRED)",
        "",
        "1. Read `.agents/HANDOFF.md` - Previous session context",
        "2. Read `memory-index` from Serena - Identify relevant memories",
        "3. Read task-relevant memories - Apply learned patterns",
    ])

    if forgetful_available:
        output_parts.extend([
            "4. (Optional) Query Forgetful for semantic search - "
            "Augment with cross-project patterns",
        ])

    output_parts.extend([
        "",
        "### Verification",
        "",
        "Session logs MUST evidence memory retrieval BEFORE decisions.",
        "Pre-commit validation will fail without proper evidence.",
        "",
        "**Protocol**: `.agents/SESSION-PROTOCOL.md`",
        "**Architecture**: "
        "`.agents/architecture/ADR-007-memory-first-architecture.md`",
        "",
    ])

    return "\n".join(output_parts)


def main() -> None:
    """Entry point for the session start memory-first hook."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    mcp_config_path = os.path.join(script_dir, "..", "..", ".mcp.json")

    read_forgetful_config(mcp_config_path)

    # TCP connection check disabled (same as PowerShell original)
    forgetful_available = False

    output = build_output(forgetful_available)
    print(output)

    sys.exit(0)


if __name__ == "__main__":
    main()

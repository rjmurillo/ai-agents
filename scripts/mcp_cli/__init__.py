"""MCP CLI wrapper using MCPorter.

Provides a thin Python interface around ``npx mcporter call`` for invoking
MCP tools from hooks and scripts without LLM inference overhead.

See: Issue #1484
"""

from scripts.mcp_cli.wrapper import McpCliError, mcp_call, mcp_list_tools

__all__ = ["McpCliError", "mcp_call", "mcp_list_tools"]

# Claude Code Instructions

Refer to [AGENTS.md](AGENTS.md) for complete project instructions.

This file exists for Claude Code's auto-load behavior. All canonical agent documentation is maintained in `AGENTS.md` to follow the DRY principle.

## Quick Reference

- **Agent invocation**: `Task(subagent_type="agent_name", prompt="...")`
- **Memory system**: `cloudmcp-manager` with Serena (tools prefixed with `mcp__serena__`: `write_memory`, `read_memory`, `list_memories`, `delete_memory`, `edit_memory`) fallback
- **Output directories**: `.agents/{analysis,architecture,planning,critique,qa,retrospective}/`

For full details on workflows, agent catalog, and best practices, see [AGENTS.md](AGENTS.md).

# Claude Code Instructions

## ⚠️ MANDATORY: Initialize Serena FIRST

**BEFORE doing ANY work**, you MUST call these tools in order:

```text
1. mcp__serena__activate_project  (with project path)
2. mcp__serena__initial_instructions
```

This is NON-NEGOTIABLE. Do not read files, do not search, do not answer questions until Serena is initialized. The Serena MCP provides critical project context, memories, and semantic code tools.

**Why this matters**: Without Serena initialization, you lack access to:

- Project memories containing past decisions and user preferences
- Semantic code navigation tools
- Historical context that prevents repeated mistakes

---

Refer to [AGENTS.md](AGENTS.md) for complete project instructions.

This file exists for Claude Code's auto-load behavior. All canonical agent documentation is maintained in `AGENTS.md` to follow the DRY principle.

## Quick Reference

- **Agent invocation**: `Task(subagent_type="agent_name", prompt="...")`
- **Memory system**: `cloudmcp-manager` with Serena (tools prefixed with `mcp__serena__`: `write_memory`, `read_memory`, `list_memories`, `delete_memory`, `edit_memory`) fallback
- **Output directories**: `.agents/{analysis,architecture,planning,critique,qa,retrospective}/`

For full details on workflows, agent catalog, and best practices, see [AGENTS.md](AGENTS.md).

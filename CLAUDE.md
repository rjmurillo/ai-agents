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

## ⚠️ MANDATORY: Session Protocol Applies ALWAYS

**The session protocol is NON-NEGOTIABLE, including for:**

- Resumed/continued conversations (context summarization does NOT exempt you)
- "Quick" tasks (even a 2-command task is still a session)
- Instructions saying "continue without asking questions" (that refers to task questions, not protocol)

**Minimum session checklist:**

```text
START (before any work):
□ Initialize Serena (see above)
□ Read .agents/HANDOFF.md for context

END (before session closes):
□ Update .agents/HANDOFF.md with what was done
□ Run: npx markdownlint-cli2 --fix "**/*.md"
□ Commit .agents/ files if changed
```

**Why this matters**: You are an expert amnesiac. Without reading HANDOFF.md, you will repeat work or contradict prior decisions. Without updating it, the next session starts blind.

See [AGENTS.md § Session Protocol](AGENTS.md#-mandatory-follow-session-workflow-protocol) for the full checklist.

---

Refer to [AGENTS.md](AGENTS.md) for complete project instructions.

This file exists for Claude Code's auto-load behavior. All canonical agent documentation is maintained in `AGENTS.md` to follow the DRY principle.

## Quick Reference

- **Agent invocation**: `Task(subagent_type="agent_name", prompt="...")`
- **Memory system**: `cloudmcp-manager` with Serena (tools prefixed with `mcp__serena__`: `write_memory`, `read_memory`, `list_memories`, `delete_memory`, `edit_memory`) fallback
- **Output directories**: `.agents/{analysis,architecture,planning,critique,qa,retrospective}/`

For full details on workflows, agent catalog, and best practices, see [AGENTS.md](AGENTS.md).

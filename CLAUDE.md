# Claude Code Instructions

> **IMPORTANT**: This file is intentionally minimal to reduce context window bloat. All detailed instructions are in [AGENTS.md](AGENTS.md).
>
> **Design Philosophy**: CLAUDE.md loads every session. We keep it under 100 lines following Anthropic's guidance.
> Critical context is auto-loaded via @imports. Use `/clear` between distinct tasks to prevent context pollution.

For non-trivial tasks, delegate to specialized agents using the Task tool:

- Use Task(subagent_type="orchestrator") for multi-step coordination
- Use Task(subagent_type="Explore") for codebase exploration
- Use specialized agents (implementer, architect, analyst, etc.) for focused work
- This manages context efficiently and provides specialized capabilities

@CRITICAL-CONTEXT.md

## Primary Reference

**Read AGENTS.md FIRST** for complete instructions:

- Session protocol (blocking gates)
- Agent catalog and workflows
- MCP server configuration
- GitHub workflow requirements
- Skill system
- Memory management
- Quality gates

## Critical Constraints (Quick Reference)

> **Full Details**: [.agents/governance/PROJECT-CONSTRAINTS.md](.agents/governance/PROJECT-CONSTRAINTS.md)

| Constraint | Source |
|------------|--------|
| PowerShell only (.ps1/.psm1) | ADR-005 |
| No raw gh when skill exists | usage-mandatory |
| No logic in workflow YAML | ADR-006 |
| Verify branch before git operations | SESSION-PROTOCOL |
| HANDOFF.md is read-only | ADR-014 |
| SHA-pinned actions in workflows | security-practices |
| ADR created/edited → adr-review skill MUST run | AGENTS.md |

## Session Protocol (Quick Reference)

> **Full Details**: [.agents/SESSION-PROTOCOL.md](.agents/SESSION-PROTOCOL.md)

**Session Start:**

1. Activate Serena: `mcp__serena__activate_project` → `mcp__serena__initial_instructions`
2. Read HANDOFF.md (read-only dashboard)
3. Create session log: `.agents/sessions/YYYY-MM-DD-session-NN.json`
4. Read usage-mandatory memory
5. Verify branch

**Session End:**

1. Complete session log
2. Update Serena memory
3. Run scoped markdownlint on changed files (ADR-043)
4. Route to qa agent (features only)
5. Commit all changes
6. Run `pwsh scripts/Validate-SessionJson.ps1 -SessionPath [log]`
   - If validation fails, use `/session-log-fixer` skill to fix issues

## Default Behavior

**For any non-trivial task:** `Task(subagent_type="orchestrator", prompt="...")`

## Key Documents

1. **AGENTS.md** - Primary reference (read first)
2. `.agents/SESSION-PROTOCOL.md` - Session requirements
3. `.agents/HANDOFF.md` - Project dashboard (read-only)
4. `.agents/governance/PROJECT-CONSTRAINTS.md` - Hard constraints
5. `.agents/AGENT-SYSTEM.md` - Full agent details
6. `.config/wt.toml` - Worktrunk configuration (see AGENTS.md for setup)

---

**For complete documentation, workflows, examples, and best practices, see [AGENTS.md](AGENTS.md).**

# GitHub Copilot Instructions

> **IMPORTANT**: This file is intentionally minimal to reduce context window bloat. All detailed instructions are in AGENTS.md.

## Primary Reference

**Read AGENTS.md FIRST** for complete instructions:

- Session protocol (blocking gates)
- Agent catalog and workflows
- Directory structure
- GitHub workflow requirements
- Skill system
- Memory management
- Quality gates

**Path**: `../AGENTS.md` (repository root)

## Serena MCP Initialization (BLOCKING)

If Serena MCP tools are available, you MUST call FIRST:

1. `serena/activate_project` (with project path)
2. `serena/initial_instructions`

**Check for**: Tools prefixed with `serena/` or `mcp__serena__`

**If unavailable**: Proceed without Serena, but reference AGENTS.md for full context

## Critical Constraints (Quick Reference)

> **Full Details**: `../.agents/governance/PROJECT-CONSTRAINTS.md`

| Constraint | Source |
|------------|--------|
| PowerShell only (.ps1/.psm1) | ADR-005 |
| No raw gh when skill exists | usage-mandatory |
| No logic in workflow YAML | ADR-006 |
| Verify branch before git operations | SESSION-PROTOCOL |
| HANDOFF.md is read-only | ADR-014 |

## Session Protocol (Quick Reference)

> **Full Details**: `../.agents/SESSION-PROTOCOL.md`

**Session Start:**

1. Initialize Serena (if available)
2. Read HANDOFF.md (read-only dashboard)
3. Create session log: `.agents/sessions/YYYY-MM-DD-session-NN.md`
4. Verify branch: `git branch --show-current`

**Session End:**

1. Complete session log
2. Update Serena memory (if available)
3. Run `npx markdownlint-cli2 --fix "**/*.md"`
4. Commit all changes
5. Run `pwsh scripts/Validate-Session.ps1 -SessionLogPath [log]`

## Key Documents

1. **AGENTS.md** - Primary reference (read first)
2. `.agents/SESSION-PROTOCOL.md` - Session requirements
3. `.agents/HANDOFF.md` - Project dashboard (read-only)
4. `.agents/governance/PROJECT-CONSTRAINTS.md` - Hard constraints
5. `.agents/AGENT-SYSTEM.md` - Full agent details

---

**For complete documentation, workflows, examples, and best practices, see [AGENTS.md](../AGENTS.md).**

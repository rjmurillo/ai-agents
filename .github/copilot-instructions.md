# GitHub Copilot Instructions

> **IMPORTANT**: File minimal. Cut context bloat. Detail in AGENTS.md.

## Global Behavioral Steering

For cross-harness behavior rules, local Copilot sessions can also read
`~/.copilot/copilot-instructions.md`. AGENTS.md remains this repository's
primary reference for ai-agents-specific rules.

Copilot Cloud cannot read local dotfiles. If you have access to Richard's
dotfiles repo, use the branch-agnostic fallback link in Key Documents.

## Agent Delegation for Complex Tasks

Multi-step tasks, specialized expertise, big context → prefer delegation via `#runSubagent` rather than inline handling.

| When to Delegate | Agent | Example Prompt |
|------------------|-------|----------------|
| Multi-step coordination | `orchestrator` | "Implement OAuth 2.0 with tests and docs" |
| Codebase exploration | `analyst` | "Investigate why cache invalidation fails" |
| Architecture decisions | `architect` | "Design the event sourcing pattern for orders" |
| Implementation work | `implementer` | "Implement the UserService per approved plan" |
| Plan validation | `critic` | "Review the migration plan for gaps" |
| Security review | `security` | "Assess auth flow for vulnerabilities" |

**Why delegate:**

- Context window efficient (agent start fresh)
- Specialized prompts + constraints
- Focused results to synthesize

**Delegation pattern:**

```text
#runSubagent orchestrator "Help me implement feature X end-to-end"
```

**Keep inline:** Simple single-file edits, quick lookups. No specialized reasoning needed.

## Primary Reference

**Read AGENTS.md FIRST** for full instructions:

- Session protocol (blocking gates)
- Agent catalog + workflows
- Directory structure
- GitHub workflow requirements
- Skill system
- Memory management
- Quality gates

**Path**: `../AGENTS.md` (repo root)

## Serena MCP Initialization (BLOCKING)

Serena MCP tools available → MUST call FIRST:

1. `serena/activate_project` (with project path)
2. `serena/initial_instructions`

**Check for**: Tools prefixed `serena/` or `mcp__serena__`

**If unavailable**: Skip Serena. Reference AGENTS.md for context.

## Critical Constraints (Quick Reference)

> **Full Details**: `../.agents/governance/PROJECT-CONSTRAINTS.md`

| Constraint | Source |
|------------|--------|
| Python first (.py preferred, PowerShell grandfathered) | ADR-042 |
| No raw gh when skill exists | usage-mandatory |
| No logic in workflow YAML | ADR-006 |
| Verify branch before git operations | SESSION-PROTOCOL |
| HANDOFF.md is read-only | ADR-014 |

## Session Protocol (Quick Reference)

> **Full Details**: `../.agents/SESSION-PROTOCOL.md`

**Session Start:**

1. Init Serena (if available)
2. Read HANDOFF.md (read-only dashboard)
3. Create session log: `.agents/sessions/YYYY-MM-DD-session-NN.json`
4. Verify branch: `git branch --show-current`

**Session End:**

1. Complete session log
2. Update Serena memory (if available)
3. Run scoped markdownlint on changed files (ADR-043, see SESSION-PROTOCOL.md Phase 2)
4. Commit all changes
5. Run `python3 scripts/validate_session_json.py [log]`

## Key Documents

1. **AGENTS.md** - Primary reference (read first)
2. `.agents/SESSION-PROTOCOL.md` - Session requirements
3. `.agents/HANDOFF.md` - Project dashboard (read-only)
4. `.agents/governance/PROJECT-CONSTRAINTS.md` - Hard constraints
5. `.agents/AGENT-SYSTEM.md` - Full agent details
6. **Global behavioral steering**: `~/.copilot/copilot-instructions.md` (local) or [`rjmurillo/ubuntu-machine-config/app-configs/copilot/copilot-instructions.md`](https://github.com/rjmurillo/ubuntu-machine-config/blob/HEAD/app-configs/copilot/copilot-instructions.md) (Copilot Cloud; requires repo access)

---

**Full docs, workflows, examples, best practices → [AGENTS.md](../AGENTS.md).**

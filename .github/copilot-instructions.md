# GitHub Copilot Instructions

> **IMPORTANT**: File minimal. Cut context bloat. Detail in AGENTS.md.

## Global Behavioral Steering (read FIRST when running locally)

If you are running on a developer machine where Richard's
`ubuntu-machine-config` dotfiles are deployed, the global file at
`~/.copilot/copilot-instructions.md` carries the cross-harness behavioral
discipline that applies to every AI session (STOP TOKEN / last-sentence audit,
refuse-to-fabricate, audit-progress-claims, diagnose-before-fixing,
walk-or-don't-name, prohibited commands, AI-vernacular scrub list).

Those rules are sourced from Richard's `SOUL.md` and Anthropic's Claude
Fable 5 / Mythos 5 skill-bundle prompting guidance (the `shared/model-migration.md`
file inside the `/claude-api` skill, mirrored at
<https://github.com/Piebald-AI/claude-code-system-prompts/blob/main/system-prompts/skill-model-migration-guide.md>
because Anthropic does not web-publish it). Five of the six
Anthropic-recommended snippets confirm the same engineer-side discipline
`SOUL.md` codifies independently.

**On Copilot Cloud / web Copilot (no access to `~/.copilot/`)**: the relevant
behavioral rules are restated in
[`rjmurillo/ubuntu-machine-config/app-configs/copilot/copilot-instructions.md`](https://github.com/rjmurillo/ubuntu-machine-config/blob/master/app-configs/copilot/copilot-instructions.md).
Read it before this file when behavioral steering matters (long-running PR
reviews, autonomous workflows, anything where manufactured-trailing-offers
or fabricated-progress-claims would cost real time).

This project-level file below covers the **ai-agents repo-specific** rules
(agent delegation, session protocol, Serena MCP). Global rules take precedence
when there is a conflict.

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
6. **Global behavioral steering**: `~/.copilot/copilot-instructions.md` (local) or [`rjmurillo/ubuntu-machine-config/app-configs/copilot/copilot-instructions.md`](https://github.com/rjmurillo/ubuntu-machine-config/blob/master/app-configs/copilot/copilot-instructions.md) (Copilot Cloud)

---

**Full docs, workflows, examples, best practices → [AGENTS.md](../AGENTS.md).**

---
description: Auto-generate session documentation and sync workflow artifacts. Always the last command in a workflow sequence.
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash(git:*)
  - Glob
  - mcp__serena__*
model: sonnet
---

# /9-sync — Documentation Sync

Auto-generate session documentation and sync workflow artifacts.

## Purpose

Capture the work performed during the session into structured documentation. Eliminates manual session log writing by querying agent execution history and synthesizing a workflow summary.

## Actions

1. **Query agent history** — Retrieve all agent invocations from the current session
2. **Generate workflow diagram** — Sequence of agents invoked and their outcomes
3. **Extract decisions** — Document key decisions made during the session
4. **List artifacts** — Files created, modified, or deleted
5. **Append to session log** — Write structured entry to `.agents/sessions/`
6. **Update HANDOFF.md** — Persist cross-session context for the next session
7. **Suggest retrospective learnings** — Identify patterns worth capturing as memories

## MCP Integration

Maps to Agent Orchestration MCP (ADR-013):

- Read `agents://history` resource — retrieve session's agent invocations
- Read `session://state` resource (ADR-011) — get session metadata

**Fallback**: Parse session log and Git history to reconstruct workflow.

## Session Log Format

```markdown
## Session [YYYY-MM-DD-NN]

**Date**: YYYY-MM-DD
**Branch**: feature/xxx
**Duration**: ~Xh

### Workflow Sequence

/0-init → /1-plan → /2-impl → /3-qa → /9-sync

### Agents Invoked

| # | Agent | Duration | Result |
|---|-------|----------|--------|
| 1 | planner | ~5m | Plan created |
| 2 | implementer | ~15m | 4 files changed |
| 3 | qa | ~8m | All tests pass |

### Decisions Made

- [Decision 1]: Chose X over Y because Z
- [Decision 2]: ...

### Artifacts

- Created: `src/Services/AuthService.cs`
- Modified: `src/Controllers/UserController.cs`
- Created: `tests/AuthServiceTests.cs`

### Retrospective Suggestions

- Pattern: [description of reusable pattern]
- Learning: [insight to persist as memory]
```

## HANDOFF.md Update

Appends a summary block to `.agents/HANDOFF.md`:

```markdown
### [Date] — [Brief description]
- Completed: [what was done]
- In progress: [what remains]
- Blockers: [any blockers]
- Next steps: [recommended next actions]
```

## Output

- **Session log entry** — Appended to `.agents/sessions/`
- **HANDOFF.md update** — Cross-session context preserved
- **Workflow diagram** — Visual sequence of agent invocations
- **Retrospective suggestions** — Learnings to capture as memories

## Sequence Position

```text
/0-init → /1-plan → /2-impl → /3-qa → /4-security → ▶ /9-sync
```

This is **always the last command** in a workflow sequence.

## Dependencies

- Agent Orchestration MCP Phase 1 (ADR-013) — `agents://history` resource
- Session State MCP Phase 1 (ADR-011) — `session://state` resource

## Examples

```text
/9-sync
/9-sync Generate session documentation and update HANDOFF.md
```

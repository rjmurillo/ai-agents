---
description: Initialize a new workflow session with memory-first architecture (ADR-007). Always the first command in any workflow sequence.
model: sonnet
---

# /0-init - Session Initialization

Enforce session protocol gates and establish context before any work begins. Always the first command in any workflow sequence.

## Actions

1. **Activate project context** - Load initial instructions and project configuration
2. **Read HANDOFF.md** - Restore cross-session context from `.agents/HANDOFF.md`
3. **Query relevant memories** - Retrieve session history and learned patterns
4. **Create session log** - Initialize a new session log entry in `.agents/sessions/`
5. **Declare current branch** - Record the active Git branch and working state

## MCP Integration

Maps to Session State MCP `session_start()` (ADR-011). Fallback: execute steps manually using Serena memory tools and file reads.

## Gate Requirements

| Gate | Level | Validation |
|------|-------|------------|
| Project activation | BLOCKING | Tool output confirms activation |
| HANDOFF.md loaded | BLOCKING | Content present in context |
| Session log created | REQUIRED | File exists with correct template |
| Git state documented | RECOMMENDED | Branch and status recorded |

## Output

After successful initialization, report:

- Session ID and timestamp
- Loaded context summary (HANDOFF.md highlights)
- Current branch and Git state
- Ready state for next command (`/1-plan` or direct work)

## Sequence Position

```text
▶ /0-init → /1-plan → /2-impl → /3-qa → /4-security → /9-sync
```

## References

- ADR-007: Memory-First Architecture
- ADR-011: Session State MCP

## Examples

```text
/0-init
```

---
description: Session initialization - enforce ADR-007 memory-first architecture at session start. Loads project context, creates session log, and declares current branch via Invoke-Init.ps1.
argument-hint: [--session-number N] [--objective "text"]
allowed-tools:
  - Bash(pwsh .claude/skills/workflow/scripts/*)
  - Bash(pwsh .claude/skills/session-init/scripts/*)
  - Bash(git:*)
  - Bash(ls:*)
  - Read
model: sonnet
---

# /0-init — Session Initialization

Enforce ADR-007 memory-first architecture at session start.

## Context

Recent sessions: !`ls -1 .agents/sessions/ | tail -5`

Current branch: !`git branch --show-current`

## Invocation

```bash
pwsh .claude/skills/workflow/scripts/Invoke-Init.ps1 $ARGUMENTS
```

## What This Command Does

1. **Activate Serena project** — load project context (graceful fallback if MCP unavailable)
2. **Load initial instructions** — read AGENTS.md for current project rules
3. **Read HANDOFF.md** — load prior session context (read-only)
4. **Query relevant memories** — surface related memories (graceful fallback if MCP unavailable)
5. **Create session log** — via `New-SessionLog.ps1`
6. **Declare current branch** — output git branch for orientation
7. **Record evidence** — persist session state (graceful fallback if MCP unavailable)

## Arguments

- `--session-number N`: Optional. Auto-detected from `.agents/sessions/`.
- `--objective "text"`: Optional. Derived from branch name if omitted.

## Related

- Protocol: `.agents/SESSION-PROTOCOL.md`
- ADR-007: `.agents/architecture/ADR-007-memory-first-architecture.md`
- Session Init Skill: `.claude/skills/session-init/SKILL.md`

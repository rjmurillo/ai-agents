---
description: Create protocol-compliant session log with verification-based enforcement. Use when starting a new session to initialize session log with canonical template from SESSION-PROTOCOL.md.
argument-hint: [--session-number N] [--objective "text"]
allowed-tools:
  - Bash(pwsh .claude/skills/session-init/scripts/*)
  - Bash(git:*)
  - Bash(ls:*)
  - Read
model: sonnet
---

# Session Init Command

Create a verified session log using the canonical template from SESSION-PROTOCOL.md.

## Context

Current sessions: !`ls -1 .agents/sessions/ | tail -5`

## Invocation

Run the session-init automation script with arguments: $ARGUMENTS

```bash
pwsh .claude/skills/session-init/scripts/New-SessionLog.ps1 $ARGUMENTS
```

The script will:

1. **Auto-detect next session number** from `.agents/sessions/` (or use --session-number)
2. **Gather git state**: !`git branch --show-current`, !`git log --oneline -1`, !`git status --short`
3. **Read canonical template**: Extract from SESSION-PROTOCOL.md
4. **Populate and validate**: Create session log with immediate validation
5. **Report result**: PASS or actionable errors

## Arguments

- `--session-number N`: Optional. Auto-detected by default.
- `--objective "text"`: Optional. Prompts if not provided.

Validation cannot be skipped to ensure protocol compliance.

## Related

- Skill: `.claude/skills/session-init/SKILL.md`
- Protocol: `.agents/SESSION-PROTOCOL.md`

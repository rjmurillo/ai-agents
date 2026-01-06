---
description: Create protocol-compliant session log with verification-based enforcement. Use when starting a new session to initialize session log with canonical template from SESSION-PROTOCOL.md.
argument-hint: [--session-number N] [--objective "text"] [--skip-validation]
allowed-tools: [Bash(git:*), Bash(pwsh:*), Skill, Read, Write]
model: sonnet
---

# Session Init Command

Create protocol-compliant session log with verification-based enforcement.

## Usage

```bash
/session-init
/session-init --session-number 375 --objective "Implement feature X"
/session-init --skip-validation
```

## Arguments

| Argument | Description | Required |
|----------|-------------|----------|
| `--session-number N` | Session number (e.g., 375). If not provided, will prompt. | No |
| `--objective "text"` | Session objective. If not provided, will prompt. | No |
| `--skip-validation` | Skip validation after creating session log (testing only). | No |

## What This Does

Invokes the session-init skill which:

1. **Gathers inputs**: Session number, objective, git state (branch, commit, date)
2. **Reads canonical template**: Extracts from SESSION-PROTOCOL.md using regex
3. **Populates template**: Replaces placeholders with actual values
4. **Writes session log**: Creates `.agents/sessions/YYYY-MM-DD-session-NN.md`
5. **Validates immediately**: Runs Validate-SessionProtocol.ps1
6. **Reports result**: Shows success or validation errors

## Example

```bash
/session-init --session-number 375 --objective "Implement session-init skill"
```

Output:

```text
=== Session Log Creator ===

Phase 1: Gathering inputs...
  Repository: /home/user/ai-agents
  Branch: feat/session-init-skill
  Commit: abc1234 docs: add session-init skill
  Status: clean

  Session Number: 375
  Objective: Implement session-init skill

Phase 2: Reading canonical template...
  Template extracted successfully

Phase 3: Populating template...
  Placeholders replaced

Phase 4: Writing session log...
  File: .agents/sessions/2026-01-06-session-375.md

Phase 5: Validating session log...

=== SUCCESS ===

Session log created and validated
  File: .agents/sessions/2026-01-06-session-375.md
  Session: 375
  Branch: feat/session-init-skill
  Commit: abc1234

Next: Complete Session Start checklist in the session log
```

## Related

- Skill: `.claude/skills/session-init/SKILL.md`
- Protocol: `.agents/SESSION-PROTOCOL.md`
- Validation: `scripts/Validate-SessionProtocol.ps1`

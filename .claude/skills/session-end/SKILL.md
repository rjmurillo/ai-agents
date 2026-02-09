---
name: session-end
description: Validate and complete session logs before commit. Auto-populates session
  end evidence (commit SHA, lint results, memory updates) and runs validation. Use
  when finishing a session, before committing, or when session validation fails.
version: 1.0.0
license: MIT
model: claude-sonnet-4-5
metadata:
  domains:
    - session-protocol
    - compliance
    - automation
  type: completion
---

# Session End

Validate and complete session logs before commit. Complements `session-init` (which handles creation).

---

## Quick Start

### Automated (Recommended)

```powershell
pwsh .claude/skills/session-end/scripts/Complete-SessionLog.ps1
```

The script will:

1. Find the current session log automatically
2. Auto-populate session end evidence from git state
3. Run markdown lint on changed files
4. Validate with validate_session_json.py
5. Report pass/fail with actionable next steps

### Preview Changes First

```powershell
pwsh .claude/skills/session-end/scripts/Complete-SessionLog.ps1 -DryRun
```

---

## Triggers

| Phrase | Action |
|--------|--------|
| `/session-end` | Complete and validate current session log |
| `complete session` | Natural language activation |
| `finalize session` | Alternative trigger |
| `validate session end` | Alternative trigger |
| `finish session` | Alternative trigger |

| Input | Output | Quality Gate |
|-------|--------|--------------|
| Session log (auto-detected or specified) | Validated, completed session log | Exit code 0 from validation |

---

## When to Use

Use this skill when:

- Finishing a work session and ready to commit
- Session log needs end-of-session evidence populated
- Want to verify session compliance before pushing

Use [session-init](../session-init/SKILL.md) instead when:

- Starting a new session (creating a session log from scratch)

Use [session-log-fixer](../session-log-fixer/SKILL.md) instead when:

- CI already failed and you need to fix a specific validation error
- Working with a session log from a previous PR

---

## Process Overview

```text
User Request: /session-end
    |
    v
+---------------------------------------------+
| Phase 1: FIND SESSION LOG                    |
| - Auto-detect most recent .json in           |
|   .agents/sessions/                          |
| - Prefer today's sessions                    |
| - Accept explicit -SessionPath               |
+---------------------------------------------+
    |
    v
+---------------------------------------------+
| Phase 2: GATHER EVIDENCE                     |
| - Ending commit SHA (git rev-parse)          |
| - HANDOFF.md modification check              |
| - Serena memory update check                 |
| - Run markdown lint on changed files         |
| - Check for uncommitted changes              |
+---------------------------------------------+
    |
    v
+---------------------------------------------+
| Phase 3: UPDATE SESSION LOG                  |
| - Auto-populate evidence fields              |
| - Mark completed items                       |
| - Evaluate checklist completeness            |
| - Write updated JSON                         |
+---------------------------------------------+
    |
    v
+---------------------------------------------+
| Phase 4: VALIDATE                            |
| - Run validate_session_json.py               |
| - Update validationPassed field              |
| - Report pass/fail with details              |
+---------------------------------------------+
    |
    v
Completed Session Log (or actionable errors)
```

---

## What Gets Auto-Populated

| Field | Source | Level |
|-------|--------|-------|
| `endingCommit` | `git rev-parse --short HEAD` | Top-level |
| `handoffNotUpdated` | Check git diff for HANDOFF.md | MUST NOT |
| `serenaMemoryUpdated` | Check .serena/memories/ changes | MUST |
| `markdownLintRun` | Run markdownlint on changed .md files | MUST |
| `changesCommitted` | Check git status for uncommitted changes | MUST |
| `checklistComplete` | Evaluate all MUST items | MUST |
| `validationPassed` | Run validate_session_json.py | MUST |

### What You Must Provide Manually

- Serena memory updates (create/edit .serena/memories/ files before running)
- Commit your changes (run git commit before running)
- Work log entries in the session JSON

---

## Workflow

### Step 1: Complete Your Work

Before running this skill, ensure you have:

- Finished implementation tasks
- Updated Serena memories if applicable
- Staged and committed your changes

### Step 2: Run Session End

```powershell
# Auto-detect and complete
pwsh .claude/skills/session-end/scripts/Complete-SessionLog.ps1

# Or specify session explicitly
pwsh .claude/skills/session-end/scripts/Complete-SessionLog.ps1 -SessionPath ".agents/sessions/2026-02-07-session-05.json"

# Preview only
pwsh .claude/skills/session-end/scripts/Complete-SessionLog.ps1 -DryRun
```

### Step 3: Address Any Failures

If validation fails, the output shows exactly what is missing:

```text
[TODO] Serena memory not updated - update .serena/memories/ before completing
[TODO] Uncommitted changes exist - commit before completing
```

Fix the issues and re-run the skill.

### Step 4: Commit Final State

After the skill reports PASS, commit the updated session log:

```powershell
git add .agents/sessions/*.json
git commit -m "docs: complete session log"
```

---

## Verification Checklist

Before reporting success, the script verifies:

- [ ] Session log found and readable
- [ ] Valid JSON structure
- [ ] Ending commit SHA populated
- [ ] HANDOFF.md NOT modified
- [ ] Serena memory updated (or flagged)
- [ ] Markdown lint passed on changed files
- [ ] All changes committed (or flagged)
- [ ] Validation script passes (exit code 0)

---

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Skipping session-end before commit | Validation only catches errors at CI time | Run `/session-end` before every commit |
| Manually editing session end fields | Error-prone, misses evidence | Let the script auto-populate |
| Running without committing first | changesCommitted will fail | Commit work, then run session-end |
| Ignoring TODO warnings | Session will fail CI validation | Address each TODO before final commit |

---

## Example Output

**Success**:

```text
Auto-detected session log: .agents/sessions/2026-02-07-session-05.json

=== Session End Completion ===
File: .agents/sessions/2026-02-07-session-05.json

Running markdown lint...

--- Changes ---
  Set endingCommit: abc1234
  Confirmed HANDOFF.md not modified
  Confirmed Serena memory updated
  Markdown lint: 3 files linted
  All changes committed

Updated: .agents/sessions/2026-02-07-session-05.json

Running validation...

=== Session Validation ===
File: .agents/sessions/2026-02-07-session-05.json

[PASS] Session log is valid

[PASS] Session log completed and validated
```

**Failure**:

```text
=== Session End Completion ===

--- Changes ---
  Set endingCommit: abc1234
  Confirmed HANDOFF.md not modified
  [TODO] Serena memory not updated - update .serena/memories/ before completing
  Markdown lint: 2 files linted
  [TODO] Uncommitted changes exist - commit before completing

[FAIL] Session validation failed. Fix issues above and re-run.
```

---

## Scripts

| Script | Purpose | Exit Codes |
|--------|---------|------------|
| [Complete-SessionLog.ps1](scripts/Complete-SessionLog.ps1) | Auto-populate and validate session end | 0=success, 1=validation failed |

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `-SessionPath` | string | No | Path to session log. Auto-detects if omitted. |
| `-DryRun` | switch | No | Preview changes without writing to file. |

---

## Related Skills

| Skill | Relationship |
|-------|--------------|
| [session-init](../session-init/) | Creates session logs (this skill completes them) |
| [session-log-fixer](../session-log-fixer/) | Reactive fix after CI failure (this skill prevents the need) |
| [session](../session/) | Session management utilities |

---

## References

- [SESSION-PROTOCOL.md](../../../.agents/SESSION-PROTOCOL.md) - Session end requirements
- [validate_session_json.py](../../../scripts/validate_session_json.py) - Validation script
- [New-SessionLogJson.ps1](../session-init/scripts/New-SessionLogJson.ps1) - Session creation script

---

## Pattern: Shift-Left Validation

This skill follows the shift-left principle: catch errors at development time, not CI time.

| Aspect | Without Skill | With Skill |
|--------|---------------|------------|
| **When errors found** | CI pipeline (minutes later) | Before commit (immediately) |
| **Feedback loop** | Push, wait, read logs, fix, push again | Run script, see errors, fix, done |
| **Cost** | CI minutes + developer context switch | Seconds of local validation |
| **Reliability** | Same script as CI | Same script as CI |

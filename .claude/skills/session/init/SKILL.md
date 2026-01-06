---
name: session-init
description: Create protocol-compliant session logs with verification-based enforcement. Prevents recurring CI validation failures by reading canonical template from SESSION-PROTOCOL.md and validating immediately. Use when starting any new session.
license: MIT
metadata:
  version: 1.0.0
  model: claude-sonnet-4-5
  domains:
    - session-protocol
    - compliance
    - automation
  type: initialization
---

# Session Init

Create protocol-compliant session logs with verification-based enforcement.

---

## Quick Start

```text
/session-init
```

The skill will:

1. Prompt for session number and objective
2. Auto-detect git state (branch, commit, date)
3. Read canonical template from SESSION-PROTOCOL.md
4. Write session log with EXACT template format
5. Validate immediately with Validate-SessionProtocol.ps1

---

## Triggers

| Phrase | Action |
|--------|--------|
| `/session-init` | Create new session log |
| `create session log` | Natural language activation |
| `start new session` | Alternative trigger |
| `initialize session` | Alternative trigger |

| Input | Output | Quality Gate |
|-------|--------|--------------|
| Session number, objective | Validated session log file | Exit code 0 from validation |

---

## Why This Skill Exists

**Problem**: Every PR starts with malformed session logs that fail CI validation.

**Root Cause**: Agents generate session logs from LLM memory instead of copying the canonical template from SESSION-PROTOCOL.md. This causes variations like:

- Missing `(COMPLETE ALL before closing)` text in Session End header
- Wrong heading levels (`##` vs `###`)
- Missing sections

**Solution**: Verification-based enforcement following the proven Serena initialization pattern.

---

## Process Overview

```text
User Request: /session-init
    |
    v
+---------------------------------------------+
| Phase 1: GATHER INPUTS                      |
| - Prompt for session number                 |
| - Prompt for objective                      |
| - Auto-detect: date (YYYY-MM-DD)           |
| - Auto-detect: branch (git branch)         |
| - Auto-detect: commit (git log)            |
| - Auto-detect: git status                  |
+---------------------------------------------+
    |
    v
+---------------------------------------------+
| Phase 2: READ CANONICAL TEMPLATE            |
| - Read .agents/SESSION-PROTOCOL.md         |
| - Extract template (lines 494-612)         |
| - Preserve EXACT formatting                |
| - Critical: Keep "(COMPLETE ALL before     |
|   closing)" text in Session End header     |
+---------------------------------------------+
    |
    v
+---------------------------------------------+
| Phase 3: POPULATE TEMPLATE                  |
| - Replace NN with session number           |
| - Replace YYYY-MM-DD with date             |
| - Replace [branch name] with actual branch |
| - Replace [SHA] with commit hash           |
| - Replace [objective] with user input      |
| - Replace [clean/dirty] with git status    |
+---------------------------------------------+
    |
    v
+---------------------------------------------+
| Phase 4: WRITE SESSION LOG                  |
| - Write to .agents/sessions/YYYY-MM-DD-    |
|   session-NN.md                            |
| - Preserve all template sections           |
+---------------------------------------------+
    |
    v
+---------------------------------------------+
| Phase 5: IMMEDIATE VALIDATION               |
| - Run Validate-SessionProtocol.ps1         |
| - Report validation result                 |
| - If FAIL: show errors, allow retry       |
| - If PASS: confirm success                 |
+---------------------------------------------+
    |
    v
Protocol-Compliant Session Log
```

---

## Workflow

### Step 1: Gather Session Information

Prompt user for required inputs:

```text
What is the session number? (e.g., 375)
What is the session objective? (e.g., "Implement session-init skill")
```

Auto-detect from environment:

```bash
# Current date
date +%Y-%m-%d
# or PowerShell: Get-Date -Format "yyyy-MM-dd"

# Current branch
git branch --show-current

# Starting commit
git log --oneline -1

# Git status
git status --short
```

### Step 2: Read Canonical Template

**CRITICAL**: Read the template from `.agents/SESSION-PROTOCOL.md` lines 494-612.

**DO NOT** generate the template from memory. The template contains exact formatting that must be preserved:

- Header levels (`##` vs `###`)
- Table structure with pipe separators
- Checkbox format `[ ]`
- Comment blocks `<!-- -->`
- **CRITICAL**: `### Session End (COMPLETE ALL before closing)` header text

### Step 3: Populate Template Variables

Replace placeholders with actual values:

| Placeholder | Replace With |
|-------------|--------------|
| `NN` | Session number (e.g., 375) |
| `YYYY-MM-DD` | Current date |
| `[branch name]` | Git branch name |
| `[SHA]` | Starting commit hash |
| `[What this session aims to accomplish]` | User-provided objective |
| `[clean/dirty]` | Git status result |

Leave these unchanged:

- All checklist items `[ ]` (unchecked)
- Evidence columns with placeholder text
- Comment blocks

### Step 4: Write Session Log File

Construct filename: `.agents/sessions/YYYY-MM-DD-session-NN.md`

Example: `.agents/sessions/2026-01-05-session-375.md`

Write the populated template to this file.

### Step 5: Validate Immediately

Run validation script:

```powershell
pwsh scripts/Validate-SessionProtocol.ps1 -SessionPath ".agents/sessions/YYYY-MM-DD-session-NN.md" -Format markdown
```

Check exit code:

| Exit Code | Meaning | Action |
|-----------|---------|--------|
| 0 | PASS | Confirm success, agent proceeds |
| 1 | FAIL | Show errors, offer to retry |

---

## Verification Checklist

Before reporting success:

- [ ] Session number provided by user
- [ ] Objective provided by user
- [ ] Template read from SESSION-PROTOCOL.md (NOT generated from memory)
- [ ] All template sections present
- [ ] Session End header includes `(COMPLETE ALL before closing)`
- [ ] File written to correct path `.agents/sessions/YYYY-MM-DD-session-NN.md`
- [ ] Validation script executed
- [ ] Validation result is PASS (exit code 0)

---

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Generating template from memory | Will miss exact formatting | Read from SESSION-PROTOCOL.md |
| Skipping validation | Won't catch errors until CI | Validate immediately |
| Hardcoding template in skill | Template may change | Always read from canonical source |
| Pre-checking boxes | Defeats verification purpose | Leave all unchecked |
| Using `## Session End` | Missing required text | Use `### Session End (COMPLETE ALL before closing)` |

---

## Example Output

**Success**:

```text
Session log created and validated

  File: .agents/sessions/2026-01-05-session-375.md
  Validation: PASS
  Branch: feat/session-init
  Commit: abc1234

Next: Complete Session Start checklist in the session log
```

**Failure**:

```text
Session log created but validation FAILED

  File: .agents/sessions/2026-01-05-session-375.md
  Validation: FAIL
  Errors:
    - Missing Session End checklist header

Run: pwsh scripts/Validate-SessionProtocol.ps1 -SessionPath ".agents/sessions/2026-01-05-session-375.md" -Format markdown

Fix the issues and re-validate.
```

---

## Related Skills

| Skill | Relationship |
|-------|--------------|
| [log-fixer](../log-fixer/) | Reactive fix after failure (this skill prevents need) |
| [qa-eligibility](../qa-eligibility/) | QA eligibility checking (different purpose) |

---

## References

- [SESSION-PROTOCOL.md](.agents/SESSION-PROTOCOL.md) - Canonical template source (lines 494-612)
- [Validate-SessionProtocol.ps1](scripts/Validate-SessionProtocol.ps1) - Validation script
- [Template Extraction](references/template-extraction.md) - How to extract template
- [Validation Patterns](references/validation-patterns.md) - Common validation issues

---

## Pattern: Verification-Based Enforcement

This skill follows the same pattern as Serena initialization:

| Aspect | Serena Init | Session Init |
|--------|-------------|--------------|
| **Verification** | Tool output in transcript | Validation script exit code |
| **Feedback** | Immediate (tool response) | Immediate (validation output) |
| **Enforcement** | Cannot proceed without output | Cannot claim success without pass |
| **Compliance Rate** | 100% (never violated) | Target: 100% |

**Why it works**:

- Reads canonical template from file (single source of truth)
- Auto-populates git state (reduces manual errors)
- Validates immediately with same script as CI (instant feedback)
- Cannot skip validation (built into skill workflow)
- Provides actionable error messages if validation fails

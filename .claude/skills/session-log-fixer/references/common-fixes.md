# Common Fixes for Session Protocol Failures

Quick reference for diagnosing and fixing session protocol validation failures.

---

## Failure Types and Fixes

### 1. Missing Session Start Table

**CI Output:**

```text
MUST requirement(s) not met: Session Start table missing
```

**Fix:**
Copy the Session Start table from `references/template-sections.md`:

1. Read the session file
2. Insert the full Session Start table after `## Protocol Compliance` heading
3. Mark all steps as `[x]` with appropriate evidence

**Prevention:**
Use `session-init` skill to create compliant session logs.

---

### 2. Missing Session End Table

**CI Output:**

```text
MUST requirement(s) not met: Session End table missing
```

**Fix:**
Copy the Session End table from `references/template-sections.md`:

1. Read the session file
2. Insert the full Session End table before final commit section
3. Mark all steps as `[x]` with appropriate evidence

---

### 3. Unchecked MUST Requirement

**CI Output:**

```text
MUST requirement(s) not met: [Step name] is unchecked
```

**Fix:**

1. Locate the unchecked `[ ]` in the Protocol Compliance section
2. If requirement was completed: Mark `[x]` and add evidence
3. If requirement cannot be completed: Mark `[N/A]` with justification

**Example:**

```markdown
# Before (failing)
| MUST | Route to qa agent | [ ] | |

# After (passing) - if completed
| MUST | Route to qa agent | [x] | QA report: `.agents/qa/feature-qa.md` |

# After (passing) - if N/A with justification
| MUST | Route to qa agent | [N/A] | Documentation-only changes, no code |
```

---

### 4. Placeholder Evidence

**CI Output:**

```text
Evidence appears to be placeholder: "pending", "TBD", "_____"
```

**Fix:**

1. Find evidence columns with placeholder text
2. Replace with actual evidence

**Common replacements:**

| Placeholder | Replace With |
|-------------|--------------|
| `pending commit` | `Commit SHA: abc1234` (actual SHA) |
| `_____` | Actual value or `N/A - [reason]` |
| `TBD` | Actual value or `N/A - [reason]` |
| `[TODO]` | Actual value or `N/A - [reason]` |

---

### 5. Empty Evidence Column

**CI Output:**

```text
Evidence column empty for MUST requirement
```

**Fix:**

Add evidence text based on requirement type:

| Requirement | Evidence to Add |
|-------------|-----------------|
| Tool calls | "Tool output present" |
| File reads | "Content in context" |
| File creates | "This file exists" |
| Commits | "Commit SHA: [actual-sha]" |
| Linting | "Lint output clean" or "Output below" |

---

### 6. HANDOFF.md Modified

**CI Output:**

```text
HANDOFF.md was modified in this session (MUST NOT)
```

**Fix:**

1. Revert HANDOFF.md changes: `git checkout origin/main -- .agents/HANDOFF.md`
2. Move content to session log instead
3. Use Serena memory for cross-session context

**Why:**
HANDOFF.md is read-only per ADR-014. Session context goes to session logs.

---

### 7. Missing QA Report

**CI Output:**

```text
QA validation required but no report found
```

**Fix:**

1. Invoke QA agent: `Task(subagent_type="qa", prompt="Validate [feature]")`
2. Ensure report is created at `.agents/qa/`
3. Update Session End table with report path

**When N/A:**

- Documentation-only changes (no code, config, or tests)
- Mark as `[N/A]` with justification: "Documentation-only changes, no code"

---

## Diagnostic Commands

### Get Run Details

```powershell
& .claude/skills/session-log-fixer/scripts/diagnose.ps1 -RunId <run-id>
```

### Find Session Files for Branch

```powershell
git log --oneline --name-only -- ".agents/sessions/*.md" | Select-Object -First 20
```

### Check Current Session Protocol Structure

```powershell
Select-String -Path ".agents/sessions/*.md" -Pattern "MUST|SHOULD" | Group-Object Path
```

### Get Commit SHA for Evidence

```powershell
git log --oneline -1
# Returns: abc1234 commit message
```

---

## Fix Validation

After applying fixes, validate locally:

```powershell
# Quick check for MUST requirements
Select-String -Path ".agents/sessions/<file>.md" -Pattern "\| MUST.*\[ \]"
# Should return nothing if all MUST are checked

# Check for placeholders
Select-String -Path ".agents/sessions/<file>.md" -Pattern "pending|TBD|_____"
# Should return nothing if no placeholders
```

---

## Common Patterns by Session Type

### Feature Session

```markdown
| MUST | Route to qa agent | [x] | QA report: `.agents/qa/feature-name-qa.md` |
```

### Documentation Session

```markdown
| MUST | Route to qa agent | [N/A] | Documentation-only changes, no code modifications |
```

### Bug Fix Session

```markdown
| MUST | Route to qa agent | [x] | QA report: `.agents/qa/bugfix-issue-123-qa.md` |
```

### Refactoring Session

```markdown
| MUST | Route to qa agent | [x] | QA report: `.agents/qa/refactor-module-qa.md` |
```

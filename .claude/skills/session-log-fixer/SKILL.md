---
name: session-log-fixer
version: 2.0.0
model: claude-opus-4-5-20251101
description: Fix session protocol validation failures in GitHub Actions. Use when a PR fails with "Session protocol validation failed", "MUST requirement(s) not met", "NON_COMPLIANT" verdict, or "Aggregate Results" job failure in the Session Protocol Validation workflow. Analyzes CI logs, identifies non-compliant session files, determines missing requirements, and applies fixes.
license: MIT
metadata:
  domains: [ci, session-protocol, compliance, github-actions]
  type: diagnostic-fixer
  inputs: [run-id, pr-number]
  outputs: [fixed-session-file, commit]
---

# Session Log Fixer

Fix session protocol validation failures by analyzing CI logs and updating session files.

---

## Quick Start

Just tell me what failed:

```text
session-log-fixer: fix run 20548622722
```

or

```text
my PR failed session validation, please fix it
```

The skill will diagnose the failure, identify the non-compliant session file, and apply the necessary fixes.

---

## Triggers

- `session-log-fixer: {run-id}` - Fix specific workflow run
- `fix session validation for {PR/run}` - Natural language activation
- `session protocol failed` - When user reports a failure
- `NON_COMPLIANT session` - Direct from CI output
- `MUST requirement not met` - Direct from validation error

| Input | Output | Quality Gate |
|-------|--------|--------------|
| Run ID or PR number | Fixed session file with commit | CI re-run passes |

---

## Process Overview

```text
GitHub Actions Failure
        │
        ▼
┌───────────────────────────────────────────────────┐
│ Phase 1: DIAGNOSE                                 │
│ • Extract run ID from URL or PR                   │
│ • Run scripts/diagnose.ps1                        │
│ • Identify NON_COMPLIANT session files            │
│ • Parse specific missing requirements             │
├───────────────────────────────────────────────────┤
│ Phase 2: ANALYZE                                  │
│ • Read failing session file                       │
│ • Read SESSION-PROTOCOL.md template               │
│ • Diff current vs required structure              │
│ • Identify specific missing elements              │
├───────────────────────────────────────────────────┤
│ Phase 3: FIX                                      │
│ • Apply fixes based on diagnosis                  │
│ • Copy template sections exactly                  │
│ • Add evidence to verification steps              │
│ • Validate fix locally                            │
├───────────────────────────────────────────────────┤
│ Phase 4: VERIFY                                   │
│ • Commit and push changes                         │
│ • Monitor re-run status                           │
│ • Confirm COMPLIANT verdict                       │
└───────────────────────────────────────────────────┘
        │
        ▼
   Passing CI
```

---

## Commands

| Command | Action |
|---------|--------|
| `scripts/diagnose.ps1 -RunId {id}` | Diagnose specific run |
| `scripts/diagnose.ps1 -RunId {id} -Repo owner/repo` | Diagnose in different repo |

---

## Workflow

### Step 1: Diagnose

Extract the run ID from the GitHub Actions URL and run:

```powershell
& .claude/skills/session-log-fixer/scripts/diagnose.ps1 -RunId 20548622722
```

The script outputs:

- Run status and conclusion
- List of NON_COMPLIANT sessions
- Artifact contents with specific failures

### Step 2: Read Failing Session

Session files are at `.agents/sessions/YYYY-MM-DD-session-NN-*.md`

Identify what's missing by comparing against the Protocol Compliance section structure.

### Step 3: Read Protocol Template

Read `.agents/SESSION-PROTOCOL.md` to get the canonical checklist templates for:

- Session Start (COMPLETE ALL before work)
- Session End (COMPLETE ALL before closing)

**CRITICAL**: Copy the exact table structure. Do not recreate from memory.

### Step 4: Apply Fixes

Common fixes by failure type:

| Failure | Fix |
|---------|-----|
| Missing Session Start table | Copy template from SESSION-PROTOCOL.md |
| Missing Session End table | Copy template from SESSION-PROTOCOL.md |
| "Pending commit" | Replace with actual commit SHA from `gh pr view` |
| Empty evidence column | Add evidence text: "Tool output present", "Content in context", or "Commit SHA: abc1234" |
| Unchecked MUST | Mark `[x]` with evidence, or mark `[N/A]` with justification if truly not applicable |

**For SHOULD requirements**: Use `[N/A]` when not applicable. Use `[x]` with evidence when completed.

**For MUST requirements**: Never leave unchecked without explanation.

### Step 5: Commit

```powershell
git add ".agents/sessions/<session-file>.md"
git commit -m "docs: fix session protocol compliance for <session-name>

Add missing <what was missing> to satisfy session protocol validation."
git push
```

### Step 6: Verify

```powershell
gh run list --branch (git branch --show-current) --limit 3
gh run view <new-run-id> --json conclusion
```

If validation still fails, re-run `scripts/diagnose.ps1` with the new run ID.

---

## Verification Checklist

After applying fixes:

- [ ] Session file has Session Start Protocol table
- [ ] Session file has Session End Protocol table
- [ ] All MUST requirements are marked `[x]` with evidence
- [ ] No "pending" or placeholder text in evidence column
- [ ] Commit SHA is real (not "pending commit")
- [ ] Push succeeded without conflicts
- [ ] New workflow run triggered

---

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Recreating tables from memory | Will miss exact structure | Copy from SESSION-PROTOCOL.md |
| Marking MUST as N/A without justification | Validation will fail | Provide specific justification |
| Using placeholder evidence | Validators detect these | Use real evidence text |
| Fixing without diagnosis | May miss actual failure | Always run diagnose.ps1 first |
| Ignoring SHOULD requirements | Creates future tech debt | Mark appropriately |

---

## Extension Points

1. **Diagnosis scripts**: Add new scripts to `scripts/` for different failure types
2. **Fix templates**: Add common fix templates to `references/`
3. **Validation rules**: Extend diagnose.ps1 for new protocol requirements
4. **CI integration**: Add GitHub Action for auto-fix PRs

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `gh run view` fails | Verify run ID is correct, check authentication |
| No artifacts found | Run may have been deleted (>90 days), check logs directly |
| Fix didn't work | Re-run diagnose.ps1 on new run ID to see remaining issues |
| Wrong session file | Verify branch matches PR, check for multiple session files |

---

## Related Skills

| Skill | Relationship |
|-------|--------------|
| session-init | Prevents need for this skill by correct initialization |
| analyze | Deep investigation when fixes aren't obvious |

---

## References

- [Common Fixes](references/common-fixes.md) - Fix patterns for common failures
- [Template Sections](references/template-sections.md) - Copy-paste ready templates
- [CI Debugging Patterns](references/ci-debugging-patterns.md) - Advanced job-level diagnostics

---

## Changelog

### v2.0.0 (Current)

- Added complete frontmatter with metadata
- Added triggers section (5 phrases)
- Added Quick Start section
- Added Process Overview diagram
- Added Verification Checklist
- Added Anti-Patterns section
- Added Extension Points
- Added Troubleshooting section
- Fixed bash examples to PowerShell (ADR-005 compliance)
- Added references directory structure

### v1.0.0

- Initial release with diagnose.ps1 script
- Basic workflow documentation

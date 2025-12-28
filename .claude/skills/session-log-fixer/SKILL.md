---
name: session-log-fixer
description: Fix session protocol validation failures in GitHub Actions. Use when a PR fails with "Session protocol validation failed", "MUST requirement(s) not met", "NON_COMPLIANT" verdict, or "Aggregate Results" job failure in the Session Protocol Validation workflow. Analyzes CI logs, identifies non-compliant session files, determines missing requirements, and applies fixes.
---

# Session Log Fixer

Fix session protocol validation failures by analyzing CI logs and updating session files.

## Workflow

1. Run `scripts/diagnose.ps1 -RunId <run-id>` to identify failures
2. Read the failing session file
3. Read `.agents/SESSION-PROTOCOL.md` for template requirements
4. Apply fixes based on diagnosis
5. Commit and push

## Step 1: Diagnose

Extract the run ID from the GitHub Actions URL and run:

```powershell
scripts/diagnose.ps1 -RunId <run-id>
```

The script outputs:
- Run status and conclusion
- List of NON_COMPLIANT sessions
- Artifact contents with specific failures

## Step 2: Read Failing Session

Session files are at `.agents/sessions/YYYY-MM-DD-session-NN-*.md`

Identify what's missing by comparing against the Protocol Compliance section structure.

## Step 3: Read Protocol Template

Read `.agents/SESSION-PROTOCOL.md` to get the canonical checklist templates for:
- Session Start (COMPLETE ALL before work)
- Session End (COMPLETE ALL before closing)

Copy the exact table structure. Do not recreate from memory.

## Step 4: Apply Fixes

Common fixes by failure type:

| Failure | Fix |
|---------|-----|
| Missing Session Start table | Copy template from SESSION-PROTOCOL.md |
| Missing Session End table | Copy template from SESSION-PROTOCOL.md |
| "Pending commit" | Replace with actual commit SHA from `gh pr view` |
| Empty evidence column | Add evidence text: "Tool output present", "Content in context", or "Commit SHA: abc1234" |
| Unchecked MUST | Mark `[x]` with evidence, or mark `[N/A]` with justification if truly not applicable |

For SHOULD requirements: Use `[N/A]` when not applicable. Use `[x]` with evidence when completed.

For MUST requirements: Never leave unchecked without explanation.

## Step 5: Commit

```bash
git add .agents/sessions/<session-file>.md
git commit -m "docs: fix session protocol compliance for <session-name>

Add missing <what was missing> to satisfy session protocol validation."
git push
```

## Step 6: Verify

```bash
gh run list --branch <branch> --limit 3
gh run view <new-run-id> --json conclusion
```

If validation still fails, re-run `scripts/diagnose.ps1` with the new run ID.

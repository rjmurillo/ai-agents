# CodeQL Ruleset Configuration: Avoid code_scanning Rule Friction

**Date**: 2026-01-16
**Category**: CI Infrastructure
**Related**: ci-infrastructure-workflow-required-checks, codeql-verification-fixes

## Problem

PRs that don't touch scannable code (e.g., memory files, documentation, session logs) get blocked by GitHub's `code_scanning` ruleset rule even when CodeQL workflow passes.

**Symptoms**:
- PR shows "Code scanning is waiting for results from CodeQL"
- CodeQL workflow completes successfully with "Skip analysis (no scannable files changed)"
- Auto-merge enabled but PR remains BLOCKED
- `gh pr view` shows `mergeStateStatus: BLOCKED` despite `reviewDecision: APPROVED`

## Root Cause

Repository ruleset contains **both**:
1. `code_scanning` rule - requires SARIF results uploaded to GitHub
2. `required_status_checks` with "CodeQL" - requires workflow job to pass

These rules have different behaviors:

| Rule Type | What It Checks | Works When No Scannable Files? |
|-----------|----------------|-------------------------------|
| `required_status_checks` | Workflow job succeeds | Yes - job runs and passes |
| `code_scanning` | SARIF results exist in GitHub | No - nothing to upload |

When CodeQL workflow skips analysis (correct behavior), no SARIF is uploaded. The `code_scanning` rule waits indefinitely for results that will never arrive.

## Solution

**Remove the `code_scanning` rule from the ruleset.** The `required_status_checks` with CodeQL already ensures:
- CodeQL workflow runs on every PR
- Analysis executes when scannable files change
- Workflow reports success/failure status

**Fix via GitHub UI**:
1. Repository Settings → Rules → [ruleset name] → Edit
2. Remove "Require code scanning results" rule
3. Keep "Require status checks to pass" (includes CodeQL)

## Investigation Commands

```bash
# Check merge state
gh pr view <PR> --json mergeStateStatus,mergeable,reviewDecision

# List ruleset rules
gh api repos/OWNER/REPO/rulesets/<ID> --jq '.rules[].type'

# Check for code scanning results on branch
gh api "repos/OWNER/REPO/code-scanning/analyses?ref=refs/heads/<branch>"

# Verify overlapping rules
gh api repos/OWNER/REPO/rulesets/<ID> --jq '.rules[] | select(.type == "code_scanning" or .type == "required_status_checks")'
```

## Workaround (Temporary)

If you cannot modify the ruleset, trigger manual CodeQL analysis:

```bash
gh workflow run codeql-analysis.yml --ref <branch>
```

This forces full analysis regardless of file changes, uploading SARIF results.

## Key Insight

The `code_scanning` rule is designed for repositories where every PR touches scannable code. For repositories with mixed content (code + documentation/config), use `required_status_checks` alone.

## Related GitHub Docs

- upload-sarif action rejects empty SARIF files (runs array must have content)
- No built-in mechanism to satisfy `code_scanning` rule when analysis is skipped

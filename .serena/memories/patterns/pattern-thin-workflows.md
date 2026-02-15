# Pattern: Thin Workflows, Testable Modules

**Importance**: HIGH
**Date**: 2025-12-18
**Scope**: All GitHub Actions workflows

## Problem

GitHub Actions workflows cannot be tested locally. The OODA loop is:
1. Edit workflow YAML
2. Commit and push
3. Wait for CI to run (1-5 minutes)
4. Check results
5. If failed, repeat

This is **slow and painful** for debugging.

## Solution

**Keep workflows THIN**. Move ALL logic to testable PowerShell modules.

### Architecture

```text
Workflow (YAML)
  | (orchestrates only)
  v
PowerShell Module (.psm1 or Claude Skill)
  | (business logic)
  v
Pester Tests (.Tests.ps1)
  | (fast local feedback)
  v
```

### Rules

1. **Workflows are orchestrators ONLY**
   - Call PowerShell scripts
   - Pass parameters
   - Handle success/failure
   - NO business logic

2. **PowerShell modules contain logic**
   - `.github/scripts/*.psm1` - Workflow-specific logic
   - `.claude/skills/github/` - Reusable GitHub operations
   - Both are Pester-testable

3. **Fast OODA loop**
   - Edit module -> Run Pester -> Get feedback (seconds)
   - vs Edit workflow -> Push -> Wait -> Check (minutes)

## Location Hierarchy

### Workflow-Specific Logic
Location: `.github/scripts/*.psm1`

Examples:
- `AIReviewCommon.psm1` - AI workflow parsing, formatting, retry logic

### Reusable GitHub Operations
Location: `.claude/skills/github/scripts/`

Examples:
- `.claude/skills/github/scripts/pr/Post-PRCommentReply.ps1` - Post/reply to PR comments
- `.claude/skills/github/scripts/issue/Post-IssueComment.ps1` - Post idempotent issue comments
- `.claude/skills/github/scripts/issue/Set-IssueLabels.ps1` - Manage issue labels
- `.claude/skills/github/scripts/reactions/Add-CommentReaction.ps1` - Add reactions

### Why Separate Locations?

| Location | Scope | Reusability |
|----------|-------|-------------|
| `.github/scripts/` | This repo's workflows only | Low |
| `.claude/skills/github/` | Any agent/workflow | High |

## Examples

### BAD (Logic in workflow)

```yaml
- name: Parse verdict
  shell: bash
  run: |
    VERDICT=$(echo "$OUTPUT" | grep -oP '(?<=VERDICT:\s*)[A-Z_]+')
    if [ "$VERDICT" = "CRITICAL_FAIL" ]; then
      exit 1
    fi
```

**Problem**: Can't test grep logic locally. Must push to test.

### GOOD (Logic in module)

```yaml
- name: Parse verdict
  shell: pwsh
  run: |
    Import-Module .github/scripts/AIReviewCommon.psm1
    $verdict = Get-Verdict -Output $env:AI_OUTPUT
    if ($verdict -eq 'CRITICAL_FAIL') { exit 1 }
```

**Benefit**: `Get-Verdict` has Pester tests. Edit -> Test -> Deploy cycle is fast.

### GOOD (Using skill script directly)

```yaml
- name: Post PR Comment
  shell: pwsh
  env:
    GH_TOKEN: ${{ github.token }}
    PR_NUMBER: ${{ env.PR_NUMBER }}
    REPORT_FILE: ${{ steps.report.outputs.report_file }}
  run: |
    # Use GitHub skill script for idempotent comment posting
    # PRs are issues in GitHub API, so we use Post-IssueComment with marker
    & .claude/skills/github/scripts/issue/Post-IssueComment.ps1 `
      -Issue $env:PR_NUMBER `
      -BodyFile $env:REPORT_FILE `
      -Marker "AI-PR-QUALITY-GATE"
```

**Benefit**: Skill script is tested, handles edge cases, provides structured output.

## DRY Principle Applied

### Before (Duplicate)

```powershell
# In AIReviewCommon.psm1
function Send-PRComment { ... 80 lines ... }
function Send-IssueComment { ... 50 lines ... }

# In .claude/skills/github/scripts/pr/Post-PRCommentReply.ps1
# ... similar functionality with better features

# In .claude/skills/github/scripts/issue/Post-IssueComment.ps1
# ... similar functionality with idempotency
```

### After (Consolidated)

```powershell
# AIReviewCommon.psm1 - NO GitHub operations
# Exports: parsing, formatting, retry logic only

# Workflows call skill scripts directly:
& .claude/skills/github/scripts/issue/Post-IssueComment.ps1 ...
```

## Related Skills

- Skill-CI-004: Thin workflows reduce CI debugging time
- Skill-Testing-002: PowerShell modules enable fast feedback
- Skill-Architecture-005: Separation of orchestration and logic

## Validation Checklist

Before merging workflow changes:
- [ ] All logic is in `.psm1` or Claude skills
- [ ] Pester tests exist for all functions
- [ ] Workflow YAML is <100 lines (orchestration only)
- [ ] Can test changes locally before pushing
- [ ] No duplicate functions between module and skills

## Removed Functions (2025-12-18)

The following functions were removed from `AIReviewCommon.psm1` because they duplicated GitHub skill functionality:

| Removed Function | Replacement Skill Script |
|-----------------|-------------------------|
| `Send-PRComment` | `.claude/skills/github/scripts/issue/Post-IssueComment.ps1` |
| `Send-IssueComment` | `.claude/skills/github/scripts/issue/Post-IssueComment.ps1` |

Note: PRs are issues in GitHub's API, so `Post-IssueComment.ps1` works for both.

## Related

- [pattern-agent-generation-three-platforms](pattern-agent-generation-three-platforms.md)
- [pattern-github-actions-variable-evaluation](pattern-github-actions-variable-evaluation.md)
- [pattern-handoff-merge-session-histories](pattern-handoff-merge-session-histories.md)
- [pattern-single-source-of-truth-workflows](pattern-single-source-of-truth-workflows.md)

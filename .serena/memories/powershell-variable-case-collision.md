# Issue #500: Get-IssueContext Variable Collision Fix

## Problem

ConvertFrom-Json failed with error: "Cannot convert PSCustomObject to Int32"

**Root Cause**: PowerShell is case-insensitive. Variable `$issue` collided with parameter `$Issue`.

```powershell
# WRONG: Parameter name collision
param([int]$Issue)
$issue = gh issue view $Issue ... | ConvertFrom-Json
# ConvertFrom-Json tries to bind to $Issue parameter instead of creating new variable
```

## Solution

Rename internal variable to avoid collision:

```powershell
# CORRECT: Distinct variable name
param([int]$Issue)
$issueData = ConvertFrom-Json -InputObject $jsonResponse
```

## Validation

Manual tests on issues #497 and #500: Both passed

## Test Debt

Get-IssueContext.ps1 has zero Pester tests. Identified coverage gaps:

- Parameter validation tests
- Error handling paths (auth failure, API error, malformed JSON)
- Edge cases (missing fields, null values)

**Follow-up**: Create Pester test suite for issue scripts (0/6 currently tested)

## Related Pattern

**Skill Candidate**: Avoid variable names that differ only by case from parameter names in PowerShell

**Rationale**: PowerShell case-insensitivity makes debugging difficult. Linters may not catch this.

**Best Practice**: Use descriptive variable names that clearly differ from parameters

- Parameter: `$Issue`
- Variable: `$issueData` or `$issueInfo` (not `$issue`)

## QA Verdict

**Status**: NEEDS WORK (can deploy with test debt)
**Fix Quality**: High (defensive coding, clear naming, documented rationale)
**Test Coverage**: 0% (P1 follow-up required)

## Reference

- QA Report: `.agents/qa/500-get-issue-context-fix-test-report.md`
- Session: `.agents/sessions/2025-12-29-session-qa-issue-500.md`

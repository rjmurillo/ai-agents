# Analysis: Pre-commit QA Requirement Gap for Investigation Sessions

**Date**: 2025-12-31
**Author**: Claude (session-107)
**Status**: Draft for Agent Review

## Problem Statement

The pre-commit session protocol validator requires QA validation for ALL sessions on branches with code changes, regardless of whether the individual session made any code changes. This creates a usability gap for investigation-only sessions.

## Current Behavior

### Validation Logic (Validate-Session.ps1:336-351)

```powershell
# $docsOnly is determined by BRANCH-level changed files, not session-level
if (-not $docsOnly) {
  # Requires QA report path in Evidence column
  if ($row.Status -ne 'x') { Fail 'E_QA_REQUIRED' ... }
  if ($row.Evidence -notmatch '\.agents/qa/.*\.md') { Fail 'E_QA_EVIDENCE' ... }
} else {
  # Allows SKIPPED: docs-only evidence
  if ($row.Evidence -notmatch '(?i)SKIPPED:\s*docs-only') { Fail 'E_QA_SKIP_EVIDENCE' ... }
}
```

### The Gap

| Session Type | Branch Has Code Changes | Current Behavior | Expected Behavior |
|--------------|------------------------|------------------|-------------------|
| Code change session | Yes | Requires QA | Requires QA |
| Investigation session | Yes | Requires QA | Should allow skip |
| Docs-only session | No | Allows skip | Allows skip |
| Investigation session | No | Allows skip | Allows skip |

**Root Cause**: The validator determines `$docsOnly` from branch-level `git diff`, not from the session's actual work. An investigation session (read-only analysis, CI debugging, research) on a branch with code changes is forced to:

1. Provide a QA report (nothing to QA), or
2. Use `--no-verify` bypass (undermines validation)

## Evidence

### Session 106 Case Study

- **Branch**: `refactor/146-skip-tests-xml-powershell` (has PowerShell changes)
- **Session type**: Investigation-only (CI debugging for PR #593)
- **Changes made**: None - only read operations and analysis
- **Outcome**: Pre-commit validator failed requiring QA report
- **Workaround used**: `git commit --no-verify`

### Frequency

Investigation sessions are common scenarios:

1. **CI debugging**: Analyzing why workflows fail
2. **Code review**: Reviewing PRs without making changes
3. **Research**: Understanding codebase before implementation
4. **Root cause analysis**: Investigating bugs
5. **Architecture review**: Assessing design decisions

## Impact

| Impact | Severity | Description |
|--------|----------|-------------|
| Bypass normalization | High | Agents learn to use `--no-verify` routinely |
| Validation erosion | Medium | Bypasses hide real protocol violations |
| False friction | Low | Extra steps for legitimate workflows |

## Design Considerations

### Option 1: Session-Level Change Detection

Detect what files the session actually changed, not the branch.

**Pros**:

- Precise: Only requires QA when session made code changes
- Automatic: No manual annotation needed

**Cons**:

- Complex: Requires tracking session changes vs branch changes
- Fragile: Hard to determine "session boundaries" in git history

### Option 2: Explicit Investigation Mode

Allow sessions to self-declare as investigation-only with explicit evidence.

**Pros**:

- Simple: Just add a new evidence pattern
- Auditable: Investigation intent is documented
- Conservative: Requires explicit opt-in

**Cons**:

- Manual: Requires session author to know the pattern
- Trust-based: Could be misused to skip QA

### Option 3: File-Based QA Exemption

Allow sessions with only `.agents/sessions/*.md` changes to skip QA.

**Pros**:

- Automatic: Based on staged files
- Targeted: Only exempts pure documentation commits

**Cons**:

- Narrow: Doesn't cover sessions that also update memories
- Inconsistent: Session + memory commit still requires QA

### Option 4: QA Report Categories

Expand QA evidence to include investigation reports.

**Pros**:

- Consistent: All sessions have evidence
- Valuable: Investigation findings are documented

**Cons**:

- Overhead: Creates busy-work for simple investigations
- Scope creep: QA agent may not be right tool for investigations

## Questions for Agent Review

1. **Analyst**: What patterns exist in session logs for investigation-only sessions? How common are they?

2. **Architect**: Which option best aligns with the session protocol's design intent? Are there architectural concerns with any approach?

3. **Critic**: What could go wrong with each option? What edge cases exist?

4. **Security**: Does any option create security/compliance risks?

## Next Steps

1. Gather agent feedback on options
2. Select preferred approach
3. Create detailed implementation proposal
4. Route through critic validation
5. Implement and test

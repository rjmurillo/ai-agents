## Problem

Session Protocol Validation failures do not block PR merges. When the `validate` job fails, the `aggregate` job is skipped, preventing the enforcement step from executing. This allows PRs with malformed session logs to be merged via auto-merge.

## Impact

**Severity**: High
**Scope**: All PRs with session log changes

1. `validate` job exits with code 1 (correct behavior)
2. `aggregate` job is **skipped** due to failed dependency (bug)
3. Enforcement step never runs (critical gap)
4. PR merge is not blocked
5. Auto-merge can proceed when other branch protection rules pass

## Root Cause

**File**: `.github/workflows/ai-session-protocol.yml:249-250`

```yaml
aggregate:
  name: Aggregate Results
  needs: [detect-changes, validate]
  if: needs.detect-changes.outputs.has_sessions == 'true'
```

**GitHub Actions Behavior**: By default, jobs skip when dependencies fail unless explicitly configured with `always()` or similar conditions.

When `validate` fails:
- GitHub Actions skips `aggregate` due to failed `needs: validate`
- The `if` condition is never evaluated
- The enforcement step at line 449 never runs
- PR is not blocked

## Evidence

**Enforcement Step** (line 449-461):

```yaml
- name: Enforce MUST Requirements
  run: |
    if ($env:FINAL_VERDICT -eq 'CRITICAL_FAIL' -or [int]$env:MUST_FAILURES -gt 0) {
      exit 1  # This never runs if job is skipped
    }
```

This step should fail the workflow when session protocol violations exist, but it never executes if the job is skipped.

## Recommended Fix

**Change line 250**:

```yaml
aggregate:
  name: Aggregate Results
  needs: [detect-changes, validate]
  if: always() && needs.detect-changes.outputs.has_sessions == 'true'
```

**Rationale**:
- Runs even when `validate` fails
- Still respects `has_sessions` check
- Simple and clear intent
- Standard GitHub Actions pattern for aggregation jobs

## Verification Plan

1. Create test PR with intentional session protocol violations
2. Verify `validate` job fails
3. Verify `aggregate` job runs (not skipped)
4. Verify enforcement step executes and fails workflow
5. Verify PR merge is blocked

## Analysis Document

Full root cause analysis: `.agents/analysis/session-protocol-enforcement-gap-analysis.md`

## Related

- Session Protocol: `.agents/SESSION-PROTOCOL.md`
- Memory: `ci-infrastructure-003-job-status-verdict-distinction`
- Memory: `ci-infrastructure-001-fail-fast-infrastructure-failures`

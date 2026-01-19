# CI Infrastructure: Aggregate Job Always Pattern

**Atomicity Score**: 95%
**Date**: 2026-01-09
**Source**: Session 813 - Issue #856 RCA
**Impact**: 9/10 (Critical for multi-stage validation workflows)

## Statement

Aggregate jobs that collect results from matrix strategies MUST use `if: always()` to run even when validation jobs fail.

## Context

When workflows have matrix validation jobs that can fail, followed by an aggregate job that must collect all results and enforce blocking conditions.

## Problem

**GitHub Actions Default Behavior**: Jobs skip when dependencies fail unless explicitly configured.

```yaml
# Anti-pattern (BUG)
validate:
  strategy:
    matrix:
      file: ${{ fromJson(needs.detect.outputs.files) }}
  steps:
    - run: exit 1  # Fails on validation error

aggregate:
  needs: [detect, validate]  # Skipped when validate fails!
  if: needs.detect.outputs.has_files == 'true'
  steps:
    - run: exit 1  # Never runs - enforcement gap!
```

**Result**: PRs can merge with validation failures because enforcement never executes.

## Evidence

**Issue #856**: Session Protocol Validation workflow allowed PRs with malformed session logs to merge via auto-merge.

**Root Cause**: `.github/workflows/ai-session-protocol.yml:249-250`

```yaml
aggregate:
  name: Aggregate Results
  needs: [detect-changes, validate]
  if: needs.detect-changes.outputs.has_sessions == 'true'  # Not enough!
```

When `validate` job failed:
1. GitHub Actions skipped `aggregate` (default behavior)
2. `if` condition never evaluated
3. Enforcement step at line 449 never ran
4. PR not blocked

## Correct Pattern

```yaml
# Correct: Use always() condition
aggregate:
  name: Aggregate Results
  needs: [detect-changes, validate]
  if: always() && needs.detect-changes.outputs.has_sessions == 'true'
  steps:
    - name: Collect Results
      run: |
        # Collect from all validation jobs (success or failure)
        # Build aggregate verdict
    
    - name: Enforce Blocking Conditions
      run: |
        if ($verdict -eq 'CRITICAL_FAIL') {
          exit 1  # NOW this runs and blocks PR
        }
```

**Why This Works**:
- `always()` runs job even when dependencies fail
- Still respects other conditions (e.g., `has_sessions`)
- Enforcement step executes and can block PR
- Clear intent: "always aggregate results, regardless of individual failures"

## When to Use

Apply this pattern when:
- Matrix strategy runs validations that can fail
- Aggregate job must collect all results (success or failure)
- Aggregate job enforces blocking conditions
- PR merge decision depends on aggregate output

## Related Patterns

**Job Status vs Verdict** (ci-infrastructure-003):
- Individual validation jobs should fail fast on violations
- Aggregate job should collect all verdicts
- Aggregate job determines final PR outcome

**Fail Fast Infrastructure** (ci-infrastructure-001):
- Infrastructure failures: Exit immediately (no aggregation)
- Policy violations: Complete successfully, emit verdict, aggregate decides

## Implementation Checklist

- [ ] Matrix validation jobs can fail independently
- [ ] Aggregate job has `needs: [validate]`
- [ ] Aggregate job uses `if: always() && <other-conditions>`
- [ ] Aggregate job collects results from all matrix jobs
- [ ] Aggregate job enforces blocking conditions
- [ ] Test: Verify aggregate runs when validation fails
- [ ] Test: Verify enforcement blocks PR when violations exist

## Success Criteria

- Aggregate job runs even when validation jobs fail
- All validation results collected (success or failure)
- Enforcement step executes and blocks PR on violations
- No false negatives (violations missed)
- No enforcement gaps (PRs merge with violations)

## Related

- Issue #856: Session Protocol Validation enforcement gap
- Memory: ci-infrastructure-003-job-status-verdict-distinction
- Memory: ci-infrastructure-001-fail-fast-infrastructure-failures
- Analysis: .agents/analysis/session-protocol-enforcement-gap-analysis.md

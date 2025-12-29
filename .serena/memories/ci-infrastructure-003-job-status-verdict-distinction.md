# Skill: CI-003 Job Status vs Verdict Distinction

**Atomicity Score**: 88%
**Source**: Session 04 retrospective - Issue #357 RCA
**Date**: 2025-12-24
**Validation Count**: 1 (Issue #357 debugging)
**Tag**: helpful
**Impact**: 8/10 (Critical for multi-stage CI pipelines)

## Statement

Distinguish job completion status from verdict output in multi-stage pipelines.

## Context

When debugging CI workflow failures with multi-stage pipelines (collect → aggregate → post).

## Evidence

Session 04 - Issue #357:

1. **Confusion**: Issue claimed "aggregation bug" because job succeeded but verdict was CRITICAL_FAIL
2. **RCA Finding**: Job status (success/failure) ≠ Verdict output (PASS/CRITICAL_FAIL)
3. **Root Cause**: Conflated job completion with verdict value
4. **Resolution**: Separate concerns - job succeeds if script runs, verdict determines PR outcome

**Result**: Correctly diagnosed "not a bug" by understanding the distinction.

## Implementation Pattern

### Two Separate Concerns

| Concern | Question | Status Values | Determines |
|---------|----------|---------------|------------|
| **Job Status** | Did the script run successfully? | success, failure | Workflow execution health |
| **Verdict Output** | What did the script conclude? | PASS, WARN, CRITICAL_FAIL | PR merge decision |

### Correct Pattern

```yaml
aggregate:
  runs-on: ubuntu-latest
  steps:
    - name: Run aggregation
      id: aggregate
      run: |
        # Script ALWAYS succeeds if it runs
        VERDICT=$(determine_verdict)
        echo "verdict=$VERDICT" >> $GITHUB_OUTPUT
        echo "VERDICT: $VERDICT"
        # Job status: success (script ran)
        # Verdict output: may be CRITICAL_FAIL

    - name: Check verdict
      if: steps.aggregate.outputs.verdict == 'CRITICAL_FAIL'
      run: |
        echo "Verdict is CRITICAL_FAIL, blocking merge"
        exit 1  # NOW job fails
```

### Anti-Pattern (Conflation)

```yaml
aggregate:
  runs-on: ubuntu-latest
  steps:
    - name: Run aggregation
      run: |
        VERDICT=$(determine_verdict)
        if [ "$VERDICT" = "CRITICAL_FAIL" ]; then
          exit 1  # Job fails immediately
        fi
        # Problem: Can't distinguish script failure from CRITICAL_FAIL verdict
```

## Why This Matters

### Debugging Multi-Stage Pipelines

When investigating "Why did job succeed but PR blocked?":

1. **Check job status**: Did workflow step succeed?
   - Yes → Script ran successfully
   - No → Infrastructure/script failure

2. **Check verdict output**: What did script conclude?
   - PASS → No issues
   - WARN → Non-blocking issues
   - CRITICAL_FAIL → Blocking issues

3. **Expected behavior**:
   - Job success + CRITICAL_FAIL verdict = Working as designed
   - Job failure = Infrastructure problem (retry, investigate)

### Issue #357 Example

**Claimed**: "Aggregation bug - all checks pass but PR blocked"

**RCA**:
- Job status: success (aggregation script ran)
- Verdict output: CRITICAL_FAIL (security agent failed)
- Conclusion: **Not a bug** - system working correctly

## When to Use

Apply this distinction when:
- Debugging CI workflow failures
- Designing multi-stage pipelines (collect → aggregate → post)
- Investigating "job succeeded but PR blocked" scenarios
- Writing RCA for workflow issues
- Explaining CI behavior to users

## Design Guideline

**Separate concerns**:
- Job status = execution health (did script run?)
- Verdict output = business logic (what did script conclude?)

**Pattern**:
1. Script runs to completion → Job succeeds
2. Script emits verdict → Captured in output
3. Separate step checks verdict → Fails job if CRITICAL_FAIL

**Benefit**: Clear distinction between infrastructure failures and policy violations.

## Related Skills

- ci-ai-integration: Verdict token format
- workflow-verdict-tokens: Token parsing
- skill-ci-001-fail-fast-infrastructure-failures: When to fail job immediately
- skill-analysis-002-rca-before-implementation: RCA process

## Success Criteria

- Correctly diagnose job success + CRITICAL_FAIL verdict as working system
- Design pipelines with separated job status and verdict concerns
- Avoid conflating script execution success with verdict output
- Write clear RCA distinguishing infrastructure failures from policy violations

## Red Flags (Triggers for This Skill)

Watch for:
- "Job succeeded but PR blocked" - Check verdict output
- "Aggregation bug" - Verify job status vs verdict distinction
- "All checks pass but fails" - Separate job status from verdict
- Mixing exit codes for script failures and policy violations

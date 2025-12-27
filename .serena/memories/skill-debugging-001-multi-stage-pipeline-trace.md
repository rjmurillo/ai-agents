# Skill: Debugging-001 Multi-Stage Pipeline Trace

**Atomicity Score**: 85%
**Source**: Session 04 retrospective - Issue #357 RCA
**Date**: 2025-12-24
**Validation Count**: 1 (Issue #357 - found each stage worked correctly)
**Tag**: helpful
**Impact**: 8/10 (Prevents misattribution of failures)

## Statement

Trace each stage's input/output separately before assuming integration failure.

## Context

When debugging multi-stage CI pipelines (collect → aggregate → post) with unexpected failures.

## Evidence

Session 04 - Issue #357:

1. **Claim**: "Aggregation bug - all checks pass but PR blocked"
2. **RCA Approach**: Traced each stage separately
   - **Collection stage**: Each agent emitted verdict correctly ✓
   - **Aggregation stage**: Parsed verdicts correctly ✓
   - **Result stage**: Applied correct blocking logic ✓
3. **Finding**: Each stage worked correctly, no integration failure
4. **Conclusion**: Not a bug - confusion between job status and verdict output

## Implementation Pattern

### Step 1: Identify Pipeline Stages

```text
Example: AI PR Quality Gate
Stage 1: Collection (ai-review action)
  Input: PR diff
  Output: Individual agent verdicts

Stage 2: Aggregation (ai-quality-gate job)
  Input: Individual verdicts
  Output: Combined verdict

Stage 3: Result Handling (result job)
  Input: Combined verdict
  Output: PR block/pass decision
```

### Step 2: Trace Each Stage Independently

```bash
# Collection stage
echo "=== COLLECTION STAGE ==="
cat $GITHUB_STEP_SUMMARY | grep "VERDICT:"
# Expected: VERDICT: PASS/WARN/CRITICAL_FAIL for each agent

# Aggregation stage
echo "=== AGGREGATION STAGE ==="
gh run view $RUN_ID --log | grep "Aggregated verdict"
# Expected: Correctly parsed verdicts, applied priority logic

# Result handling
echo "=== RESULT STAGE ==="
gh run view $RUN_ID --log | grep "Final decision"
# Expected: Blocked if CRITICAL_FAIL, passed if PASS/WARN
```

### Step 3: Verify Each Stage's Contract

| Stage | Input Contract | Output Contract | Verification |
|-------|----------------|-----------------|--------------|
| Collection | PR diff | Agent verdicts | Check each agent ran |
| Aggregation | Agent verdicts | Combined verdict | Check parsing logic |
| Result | Combined verdict | Block/pass | Check decision logic |

### Step 4: Locate Actual Failure

```text
IF Collection stage fails:
    → Agent timeout, infrastructure issue
ELSE IF Aggregation stage fails:
    → Verdict parsing bug
ELSE IF Result stage fails:
    → Decision logic bug
ELSE:
    → Not a bug - verify expected behavior
```

## Why This Works

### Anti-Pattern (Assume Integration Failure)

```text
1. Observe: "All checks pass but PR blocked"
2. Assume: "Aggregation must be broken"
3. Implement: Fix aggregation logic
4. Result: Wasted work - aggregation was correct
```

### Correct Pattern (Trace Each Stage)

```text
1. Observe: "All checks pass but PR blocked"
2. Trace: Check collection output → ✓
3. Trace: Check aggregation output → ✓
4. Trace: Check result logic → ✓
5. Finding: Each stage correct, confusion about job-vs-verdict
6. Result: Issue resolved with documentation, no code change
```

## When to Use

Apply when:
- Multi-stage pipeline produces unexpected result
- "Should work but doesn't" scenarios
- Integration failure suspected
- Debugging aggregation logic
- Verifying data flow through stages

Skip when:
- Single-stage pipeline (no integration)
- Infrastructure failure (timeout, network)
- Obvious bug with clear reproduction

## Trace Checklist

1. **Identify Stages**
   - [ ] List all pipeline stages
   - [ ] Document input/output for each

2. **Trace Each Stage**
   - [ ] Verify input matches expected format
   - [ ] Verify output matches expected format
   - [ ] Check for data transformation errors

3. **Verify Contracts**
   - [ ] Each stage honors input contract
   - [ ] Each stage produces valid output
   - [ ] Output format matches next stage's input

4. **Locate Failure**
   - [ ] Which stage's output is incorrect?
   - [ ] Is it a stage bug or contract violation?
   - [ ] Or is expected behavior misunderstood?

## Related Skills

- skill-ci-003-job-status-verdict-distinction: Job status vs verdict concept
- skill-analysis-002-rca-before-implementation: RCA process
- ci-ai-integration: Multi-stage AI review pipeline design

## Success Criteria

- Correctly identify which stage (if any) is failing
- Avoid assuming integration failure without evidence
- Trace data flow through each stage
- Distinguish stage bugs from contract violations
- Prevent wasted implementation on working code

## Red Flags (Triggers for This Skill)

Watch for:
- "All checks pass but fails" - Trace each stage
- "Aggregation bug" - Verify each stage's output
- "Integration failure" - Trace input/output contracts
- "Used to work, now broken" - Check each stage for changes

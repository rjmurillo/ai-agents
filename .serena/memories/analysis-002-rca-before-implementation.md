# Skill: Analysis-002 RCA Before Implementation

**Atomicity Score**: 95%
**Source**: Session 04 retrospective - Issue #357 RCA
**Date**: 2025-12-24
**Validation Count**: 1 (Issue #357 - found "not a bug")
**Tag**: helpful
**Impact**: 10/10 (Prevents wasted work, critical for correctness)

## Statement

Run RCA to verify issue premise before implementing fixes.

## Context

When issue claims a bug, failure, or unexpected behavior that requires code changes.

## Evidence

Session 04 - Issue #357:

1. Issue claimed: "AI PR Quality Gate blocks PRs even when all checks pass"
2. RCA performed: Analyzed workflow logs, verdict aggregation
3. Finding: **Not a bug** - System works as designed
4. Result: No implementation needed, documentation improvement suggested

**Time saved**: ~2 hours of implementation + testing + PR review
**Correctness**: Avoided changing working code based on misunderstanding

## Implementation Pattern

### Step 1: Read Issue Claims

```text
Issue states: "X fails when Y happens"
Claim: System should do A but does B instead
```

### Step 2: Run RCA

```bash
# Collect evidence
- Review workflow logs
- Check actual behavior vs claimed behavior
- Trace execution path
- Verify assumptions
```

### Step 3: Validate Premise

**Question**: Is this actually a bug?

Possible findings:
- **Confirmed Bug**: Behavior differs from spec → Proceed with fix
- **Not a Bug**: Behavior matches spec, issue is misunderstanding → Document
- **Feature Request**: Enhancement, not bug → Reclassify issue
- **User Error**: Configuration issue → Provide guidance

### Step 4: Decision Gate

```text
IF RCA confirms bug:
    → Proceed to implementation
ELSE IF RCA finds misunderstanding:
    → Update documentation, close issue
ELSE IF RCA finds feature gap:
    → Reclassify as enhancement
ELSE IF RCA finds config issue:
    → Provide user guidance
```

## Why This Works

### Without RCA (Anti-pattern)

```text
1. Read issue: "X is broken"
2. Implement fix for X
3. Create PR
4. Review reveals: X was working correctly
5. Close PR, wasted 2+ hours
```

### With RCA (Correct Pattern)

```text
1. Read issue: "X is broken"
2. Run RCA: Analyze logs, trace execution
3. Finding: X works as designed, documentation unclear
4. Action: Update docs (15 min) instead of code (2+ hours)
5. Result: Issue resolved, no code churn
```

## When to Use

Apply BEFORE implementation when:
- Issue claims unexpected behavior
- Bug report without logs/evidence
- "Should work but doesn't" scenarios
- CI failure reports
- User-reported issues

Skip RCA when:
- Issue is enhancement request
- Typo/documentation fix
- Obvious bug with clear reproduction
- Regression with known root cause

## RCA Checklist

1. **Gather Evidence**
   - [ ] Review workflow logs
   - [ ] Check execution traces
   - [ ] Verify claimed behavior

2. **Verify Assumptions**
   - [ ] What does spec say?
   - [ ] What does code do?
   - [ ] Do they match?

3. **Classify Finding**
   - [ ] Confirmed bug → Implement fix
   - [ ] Not a bug → Document/close
   - [ ] Feature gap → Reclassify
   - [ ] Config issue → Guide user

4. **Document RCA**
   - [ ] Save findings to `.agents/analysis/`
   - [ ] Update issue with findings
   - [ ] Store learnings in memory

## Related Skills

- analysis-comprehensive-standard: Analysis depth requirements
- skill-implementation-001-memory-first-pattern: Check context before work
- analysis-gap-template: Gap analysis structure

## Success Criteria

- Avoid implementing fixes for non-bugs
- Reduce code churn from misunderstandings
- Improve issue triage accuracy
- Save implementation time on invalid premises
- Build institutional knowledge of system behavior

## Red Flags (Triggers for RCA)

Watch for:
- "Should work but doesn't" - Verify assumption
- "Used to work, now broken" - Check for config/env changes
- "All checks pass but fails" - Investigate aggregation logic
- "Works locally, fails in CI" - Environment differences
- "Intermittent failure" - Timing/race conditions

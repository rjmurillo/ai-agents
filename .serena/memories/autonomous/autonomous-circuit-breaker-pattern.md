# Autonomous Execution Circuit Breaker

**Date**: 2026-01-04
**Context**: PR #760 accumulated 38 commits without stopping
**Atomicity**: 98%

## The Pattern

After 3 failed fix attempts on same issue, STOP and request human guidance with evidence of attempts.

## Why 3 Attempts?

**Attempt 1**: May have misunderstood requirements
**Attempt 2**: May have missed subtle detail
**Attempt 3**: Pattern indicates fundamental gap in understanding

**Attempt 4+**: Wastes effort, damages user trust, accumulates context pollution

## Circuit Breaker Protocol

### When to Trigger

Circuit breaker activates when ANY of these conditions met:
1. Same issue failed 3 times (CI checks, review comments, user rejection)
2. 10 commits on same PR without merge (see retrospective-006)
3. User provides same feedback/patch 3 times
4. User expresses frustration explicitly

### What to Do When Triggered

1. **STOP** - Do not attempt 4th fix
2. **DOCUMENT** - List all 3 attempts with what was tried and why it failed
3. **ANALYZE** - Identify what understanding is missing
4. **REQUEST** - Ask user/human for guidance with evidence
5. **WAIT** - Do not resume until explicit approval

### Documentation Template

```markdown
## Circuit Breaker Triggered

**Issue**: [Brief description]
**Attempts**: 3 failed

### Attempt 1
- **What was tried**: [Description]
- **Why it failed**: [Evidence]
- **What was learned**: [Insight]

### Attempt 2
- **What was tried**: [Description]
- **Why it failed**: [Evidence]
- **What was learned**: [Insight]

### Attempt 3
- **What was tried**: [Description]
- **Why it failed**: [Evidence]
- **What was learned**: [Insight]

### Understanding Gap
[What is still unclear after 3 attempts]

### Request for Guidance
[Specific question or example needed]
```

## Evidence from PR #760

**Total commits**: 38
**Pattern**: No circuit breaker triggered despite repeated failures
**User feedback**: "bullshit you responded or even acknowledged all the comments"
**Outcome**: User frustration, trust damage, wasted effort

**If circuit breaker triggered at attempt 3**:
- Total commits: ~10 (instead of 38)
- User provides guidance earlier
- Prevents trust damage from repeated failures

## Success Metrics

### Without Circuit Breaker
- Commits: 38
- User frustration: High
- Resolution time: Long
- Learning efficiency: Low (same mistakes repeated)

### With Circuit Breaker
- Commits: 3-10 (stop after 3 failures)
- User frustration: Low (shows awareness of gap)
- Resolution time: Faster (correct guidance sooner)
- Learning efficiency: High (understand before attempting 4th time)

## Integration with Other Patterns

### Combines With

**autonomous-execution-003-patch-as-signal**:
- User provides patch unsolicited → Increment failure count
- If user provides patch 3 times → Circuit breaker triggers

**retrospective-006-commit-threshold-trigger**:
- After 10 commits without merge → Trigger mini-retrospective
- Mini-retrospective may identify need for circuit breaker

**security-013-no-blind-suppression**:
- Security suppression attempt = failure
- If attempted 3 times → Circuit breaker triggers

### Escalation Path

```text
Attempt 1 → Fail → Try different approach
Attempt 2 → Fail → Analyze what's missing
Attempt 3 → Fail → CIRCUIT BREAKER TRIGGER
  ↓
STOP autonomous execution
  ↓
Request human guidance
  ↓
Wait for approval
  ↓
Resume with new understanding
```

## Implementation Checklist

When implementing circuit breaker in autonomous mode:
- [ ] Track failure count per issue (not global)
- [ ] Define what counts as "same issue" (PR number, review thread, etc.)
- [ ] Document all attempts before triggering
- [ ] Clear, specific request for guidance
- [ ] Wait for explicit approval before resuming

## Exemptions (When NOT to Trigger)

Circuit breaker should NOT trigger for:
- Environmental issues (CI flakiness, network timeout)
- External dependency failures (API down, service unavailable)
- Infrastructure problems (runner capacity, quota limits)

**Rule**: Only trigger for issues under agent control (understanding, logic, implementation)

## Tuning the Threshold

**3 attempts** is default based on:
- Attempt 1: Quick fix (may work)
- Attempt 2: Thoughtful fix (understand better)
- Attempt 3: Deep analysis (still missing something)

**Adjust threshold if**:
- Simple issues: 2 attempts may suffice
- Complex issues: 3 attempts is firm limit (more = wasted effort)

**Never exceed 5 attempts** without human guidance.

## Related Skills

- autonomous-execution-guardrails (general autonomous behavior)
- autonomous-execution-003-patch-as-signal (user patch = failure signal)
- autonomous-execution-004-trust-metric (success = trust maintained)
- retrospective-006-commit-threshold-trigger (commit count threshold)

## Cross-Reference

- Retrospective: `.agents/retrospective/2026-01-04-pr760-security-suppression-failure.md`
- PR: #760 (38 commits without circuit breaker)
- Session: `.agents/sessions/2026-01-04-session-305-pr760-retrospective.md`

## Related

- [autonomous-circuit-breaker](autonomous-circuit-breaker.md)
- [autonomous-execution-failures-pr760](autonomous-execution-failures-pr760.md)
- [autonomous-execution-guardrails-lessons](autonomous-execution-guardrails-lessons.md)
- [autonomous-execution-guardrails](autonomous-execution-guardrails.md)
- [autonomous-patch-signal](autonomous-patch-signal.md)

# Skill-autonomous-execution-002: Circuit Breaker

**Statement**: After 3 failed attempts on same issue, STOP and request human guidance with attempt evidence.

**Context**: Repeated failures indicate missing understanding, not missing effort. Continuing to iterate after 3 failures wastes effort and damages user trust. Failing 38 times is worse than failing 3 and asking for help.

**Evidence**: PR #760 accumulated 38 commits with suppression attempt, incomplete fix, user patches provided 3 times, user frustration escalated. 54 review comments on single PR. If circuit breaker triggered at attempt 3, would have saved 35 commits and user frustration.

**Atomicity**: 98% | **Impact**: 10/10

## Pattern

Track failed attempts on same issue:

1. **Attempt 1 fails**: Document failure, analyze why
2. **Attempt 2 fails**: Document failure, try different approach
3. **Attempt 3 fails**: STOP autonomous execution here
4. **Request human guidance**: Provide summary of 3 failed attempts with evidence
   - What was tried
   - Why it failed
   - What evidence suggests (missing understanding? wrong approach? insufficient context?)
   - Recommended next steps (ask for clarification, get expert review, different strategy)

Evidence includes:
- Commit messages from failed attempts
- Test failures
- User feedback
- Code differences between attempts

## Anti-Pattern

Never continue autonomous execution beyond 3 failed attempts on same issue. This indicates:
- Missing understanding of problem domain
- Insufficient context for solving the issue
- Need for expert input or clarification

Continuing past this point damages user trust and wastes compute/time.

## Related

- [autonomous-circuit-breaker-pattern](autonomous-circuit-breaker-pattern.md)
- [autonomous-execution-failures-pr760](autonomous-execution-failures-pr760.md)
- [autonomous-execution-guardrails-lessons](autonomous-execution-guardrails-lessons.md)
- [autonomous-execution-guardrails](autonomous-execution-guardrails.md)
- [autonomous-patch-signal](autonomous-patch-signal.md)

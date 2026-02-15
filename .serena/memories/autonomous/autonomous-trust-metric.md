# Skill-autonomous-execution-004: Trust Metric

**Statement**: Autonomous execution success measured by user trust maintained, not by CI checks passed.

**Context**: True success in autonomous execution is user trust. CI checks passing is necessary but not sufficient. If user distrusts your approach, you've failed even if CI is green. PR #760 passed CI eventually but damaged user trust through suppression attempt.

**Evidence**: PR #760 final state: CI green (tests pass), but user frustrated after 38 commits and 54 review comments. Suppression attempt without understanding indicated agent optimizing for "make alert go away" instead of "solve problem correctly". Even after fix was correct, trust damage remained.

**Atomicity**: 87% | **Impact**: 9/10

## Pattern

Measure autonomous execution success:

1. **CI Passing** - Necessary but not sufficient
2. **Code Review Approval** - Reviews are substantive and positive
3. **User Satisfaction** - User expresses confidence in solution
4. **Low Iteration Count** - Problem solved in 2-3 attempts, not 38
5. **Trust Preserved** - User willing to trust agent on next issue

Red flags for trust damage:
- User provides patches (indicates agent misunderstanding)
- User expresses frustration in comments
- Excessive commits without merge (> 10 commits)
- Security concerns dismissed without understanding
- Suppression/bypass attempted without root cause analysis

## Anti-Pattern

Never optimize autonomous execution for:
- Making CI green fastest
- Minimizing code review comments
- Suppressing alerts instead of fixing them
- Merging quickly without proper validation

These optimize for speed over correctness and damage user trust.

## Related

- [autonomous-circuit-breaker-pattern](autonomous-circuit-breaker-pattern.md)
- [autonomous-circuit-breaker](autonomous-circuit-breaker.md)
- [autonomous-execution-failures-pr760](autonomous-execution-failures-pr760.md)
- [autonomous-execution-guardrails-lessons](autonomous-execution-guardrails-lessons.md)
- [autonomous-execution-guardrails](autonomous-execution-guardrails.md)

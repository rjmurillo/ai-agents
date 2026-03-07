# Skill Observations: cost-optimization

**Last Updated**: 2026-01-17
**Sessions Analyzed**: 2

## Purpose

This memory captures learnings from cost optimization strategies, token efficiency, and resource management across sessions.

## Constraints (HIGH confidence)

These are corrections that MUST be followed:

## Preferences (MED confidence)

These are preferences that SHOULD be followed:

- Batch agent invocations for parallel operations reduce overall latency and cost (Session 2026-01-16-session-07, 2026-01-16)
- Use sonnet (not opus) for CI automation tasks - CI automation doesn't require orchestration capabilities, sonnet provides sufficient quality at lower cost (Session 3, PR #918, 2026-01-16)
  - Evidence: Changed model from opus to sonnet for CI automation workflow execution

## Edge Cases (MED confidence)

These are scenarios to handle:

## Notes for Review (LOW confidence)

These are observations that may become patterns:

## History

| Date | Session | Type | Learning |
|------|---------|------|----------|
| 2026-01-16 | 2026-01-16-session-07 | MED | Batch agent invocations for parallel operations |
| 2026-01-16 | Session 3, PR #918 | MED | Use sonnet (not opus) for CI automation tasks |

## Related

- [performance-observations](performance-observations.md)
- [architecture-observations](architecture-observations.md)

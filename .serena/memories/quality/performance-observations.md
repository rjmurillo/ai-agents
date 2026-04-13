# Skill Observations: performance

**Last Updated**: 2026-01-16
**Sessions Analyzed**: 1

## Purpose

This memory captures learnings from performance optimization strategies, latency reduction, and efficiency improvements across sessions.

## Constraints (HIGH confidence)

These are corrections that MUST be followed:

- Context efficiency compounds: Small token savings multiply across agents and sessions. 82% memory retrieval reduction (ADR-017) + 3-9 tool allocation (ADR-003) = major impact on cost and latency (Session 07, 2026-01-16)
- MCP integration for 90-95% latency reduction: GitHub MCP reduces 183-416ms to 5-20ms per operation. Critical for multi-agent workflows (ADR-027, Session 07, 2026-01-16)

## Preferences (MED confidence)

These are preferences that SHOULD be followed:

- Cache invalidation strategy: Use deterministic naming and query parameters. Avoid manual purging (ADR-018, Session 07, 2026-01-16)

## Edge Cases (MED confidence)

These are scenarios to handle:

## Notes for Review (LOW confidence)

These are observations that may become patterns:

## History

| Date | Session | Type | Learning |
|------|---------|------|----------|
| 2026-01-16 | Session 07 | HIGH | Context efficiency compounds across agents and sessions |
| 2026-01-16 | Session 07 | HIGH | MCP integration 90-95% latency reduction (ADR-027) |
| 2026-01-16 | Session 07 | MED | Cache invalidation strategy with deterministic naming (ADR-018) |

## Related

- [cost-optimization-observations](cost-optimization-observations.md)
- [architecture-observations](architecture-observations.md)

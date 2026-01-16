# Skill Observations: cost-optimization

**Last Updated**: 2026-01-16
**Sessions Analyzed**: 1

## Purpose

This memory captures learnings from cost optimization strategies, model routing, infrastructure choices, and efficiency improvements across sessions.

## Constraints (HIGH confidence)

These are corrections that MUST be followed:

- Model selection for cost-quality balance: Opus for 7 critical agents (architecture, planning, critic), Sonnet for 11 structured agents. Achieves 40-50% cost reduction (ADR-002, ADR-021, Session 07, 2026-01-16)
- ARM runners for 37.5% cost savings: $1,800/year projected savings, 1-line change. High ROI trivial implementation (ADR-025, Session 07, 2026-01-16)
- Cost optimization compounds: 60-80% total reduction from layered improvements (model routing, ARM runners, path filters, concurrency groups, MCP latency). Small savings multiply (ADR-021, ADR-024, Session 07, 2026-01-16)

## Preferences (MED confidence)

These are preferences that SHOULD be followed:

- Path filters yield 20% CI cost reduction with 5-10 lines of configuration. High ROI (ADR-016, Session 07, 2026-01-16)
- Concurrency groups yield 10% cost reduction with 3 lines of configuration. Prevents redundant workflow runs (ADR-026, Session 07, 2026-01-16)

## Edge Cases (MED confidence)

These are scenarios to handle:

## Notes for Review (LOW confidence)

These are observations that may become patterns:

## History

| Date | Session | Type | Learning |
|------|---------|------|----------|
| 2026-01-16 | Session 07 | HIGH | Model selection 40-50% cost reduction (ADR-002, ADR-021) |
| 2026-01-16 | Session 07 | HIGH | ARM runners 37.5% savings $1,800/year (ADR-025) |
| 2026-01-16 | Session 07 | HIGH | Cost optimization compounds 60-80% total (ADR-021, ADR-024) |
| 2026-01-16 | Session 07 | MED | Path filters 20% CI cost reduction (ADR-016) |
| 2026-01-16 | Session 07 | MED | Concurrency groups 10% cost reduction (ADR-026) |

## Related

- [architecture-observations](architecture-observations.md)
- [performance-observations](performance-observations.md)

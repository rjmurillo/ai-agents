# Skill Observations: architecture

**Last Updated**: 2026-01-16
**Sessions Analyzed**: 2

## Purpose

This memory captures learnings from architecture and ADR compliance work across sessions.

## Constraints (HIGH confidence)

These are corrections that MUST be followed:

- Multi-tier architecture pattern for tool integrations: Tier 1 (CI/CD enforcement), Tier 2 (Local fast feedback), Tier 3 (Automatic background) (Session 2026-01-16-session-07, 2026-01-16)
- Fail-open for infrastructure errors, fail-closed for protocol violations (Session 2026-01-16-session-07, 2026-01-16)

## Preferences (MED confidence)

These are preferences that SHOULD be followed:

- When fixing ADR-017 violations, preserve intuitiveness and keyword clustering (Session 2026-01-14, 2026-01-14)
- Database caching at local development tier (Tier 2) provides significant performance improvement (60-120s → 10-20s) (Session 2026-01-16-session-07, 2026-01-16)
- Non-blocking PostToolUse hooks with timeout (30s) for automatic tier (Session 2026-01-16-session-07, 2026-01-16)
- Educational warnings (3x) before blocking for protocol enforcement (Session 2026-01-16-session-07, 2026-01-16)
- Date-based counter reset for educational thresholds prevents permanent blocking (Session 2026-01-16-session-07, 2026-01-16)

## Edge Cases (MED confidence)

These are scenarios to handle:

- Exit code 2 signals BLOCKING to Claude (convention across all hooks) (Session 2026-01-16-session-07, 2026-01-16)

## Notes for Review (LOW confidence)

These are observations that may become patterns:

## History

| Date | Session | Type | Learning |
|------|---------|------|----------|
| 2026-01-14 | 2026-01-14 | MED | When fixing ADR-017 violations preserve intuitiveness and keyword clustering |
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Multi-tier architecture pattern for tool integrations |
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Fail-open for infrastructure errors, fail-closed for protocol violations |
| 2026-01-16 | 2026-01-16-session-07 | MED | Database caching at Tier 2 provides 3-5x performance improvement |
| 2026-01-16 | 2026-01-16-session-07 | MED | Non-blocking PostToolUse hooks with timeout for automatic tier |
| 2026-01-16 | 2026-01-16-session-07 | MED | Educational warnings (3x) before blocking |
| 2026-01-16 | 2026-01-16-session-07 | MED | Date-based counter reset for educational thresholds |
| 2026-01-16 | 2026-01-16-session-07 | MED | Exit code 2 signals BLOCKING to Claude |

## Related

- [architecture-003-dry-exception-deployment](architecture-003-dry-exception-deployment.md)
- [architecture-015-deployment-path-validation](architecture-015-deployment-path-validation.md)
- [architecture-016-adr-number-check](architecture-016-adr-number-check.md)
- [architecture-adr-compliance-documentation](architecture-adr-compliance-documentation.md)
- [architecture-composite-action](architecture-composite-action.md)
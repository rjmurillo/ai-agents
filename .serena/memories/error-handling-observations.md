# Skill Observations: error-handling

**Last Updated**: 2026-01-16
**Sessions Analyzed**: 1

## Purpose

This memory captures learnings from error handling patterns, diagnostics, and failure recovery across sessions.

## Constraints (HIGH confidence)

These are corrections that MUST be followed:

- Fallback mechanisms must preserve error context - capture stderr before falling back and include in diagnostic output (Session 2026-01-16-session-07, 2026-01-16)
- Silent truncation must be reported - never silently truncate data without explicit warning that results are incomplete (Session 2026-01-16-session-07, 2026-01-16)

## Preferences (MED confidence)

These are preferences that SHOULD be followed:

- Use tempfile for stderr capture instead of inline command substitution for better error preservation (Session 2026-01-16-session-07, 2026-01-16)

## Edge Cases (MED confidence)

These are scenarios to handle:

## Notes for Review (LOW confidence)

These are observations that may become patterns:

## History

| Date | Session | Type | Learning |
|------|---------|------|----------|
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Fallback mechanisms must preserve error context |
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Silent truncation must be reported |
| 2026-01-16 | 2026-01-16-session-07 | MED | Use tempfile for stderr capture |

## Related

- [error-handling-002-suppressed-stderr-antipattern](error-handling-002-suppressed-stderr-antipattern.md)
- [error-handling-audit-session-378](error-handling-audit-session-378.md)
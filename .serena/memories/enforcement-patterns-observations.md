# Skill Observations: enforcement-patterns

**Last Updated**: 2026-01-16
**Sessions Analyzed**: 1

## Purpose

This memory captures learnings from protocol enforcement patterns, verification-based compliance, and hook implementation strategies across sessions.

## Constraints (HIGH confidence)

These are corrections that MUST be followed:

- Verification-based enforcement (check evidence) achieves 100% compliance vs <50% with guidance alone (Session 2026-01-16-session-07, 2026-01-16)
- Educational phase before blocking: 3 invocations with warnings, then block (Session 2026-01-16-session-07, 2026-01-16)
- Date-based counter reset for educational thresholds (Session 2026-01-16-session-07, 2026-01-16)
- YAML frontmatter must use block-style arrays, never inline arrays - inline arrays fail on Copilot CLI with CRLF line endings (Session 2026-01-16-session-07, 2026-01-16)

## Preferences (MED confidence)

These are preferences that SHOULD be followed:

- Hook audit logging for debugging and transparency (Session 2026-01-16-session-07, 2026-01-16)
- Structured error messages with actionable steps (Session 2026-01-16-session-07, 2026-01-16)
- Evidence patterns with proximity constraints for precision (Session 2026-01-16-session-07, 2026-01-16)

## Edge Cases (MED confidence)

These are scenarios to handle:

- ADR review requires BOTH session log mention AND debate log artifact (Session 2026-01-16-session-07, 2026-01-16)
- Fuzzy skill matching for raw gh commands (exact match + Levenshtein) (Session 2026-01-16-session-07, 2026-01-16)

## Notes for Review (LOW confidence)

These are observations that may become patterns:

## History

| Date | Session | Type | Learning |
|------|---------|------|----------|
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Verification-based enforcement achieves 100% compliance |
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Educational phase before blocking: 3 warnings then block |
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Date-based counter reset for educational thresholds |
| 2026-01-16 | 2026-01-16-session-07 | HIGH | YAML frontmatter must use block-style arrays, never inline |
| 2026-01-16 | 2026-01-16-session-07 | MED | Hook audit logging for debugging and transparency |
| 2026-01-16 | 2026-01-16-session-07 | MED | Structured error messages with actionable steps |
| 2026-01-16 | 2026-01-16-session-07 | MED | Evidence patterns with proximity constraints |
| 2026-01-16 | 2026-01-16-session-07 | MED | ADR review requires BOTH session log and debate artifact |
| 2026-01-16 | 2026-01-16-session-07 | MED | Fuzzy skill matching for raw gh commands |

## Related

- [autonomous-execution-guardrails](autonomous-execution-guardrails.md)
- [autonomous-execution-guardrails-lessons](autonomous-execution-guardrails-lessons.md)
- [protocol-013-verification-based-enforcement](protocol-013-verification-based-enforcement.md)
- [protocol-blocking-gates](protocol-blocking-gates.md)
- [validation-pr-gates](validation-pr-gates.md)
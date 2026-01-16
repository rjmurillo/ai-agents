# Skill Observations: bash-integration

**Last Updated**: 2026-01-16
**Sessions Analyzed**: 1

## Purpose

This memory captures learnings from bash scripting, cross-language integration, and shell patterns across sessions.

## Constraints (HIGH confidence)

These are corrections that MUST be followed:

- Never suppress stderr with 2>/dev/null without capturing it for diagnostics - silent failures mask root causes (Session 2026-01-16-session-07, 2026-01-16)
- Glob patterns with nested dirs require ** not just * (.claude/skills/*/scripts/**/*.ps1 vs */scripts/*.ps1) (Session 2026-01-16-session-07, 2026-01-16)
- Never assume directory structure exists - verify paths in actual repository (Session 2026-01-16-session-07, 2026-01-16)

## Preferences (MED confidence)

These are preferences that SHOULD be followed:

## Edge Cases (MED confidence)

These are scenarios to handle:

- echo with empty string adds newline, so 'wc -l' always returns 1 not 0 - use -z test instead (Session 2026-01-16-session-07, 2026-01-16)

## Notes for Review (LOW confidence)

These are observations that may become patterns:

## History

| Date | Session | Type | Learning |
|------|---------|------|----------|
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Never suppress stderr without capturing for diagnostics |
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Glob patterns with nested dirs require ** |
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Never assume directory structure exists |
| 2026-01-16 | 2026-01-16-session-07 | MED | echo adds newline, wc -l always returns 1 for empty string |

## Related

- [bash-integration-exit-code-testing](bash-integration-exit-code-testing.md)
- [bash-integration-exit-codes](bash-integration-exit-codes.md)
- [bash-integration-pattern-discovery](bash-integration-pattern-discovery.md)
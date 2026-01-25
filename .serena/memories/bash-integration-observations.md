# Skill Observations: bash-integration

**Last Updated**: 2026-01-18
**Sessions Analyzed**: 3

## Purpose

This memory captures learnings from bash scripting, cross-language integration, and shell patterns across sessions.

## Constraints (HIGH confidence)

These are corrections that MUST be followed:

- Never suppress stderr with 2>/dev/null without capturing it for diagnostics - silent failures mask root causes (Session 2026-01-16-session-07, 2026-01-16)
- Glob patterns with nested dirs require ** not just * (.claude/skills/*/scripts/**/*.ps1 vs */scripts/*.ps1) (Session 2026-01-16-session-07, Session 02, Session 03, 2026-01-16)
  - Additional evidence: Session 02 PR #919 - Changed from */scripts/*.ps1 to */scripts/**/*.ps1 to match files in nested subdirectories like scripts/pr/Get-PRChecks.ps1
  - Additional evidence: Batch 36 Session 03 - Pattern `*/scripts/*.ps1` failed to match nested scripts, reinforced need for `*/scripts/**/*.ps1` recursive pattern
- Never assume directory structure exists - verify paths in actual repository (Session 2026-01-16-session-07, Session 02, 2026-01-16)
  - Additional evidence: Session 02 - .github/tests/ assumed but doesn't exist, tests actually in .github/scripts/

## Preferences (MED confidence)

These are preferences that SHOULD be followed:

- Bash variable substitution ${var%.*} removes file extension - cleaner than separate case branches for .ps1 and .psm1 (Session 02, PR #919, 2026-01-15)
  - Evidence: Consolidated duplicate code branches using ${scriptname%.*} pattern per Gemini code review suggestion

## Edge Cases (MED confidence)

These are scenarios to handle:

- echo with empty string adds newline, so 'wc -l' always returns 1 not 0 - use -z test instead (Session 2026-01-16-session-07, 2026-01-16)

## Notes for Review (LOW confidence)

These are observations that may become patterns:

## History

| Date | Session | Type | Learning |
|------|---------|------|----------|
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Never suppress stderr without capturing for diagnostics |
| 2026-01-16 | 2026-01-16-session-07, Session 02, Session 03 | HIGH | Glob patterns with nested dirs require ** (reinforced by Sessions 02, 03) |
| 2026-01-16 | 2026-01-16-session-07, Session 02 | HIGH | Never assume directory structure exists (reinforced by Session 02) |
| 2026-01-16 | 2026-01-16-session-07 | MED | echo adds newline, wc -l always returns 1 for empty string |
| 2026-01-15 | Session 02, PR #919 | MED | Bash variable substitution ${var%.*} for extension removal |

## Related

- [bash-integration-exit-code-testing](bash-integration-exit-code-testing.md)
- [bash-integration-exit-codes](bash-integration-exit-codes.md)
- [bash-integration-pattern-discovery](bash-integration-pattern-discovery.md)

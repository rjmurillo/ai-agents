# Skill Observations: powershell

**Last Updated**: 2026-01-16
**Sessions Analyzed**: 1

## Purpose

This memory captures learnings from PowerShell scripting, cross-platform compatibility, and testing patterns across sessions.

## Constraints (HIGH confidence)

These are corrections that MUST be followed:

- For cross-platform hooks, use [Console]::In.ReadToEnd() instead of $input to avoid bash vs cmd.exe escaping issues (Session 2026-01-16-session-07, 2026-01-16)
- Always quote variables passed to external commands, even in PowerShell (CWE-78) (Session 2026-01-16-session-07, 2026-01-16)
- Test both positive AND negative cases - if testing 'should skip', also test 'should process' (Session 2026-01-16-session-07, 2026-01-16)
- Pattern matching must go from most specific to least specific (not alphabetical) (Session 2026-01-16-session-07, 2026-01-16)

## Preferences (MED confidence)

These are preferences that SHOULD be followed:

- PowerShell modules require -Force flag during development to reload changes (Import-Module ./MyModule.psm1 -Force) (Session 2026-01-16-session-07, 2026-01-16)

## Edge Cases (MED confidence)

These are scenarios to handle:

- Null check consistency within a script matters more than global style (Session 2026-01-16-session-07, 2026-01-16)

## Notes for Review (LOW confidence)

These are observations that may become patterns:

## History

| Date | Session | Type | Learning |
|------|---------|------|----------|
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Use [Console]::In.ReadToEnd() for cross-platform hooks |
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Always quote variables in external commands (CWE-78) |
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Test both positive and negative cases |
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Pattern matching: most specific first |
| 2026-01-16 | 2026-01-16-session-07 | MED | PowerShell modules require -Force flag during development |
| 2026-01-16 | 2026-01-16-session-07 | MED | Null check consistency within script |

## Related

- [powershell-array-contains](powershell-array-contains.md)
- [powershell-array-handling](powershell-array-handling.md)
- [powershell-cross-platform-ci](powershell-cross-platform-ci.md)
- [powershell-cross-platform-patterns](powershell-cross-platform-patterns.md)
- [powershell-like-pattern-matching](powershell-like-pattern-matching.md)
- [powershell-security-ai-output](powershell-security-ai-output.md)
- [powershell-string-safety](powershell-string-safety.md)
- [powershell-testing-patterns](powershell-testing-patterns.md)
- [powershell-variable-case-collision](powershell-variable-case-collision.md)
- [powershell-variable-shadowing-detection](powershell-variable-shadowing-detection.md)

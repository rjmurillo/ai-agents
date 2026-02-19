# Skill Observations: error-handling

**Last Updated**: 2026-01-18
**Sessions Analyzed**: 1

## Purpose

This memory captures learnings from error handling patterns, debugging strategies, and error recovery mechanisms across sessions.

## Constraints (HIGH confidence)

These are corrections that MUST be followed:

- Error suppression anti-pattern - redirecting stderr to Write-Verbose BEFORE checking $LASTEXITCODE hides critical errors (Session 7, PR #908, 2026-01-16)
  - Evidence: Batch 38 - PowerShell script redirected `2>&1 | Write-Verbose` before `if ($LASTEXITCODE -ne 0)`, suppressing error messages before exit code check
  - Root cause: Error output consumed by Write-Verbose pipeline, making diagnosis impossible when $LASTEXITCODE indicates failure
  - Correct pattern: Check $LASTEXITCODE first, THEN redirect stderr conditionally based on success/failure

## Preferences (MED confidence)

These are preferences that SHOULD be followed:

## Edge Cases (MED confidence)

These are scenarios to handle:

## Notes for Review (LOW confidence)

These are observations that may become patterns:

## History

| Date | Session | Type | Learning |
|------|---------|------|----------|
| 2026-01-16 | Session 7, PR #908 | HIGH | Error suppression anti-pattern - stderr redirect before LASTEXITCODE |

## Related

- `powershell-error-handling`
- `debugging-strategies`

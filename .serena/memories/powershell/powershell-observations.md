# Skill Observations: powershell

**Last Updated**: 2026-01-18
**Sessions Analyzed**: 10

## Purpose

This memory captures learnings from PowerShell scripting, cross-platform compatibility, and testing patterns across sessions.

## Constraints (HIGH confidence)

These are corrections that MUST be followed:

- For cross-platform hooks, use [Console]::In.ReadToEnd() instead of $input to avoid bash vs cmd.exe escaping issues (Session 2026-01-16-session-07, 2026-01-16)
- Always quote variables passed to external commands, even in PowerShell (CWE-78) (Session 2026-01-16-session-07, 2026-01-16)
- Test both positive AND negative cases - if testing 'should skip', also test 'should process' (Session 2026-01-16-session-07, 2026-01-16)
- Pattern matching must go from most specific to least specific (not alphabetical) (Session 2026-01-16-session-07, 2026-01-16)
- Collect arrays using $() subexpression operator, never use += in loops - prevents O(n²) reallocation (Session 2026-01-16-session-07, PR #715)
- Use `@($raw) | Where-Object { $_ }` before `-contains` to filter nulls from potentially empty arrays (Session 07, 2026-01-16)
  - Evidence: PR #212 cursor[bot] #2628872634 - null method call on `@($null)` array, 94% atomicity
- Wrap single strings with `@()` before `-contains` operator to prevent type errors (Session 07, 2026-01-16)
  - Evidence: PR #212 cursor[bot] #2628872629 - `-contains` failed on single string milestone check, 95% atomicity
- Call `.ToLowerInvariant()` on strings before `-contains` for case-insensitive matching (default is case-sensitive) (Session 07, 2026-01-16)
  - Evidence: PR #212 Copilot - 3 instances of case-sensitive matching bugs in label/milestone comparison, 96% atomicity
- YAML + PowerShell here-strings conflict: Here-string closing `"@` must be at column 0, conflicts with YAML block scalar indentation. Fix: Use array-join pattern ($lines -join "`n") (Session 01, PR #845, 2026-01-16)
  - Evidence: Session 01 - PowerShell here-string closing delimiter caused YAML parser errors at lines 618 and 672. Used `act` for local validation.
- JSON property casing must match schema exactly - PowerShell JSON conversion is case-sensitive. Use PascalCase Complete/Evidence not lowercase complete/evidence (Session 388, 2026-01-09)
  - Evidence: New-SessionLogJson.ps1 and Convert-SessionToJson.ps1 used lowercase property names causing schema validation failures
- POSIX character classes [[:space:]] more compatible than \s in bash regex - improves cross-platform pre-commit hook reliability (Session 821, 2026-01-10)
  - Evidence: Pre-commit hook SHA-pinning validation used `\s` causing compatibility issues, changed to `[[:space:]]` for POSIX compliance
- PowerShell $matches automatic variable shadowing - must rename to avoid conflicts. Use descriptive name like $itemMatches instead (Session 826, 2026-01-13)
  - Evidence: Generate-Agents.Common.psm1 regex match variable conflicted with PowerShell $matches automatic variable, causing unexpected behavior
- Conditional execution for dot-sourced scripts - prevent script execution when dot-sourced for testing. Pattern: `if ($MyInvocation.InvocationName -ne '.') { <main script logic> }` (Session 02, 2026-01-15)
  - Evidence: CodeQL scripts executed when dot-sourced by Pester, breaking test isolation. Wrapped main logic in conditional check.

## Preferences (MED confidence)

These are preferences that SHOULD be followed:

- PowerShell modules require -Force flag during development to reload changes (Import-Module ./MyModule.psm1 -Force) (Session 2026-01-16-session-07, 2026-01-16)
- Use `([pattern])?$` not `[pattern]?$` for optional trailing characters in regex validation (Session 07, 2026-01-16)
  - Evidence: PR #212 Copilot - 5 instances of `[a-zA-Z0-9]?$` allowing trailing special chars, 93% atomicity
- PowerShell module location convention: Use scripts/modules/ for reusable modules (e.g., ValidationPrimitives.psm1, SkillLearning.Helpers) (Sessions 824, 907, 2026-01-16)
  - Evidence: Sessions 824 and 907 - Consistent pattern for module extraction and organization
- PSAvoidUsingWriteHost can be suppressed for user-facing installation/scan scripts with colored output - clarity and UX trump PSScriptAnalyzer rules. Visual feedback is critical in installation scripts (Sessions 02, 03, 2026-01-15/16)
  - Evidence: Suppressed PSAvoidUsingWriteHost in .PSScriptAnalyzerSettings.psd1 for CodeQL Install/Scan scripts providing colored user feedback
- PowerShell interprets $Variable: as drive-qualified path syntax (C:, D:). Use ${Variable}: to escape and prevent parser errors (Session 905, 2026-01-13)
  - Evidence: Error 'Variable reference is not valid. ':' was not followed by a valid variable name' when using $Table: in string

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
| 2026-01-16 | 2026-01-16-session-07 | HIGH | Use $() subexpression for arrays, never += in loops |
| 2026-01-16 | Session 07 | HIGH | Filter nulls with `@($raw) \| Where-Object { $_ }` before `-contains` |
| 2026-01-16 | Session 07 | HIGH | Wrap single strings with `@()` before `-contains` |
| 2026-01-16 | Session 07 | HIGH | Use `.ToLowerInvariant()` for case-insensitive `-contains` |
| 2026-01-16 | Session 01, PR #845 | HIGH | YAML + PowerShell here-strings conflict - use array-join pattern |
| 2026-01-09 | Session 388 | HIGH | JSON property casing must match schema exactly |
| 2026-01-10 | Session 821 | HIGH | POSIX character classes [[:space:]] more compatible than \s |
| 2026-01-13 | Session 826 | HIGH | PowerShell $matches automatic variable shadowing |
| 2026-01-15 | Session 02 | HIGH | Conditional execution for dot-sourced scripts |
| 2026-01-16 | 2026-01-16-session-07 | MED | PowerShell modules require -Force flag during development |
| 2026-01-16 | Session 07 | MED | Use atomic grouping `([pattern])?$` for optional trailing chars |
| 2026-01-16 | Sessions 824, 907 | MED | Module location convention: scripts/modules/ |
| 2026-01-16 | 2026-01-16-session-07 | MED | Null check consistency within script |
| 2026-01-15/16 | Sessions 02, 03 | MED | PSAvoidUsingWriteHost suppression for user-facing colored output |
| 2026-01-13 | Session 905 | MED | $Variable: interpreted as drive-qualified path, use ${Variable}: |

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

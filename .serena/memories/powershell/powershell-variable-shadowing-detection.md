# PowerShell Variable Shadowing Detection

## Pattern

Grep for PowerShell automatic variable names (`$matches`, `$Error`, `$?`, `$_`, `$PSItem`) to prevent unintentional shadowing that causes subtle bugs.

## Problem

PowerShell has automatic variables that are implicitly set by the runtime. Reusing these names creates variable shadowing where your local variable masks the automatic variable, causing:

- Silent failures (regex `$matches` not populated)
- Lost error information (`$Error` shadowed)
- Control flow bugs (`$?` exit code shadowed)
- Pipeline issues (`$_` current object unavailable)

## Solution

**During code review** (before testing):

1. Grep for automatic variable patterns: `$matches`, `$Error`, `$?`, `$_`, `$PSItem`, `$PSCmdlet`
2. Flag any usage as local variable names
3. Rename to descriptive alternatives: `$itemMatches`, `$errorLog`, `$exitCode`, `$currentItem`

## Evidence

**Session 826** (2026-01-13): PowerShell parser code used `$matches` as a variable name to store regex match results. This shadowed PowerShell's automatic `$matches` variable, causing the automatic variable to become inaccessible. Changed to `$itemMatches` before testing, preventing failures.

```powershell
# ❌ INCORRECT: Shadows automatic variable
$matches = [regex]::Matches($line, $pattern)

# ✅ CORRECT: Descriptive name avoids conflict
$itemMatches = [regex]::Matches($line, $pattern)
```

## PowerShell Automatic Variables Reference

| Variable | Purpose | Common Shadowing Impact |
|----------|---------|------------------------|
| `$matches` | Regex match results | Regex operations fail silently |
| `$Error` | Error array | Error handling breaks |
| `$?` | Last command exit status | Control flow bugs |
| `$_` | Current pipeline object | `ForEach-Object`, `Where-Object` fail |
| `$PSItem` | Alias for `$_` | Same as `$_` |
| `$PSCmdlet` | Current cmdlet | Advanced function failures |

## Impact

- **Atomicity**: 95%
- **Domain**: powershell-development
- **Failure Mode**: Silent failures, difficult debugging
- **Detection**: Code review (before testing)

## Implementation

Add to PowerShell code review checklist:
```markdown
- [ ] Grep for `$matches`, `$Error`, `$?`, `$_` variable names
- [ ] Verify no automatic variable shadowing
- [ ] Use descriptive names: `$itemMatches`, `$errorLog`, `$exitCode`, `$currentItem`
```

## Related

- [[powershell-array-handling]] - PowerShell array patterns
- [[powershell-string-safety]] - String handling best practices
- [[powershell-testing-patterns]] - Testing strategies

## Source

- Session: 826 (2026-01-13)
- Retrospective: `.agents/retrospective/2026-01-13-fix-tools-frontmatter-retrospective.md`
- Learning: L2 (Phase 4, Lines 532-540)
- Commit: 96d88ac (variable renamed before merge)

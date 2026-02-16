# PowerShell Pitfalls Pattern

## Variable Shadowing

PowerShell has automatic variables that get overwritten by regex operations. Using these names for your own variables causes conflicts.

### Dangerous Variables

| Variable | Populated By | Risk |
|----------|--------------|------|
| `$matches` | `-match` operator | Overwrites your hashtable |
| `$Error` | Any error | Array grows unexpectedly |
| `$?` | Last command status | Boolean changes silently |
| `$_` | Pipeline input | Scope confusion |
| `$input` | Pipeline input | Scope confusion |

### Example Problem

```powershell
# BAD: $matches is automatic variable
$matches = [regex]::Matches($content, $pattern)
foreach ($match in $matches) {  # $matches may be wrong type
    # ...
}
```

### Solution

```powershell
# GOOD: Use distinct variable name
$itemMatches = [regex]::Matches($content, $pattern)
foreach ($match in $itemMatches) {
    # ...
}
```

## Detection

Run before code review:

```powershell
# Find potential shadowing issues
Select-String -Path "*.ps1" -Pattern '\$matches\s*=' -AllMatches
Select-String -Path "*.ps1" -Pattern '\$Error\s*=' -AllMatches
```

## Evidence

- Session 826: `$matches` renamed to `$itemMatches` in Generate-Agents.Common.psm1
- Caught during code review before tests ran

## Related

- [[learnings-2026-01]] - Learning L2: PowerShell Variable Shadowing Detection

# PowerShell `-like` Pattern Matching Limitations

## Problem

PowerShell's `-like` operator does NOT support recursive directory matching.

## Example

```powershell
# This does NOT work for nested directories
'templates/agents/file.md' -like 'templates/*'  # Returns $false

# Because `-like` treats `*` as matching any characters EXCEPT path separators
```

## Solution

For recursive matching, you must explicitly list subdirectory patterns:

```powershell
$patterns = @(
    'templates/*',        # Matches templates/file.md
    'templates/*/*',      # Matches templates/agents/file.md
    'templates/*/*/*'     # Matches templates/agents/sub/file.md
)
```

## Applied In

- `.claude/skills/merge-resolver/scripts/Resolve-PRConflicts.ps1` - Auto-resolvable file patterns

## See Also

- For true recursive matching, consider using `Get-ChildItem -Recurse` with `-Filter` or regex patterns

## Related

- [powershell-array-contains](powershell-array-contains.md)
- [powershell-array-handling](powershell-array-handling.md)
- [powershell-cross-platform-ci](powershell-cross-platform-ci.md)
- [powershell-security-ai-output](powershell-security-ai-output.md)
- [powershell-string-safety](powershell-string-safety.md)

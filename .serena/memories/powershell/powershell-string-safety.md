# PowerShell String Safety

## Skill-001: Variable Interpolation Safety (95%)

**Statement**: Use subexpression syntax `$($var)` or braced syntax `${var}` when variable is followed by colon in double-quoted strings.

**Problem**:

```powershell
# WRONG - Colon causes scope qualifier ambiguity
$message = "Pull Request: $PullRequest: Title"  # Syntax error!
```

**Solution**:

```powershell
# CORRECT - Subexpression syntax
$message = "Pull Request: $($PullRequest): Title"

# ALTERNATIVE - Braced syntax
$message = "Pull Request: ${PullRequest}: Title"
```

PowerShell interprets `$var:` as scope qualifier (like `$global:var`). Wrap with `$()` or `${}` to disambiguate.

**Evidence**: PR #79

## Skill-007: Here-String Terminator Column Zero (96%)

**Statement**: Here-string terminators (`"@` or `'@`) must start at column 0 with no leading whitespace.

**Problem**:

```powershell
# WRONG - Terminator is indented
$content = @"
Some content here
  "@    # ERROR: The string is missing the terminator
```

**Solution**:

```powershell
# CORRECT - Terminator at column 0
$content = @"
Some content here
"@
```

**Detection**: Error message: "The string is missing the terminator: `"@`"

**Evidence**: PR #224

## Related

- [powershell-array-contains](powershell-array-contains.md)
- [powershell-array-handling](powershell-array-handling.md)
- [powershell-cross-platform-ci](powershell-cross-platform-ci.md)
- [powershell-like-pattern-matching](powershell-like-pattern-matching.md)
- [powershell-security-ai-output](powershell-security-ai-output.md)

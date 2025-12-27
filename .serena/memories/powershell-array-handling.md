# PowerShell Array Handling Best Practices

**Domain**: PowerShell Development
**Last Updated**: 2025-12-26
**Source**: PR #402 debugging session (commit 526f551)

## Anti-Pattern: Double-Nested Arrays

**NEVER** combine `Write-Output -NoEnumerate` with `@()` wrapper at call site.

### The Problem

```powershell
# Inside function
function Get-Items {
    $items = @(1, 2, 3)
    Write-Output -NoEnumerate $items  # Returns array as SINGLE object
}

# At call site
$result = @(Get-Items)  # Wraps the single object in ANOTHER array

# Result: @( @(1, 2, 3) )
# foreach $item in $result → $item = @(1, 2, 3) (entire inner array, not elements)
```

### Real-World Impact

**PR #402**: Script failed on all 15 PRs with "property 'number' cannot be found"

- Function used `Write-Output -NoEnumerate $similar`
- Call site used `$similarPRs = @(Get-SimilarPRs ...)`
- Resulted in `@( @(items) )` - double-nested array
- `foreach ($similar in $similarPRs)` received entire inner array as single element
- Accessing `$similar.number` tried to access property on array object (fails)

### Correct Patterns

| Scenario | Function Side | Call Site | Result |
|----------|---------------|-----------|--------|
| **Return array** | `return $items` | `$result = Get-Items` | Flat array ✓ |
| **Return array (safe)** | `return $items` | `$result = @(Get-Items)` | Flat array ✓ |
| **Return empty safe** | `return @()` | `$result = Get-Items` | Empty array ✓ |
| **WRONG** | `Write-Output -NoEnumerate $items` | `$result = @(Get-Items)` | Double-nested ✗ |

### Recommended Approach

```powershell
# CORRECT - simple return
function Get-SimilarPRs {
    $similar = @()
    # ... populate array ...

    # Simple return - let PowerShell handle it
    return $similar
}

# Call site - @() wrapper is SAFE with simple return
$similarPRs = @(Get-SimilarPRs -Owner $Owner -Repo $Repo)

# Result: Flat array, foreach works correctly
foreach ($pr in $similarPRs) {
    Write-Host $pr.number  # ✓ Works
}
```

### When to Use Write-Output -NoEnumerate

**Almost never.** Specifically avoid if:

- Call site might use `@()` wrapper
- You don't control all call sites
- You're trying to prevent empty array issues (use `@()` wrapper at call site instead)

**Only use when:**

- You specifically need pipeline unwrapping prevention
- You control ALL call sites
- You have documented why (rare edge cases)

**Better alternative:** Use comma operator `, $items` if you must return array as single object

### Rule of Thumb

If you find yourself using `Write-Output -NoEnumerate`, ask "Why?"

99% of the time, simple `return $array` is correct. PowerShell's natural array handling works well.

## Skills

- **Skill-PowerShell-004**: Use simple return for arrays; avoid Write-Output -NoEnumerate with @() wrapper
- **Atomicity**: 95%
- **Evidence**: PR #402 commit 526f551, runtime failure on 15 PRs

# PowerShell Array Contains Patterns

## Skill-002: Null-Safety for Contains Operator (94%)

**Statement**: Use `@($raw) | Where-Object { $_ }` before `-contains` to filter nulls from potentially empty arrays.

**Problem**:

```powershell
# WRONG - Creates array with null if results are empty
$results = @(Get-Something)
if ($results -contains $item) { }  # Null method call
```

**Solution**:

```powershell
# CORRECT - Filters nulls before contains
$results = @(Get-Something) | Where-Object { $_ }
if ($results -contains $item) { }
```

`@($null)` creates single-element array containing null, not empty array.

**Evidence**: PR #212

## Skill-003: Array Coercion for Single Items (95%)

**Statement**: Wrap single strings with `@()` before `-contains` operator.

**Problem**:

```powershell
# WRONG - Fails if $Milestone is a single string
if ($Milestone -contains $label) { }  # Type error!
```

**Solution**:

```powershell
# CORRECT - Coerces single string to array
if (@($Milestone) -contains $label) { }
```

PowerShell `-contains` treats strings as character arrays, not string collections.

**Evidence**: PR #212

## Skill-004: Case-Insensitive String Matching (96%)

**Statement**: Call `.ToLowerInvariant()` on strings before `-contains` for case-insensitive matching.

**Problem**:

```powershell
# WRONG - Case-sensitive by default
if ($labels -contains $input) { }  # Fails if case differs
```

**Solution**:

```powershell
# CORRECT - Normalize case
if ($labels.ToLowerInvariant() -contains $input.ToLowerInvariant()) { }
```

Use `.ToLowerInvariant()` over `.ToLower()` for culture-independent comparisons.

**Evidence**: PR #212

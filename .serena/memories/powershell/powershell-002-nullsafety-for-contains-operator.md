# Powershell: Nullsafety For Contains Operator

## Skill-PowerShell-002: Null-Safety for Contains Operator

**Statement**: Use `@($raw) | Where-Object { $_ }` before `-contains` to filter nulls from potentially empty arrays

**Context**: When using `-contains` operator on potentially empty PowerShell arrays

**Evidence**: PR #212 cursor[bot] #2628872634 - null method call on `@($null)` array

**Atomicity**: 94%

**Tag**: helpful (prevents null reference errors)

**Impact**: 10/10 (prevents runtime failures)

**Created**: 2025-12-20

**Problem**:

```powershell
# WRONG - Creates array with null if results are empty
$results = @(Get-Something)
if ($results -contains $item) { }  # Fails with null method call if results empty

# WRONG - No null protection
$results = Get-Something
if ($results -contains $item) { }  # Fails on empty results
```

**Solution**:

```powershell
# CORRECT - Filters nulls before contains
$results = @(Get-Something) | Where-Object { $_ }
if ($results -contains $item) { }
```

**Why It Matters**:

PowerShell's `@()` operator coerces values to arrays but `@($null)` creates a single-element array containing null, not an empty array. When you call `-contains` on this array, it may invoke methods on null elements, causing runtime errors.

**Pattern**:

```powershell
# Safe pattern for potentially empty results
$safeResults = @($rawResults) | Where-Object { $_ }
```

**Anti-Pattern**:

```powershell
# Unsafe - can create @($null)
$unsafeResults = @($rawResults)
```

**Validation**: 1 (PR #212)

---

## Related

- [powershell-001-casesensitive-regex-matching](powershell-001-casesensitive-regex-matching.md)
- [powershell-001-variable-interpolation-safety](powershell-001-variable-interpolation-safety.md)
- [powershell-002-pester-hashtable-initialization](powershell-002-pester-hashtable-initialization.md)
- [powershell-003-array-coercion-for-single-items](powershell-003-array-coercion-for-single-items.md)
- [powershell-004-caseinsensitive-string-matching](powershell-004-caseinsensitive-string-matching.md)

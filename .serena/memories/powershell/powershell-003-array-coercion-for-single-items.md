# Powershell: Array Coercion For Single Items

## Skill-PowerShell-003: Array Coercion for Single Items

**Statement**: Wrap single strings with `@()` before `-contains` operator to prevent type errors

**Context**: When variable may be single string or array, before using `-contains`

**Evidence**: PR #212 cursor[bot] #2628872629 - `-contains` failed on single string

**Atomicity**: 95%

**Tag**: helpful (prevents type errors)

**Impact**: 9/10 (enables consistent array operations)

**Created**: 2025-12-20

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

**Why It Matters**:

PowerShell's `-contains` operator works on arrays. If the left operand is a single string, PowerShell treats it as a character array, not a string collection. Wrapping with `@()` ensures consistent array behavior.

**Pattern**:

```powershell
# Safe pattern for potentially single-item variable
@($variable) -contains $item
```

**Anti-Pattern**:

```powershell
# Unsafe - assumes variable is array
$variable -contains $item
```

**Validation**: 1 (PR #212)

---

## Related

- [powershell-001-casesensitive-regex-matching](powershell-001-casesensitive-regex-matching.md)
- [powershell-001-variable-interpolation-safety](powershell-001-variable-interpolation-safety.md)
- [powershell-002-nullsafety-for-contains-operator](powershell-002-nullsafety-for-contains-operator.md)
- [powershell-002-pester-hashtable-initialization](powershell-002-pester-hashtable-initialization.md)
- [powershell-004-caseinsensitive-string-matching](powershell-004-caseinsensitive-string-matching.md)

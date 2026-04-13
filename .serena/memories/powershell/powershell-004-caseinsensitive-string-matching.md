# Powershell: Caseinsensitive String Matching

## Skill-PowerShell-004: Case-Insensitive String Matching

**Statement**: Call `.ToLowerInvariant()` on strings before `-contains` for case-insensitive matching

**Context**: When matching labels, milestones, or other user input where case should not matter

**Evidence**: PR #212 Copilot review - 3 instances of case-sensitive matching bugs

**Atomicity**: 96%

**Tag**: helpful (prevents case-sensitivity bugs)

**Impact**: 8/10 (improves user experience)

**Created**: 2025-12-20

**Problem**:

```powershell
# WRONG - Case-sensitive by default
if ($labels -contains $input) { }  # Fails if case differs
```

**Solution**:

```powershell
# CORRECT - Normalize case before comparison
if ($labels.ToLowerInvariant() -contains $input.ToLowerInvariant()) { }
```

**Why It Matters**:

PowerShell's `-contains` operator is case-sensitive by default. When matching user input (labels, milestones, tags), case should typically not matter. Normalizing both operands to lowercase ensures consistent matching.

**Pattern**:

```powershell
# Safe pattern for case-insensitive matching
$collection.ToLowerInvariant() -contains $item.ToLowerInvariant()

# Alternative: Use -in operator with lowercase
$item.ToLowerInvariant() -in $collection.ToLowerInvariant()
```

**Anti-Pattern**:

```powershell
# Unsafe - case-sensitive
$collection -contains $item
```

**Note**: `.ToLowerInvariant()` is preferred over `.ToLower()` for culture-independent comparisons.

**Validation**: 1 (PR #212, 3 instances fixed)

---

## Related

- [powershell-001-casesensitive-regex-matching](powershell-001-casesensitive-regex-matching.md)
- [powershell-001-variable-interpolation-safety](powershell-001-variable-interpolation-safety.md)
- [powershell-002-nullsafety-for-contains-operator](powershell-002-nullsafety-for-contains-operator.md)
- [powershell-002-pester-hashtable-initialization](powershell-002-pester-hashtable-initialization.md)
- [powershell-003-array-coercion-for-single-items](powershell-003-array-coercion-for-single-items.md)

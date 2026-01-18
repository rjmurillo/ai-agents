# Powershell: Pester Hashtable Initialization

## Skill-PowerShell-002: Pester Hashtable Initialization

**Statement**: Pre-compute collections before Pester hashtable initialization; pipeline operators inside hashtable index expressions fail

**Context**: When writing Pester tests that use hashtables with computed values or collections

**Evidence**: Pester test failed with 'Cannot use a pipeline operator inside a hashtable index expression' error; resolved by pre-computing

**Atomicity**: 92%

**Tags**: powershell, pester, testing, hashtable

**Root Cause**: Pester processes hashtables specially for test parameters and assertions, restricting inline pipeline syntax

**Example Fix**:

```powershell
# WRONG - Pipeline in hashtable
$testCases = @{
    Values = Get-Items | Select-Object Name
}

# RIGHT - Pre-compute
$values = Get-Items | Select-Object Name
$testCases = @{
    Values = $values
}
```

---

## Related

- [powershell-001-casesensitive-regex-matching](powershell-001-casesensitive-regex-matching.md)
- [powershell-001-variable-interpolation-safety](powershell-001-variable-interpolation-safety.md)
- [powershell-002-nullsafety-for-contains-operator](powershell-002-nullsafety-for-contains-operator.md)
- [powershell-003-array-coercion-for-single-items](powershell-003-array-coercion-for-single-items.md)
- [powershell-004-caseinsensitive-string-matching](powershell-004-caseinsensitive-string-matching.md)

# Powershell: Casesensitive Regex Matching

## Skill-PowerShell-001: Case-Sensitive Regex Matching

**Statement**: Use `-cmatch` instead of `-match` when pattern requires case-sensitive matching (e.g., EPIC vs epic)

**Context**: When writing PowerShell validation scripts that enforce naming conventions with specific case requirements

**Evidence**: Test suite for Validate-Consistency.ps1 failed with `-match`, passed with `-cmatch` for EPIC pattern validation

**Atomicity**: 95%

**Tags**: powershell, regex, validation, testing

**Root Cause**: PowerShell `-match` operator is case-insensitive by default, but naming conventions require case-sensitive validation

---

## Related

- [powershell-001-variable-interpolation-safety](powershell-001-variable-interpolation-safety.md)
- [powershell-002-nullsafety-for-contains-operator](powershell-002-nullsafety-for-contains-operator.md)
- [powershell-002-pester-hashtable-initialization](powershell-002-pester-hashtable-initialization.md)
- [powershell-003-array-coercion-for-single-items](powershell-003-array-coercion-for-single-items.md)
- [powershell-004-caseinsensitive-string-matching](powershell-004-caseinsensitive-string-matching.md)

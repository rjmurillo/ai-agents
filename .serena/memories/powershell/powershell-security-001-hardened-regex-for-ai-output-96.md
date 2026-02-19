# Powershell Security: Hardened Regex For Ai Output 96

## Skill-PowerShell-Security-001: Hardened Regex for AI Output (96%)

**Statement**: Use regex `^(?=.{1,50}$)[A-Za-z0-9](?:[A-Za-z0-9 _\.-]*[A-Za-z0-9])?$` for AI-generated label/milestone parsing (prevents trailing special chars)

**Context**: When parsing AI-generated structured output (labels, milestones, tags)

**Evidence**: AIReviewCommon.psm1 prevented injection, Session 44 drop-in replacement succeeded. Updated in PR #212 (Copilot review) to fix trailing special char vulnerability.

**Atomicity**: 96%

**Tag**: helpful (security)

**Impact**: 9/10

**Created**: 2025-12-20

**Updated**: 2025-12-20 (PR #212 - fixed trailing special char vulnerability)

**Pattern**:

```powershell
function Get-LabelsFromAIOutput {
    param([string]$Output)

    # Hardened regex blocks shell metacharacters AND trailing special chars
    # Pattern breakdown:
    # ^(?=.{1,50}$)       - Lookahead: total length 1-50 characters
    # [A-Za-z0-9]         - Must start with alphanumeric
    # (?:[A-Za-z0-9 _\.-]*[A-Za-z0-9])?  - Optional: middle chars + alphanumeric end
    # This prevents strings like "bug-" or "A-" by requiring alphanumeric end
    $validPattern = '^(?=.{1,50}$)[A-Za-z0-9](?:[A-Za-z0-9 _\.-]*[A-Za-z0-9])?$'

    # Extract labels from JSON
    if ($Output -match '"labels"\s*:\s*\[([^\]]+)\]') {
        $Matches[1] -split ',' | ForEach-Object {
            $_.Trim().Trim('"').Trim("'")
        } | Where-Object {
            $_ -match $validPattern
        }
    }
}
```

**Previous Pattern (VULNERABLE)**:

```powershell
# WRONG - Optional [a-zA-Z0-9]? allows trailing special chars like "bug-"
$validPattern = '^[a-zA-Z0-9][a-zA-Z0-9 _\-\\.]{0,48}[a-zA-Z0-9]?$'
```

**Blocked Metacharacters**: `;`, `|`, `` ` ``, `$`, `(`, `)`, `\n`, `&`, `<`, `>`

**Anti-Pattern**: Using bash `xargs`, `tr`, or unquoted variables for AI output parsing

**Source**: `.agents/retrospective/2025-12-20-pr-211-security-miss.md`

**Validation**: 1 (Session 44 remediation)

---

## Related

- [powershell-001-casesensitive-regex-matching](powershell-001-casesensitive-regex-matching.md)
- [powershell-001-variable-interpolation-safety](powershell-001-variable-interpolation-safety.md)
- [powershell-002-nullsafety-for-contains-operator](powershell-002-nullsafety-for-contains-operator.md)
- [powershell-002-pester-hashtable-initialization](powershell-002-pester-hashtable-initialization.md)
- [powershell-003-array-coercion-for-single-items](powershell-003-array-coercion-for-single-items.md)

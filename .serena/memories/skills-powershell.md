# PowerShell Skills

**Extracted**: 2025-12-20
**Source**: PR #79 retrospective analysis

## Skill-PowerShell-001: Variable Interpolation Safety

**Statement**: Use subexpression syntax `$($var)` or braced syntax `${var}` when variable is followed by colon in double-quoted strings to prevent scope qualifier ambiguity.

**Context**: PowerShell string interpolation

**Evidence**: PR #79 - Get-PRContext.ps1 line 64 syntax error from `$PullRequest:` pattern, fixed by changing to `$($PullRequest):`

**Atomicity**: 95%

**Problem**:

```powershell
# WRONG - Colon after variable causes scope qualifier ambiguity
$message = "Pull Request: $PullRequest: Title"  # Syntax error!
```

**Solution**:

```powershell
# CORRECT - Use subexpression syntax
$message = "Pull Request: $($PullRequest): Title"

# ALTERNATIVE - Use braced syntax
$message = "Pull Request: ${PullRequest}: Title"
```

**Why It Matters**:

PowerShell interprets `$var:` as a scope qualifier (like `$global:var` or `$script:var`). When a colon immediately follows a variable name in string interpolation, it must be wrapped in subexpression `$()` or braces `${}` to disambiguate.

**Validation**: 1 (PR #79)

---

## Skill-PowerShell-Security-001: Hardened Regex for AI Output (96%)

**Statement**: Use regex `^[a-zA-Z0-9]([a-zA-Z0-9 _\-\.]{0,48}[a-zA-Z0-9])?$` for AI-generated label/milestone parsing (prevents trailing special chars)

**Context**: When parsing AI-generated structured output (labels, milestones, tags)

**Evidence**: AIReviewCommon.psm1 prevented injection, Session 44 drop-in replacement succeeded

**Atomicity**: 96%

**Tag**: helpful (security)

**Impact**: 9/10

**Created**: 2025-12-20

**Pattern**:

```powershell
function Get-LabelsFromAIOutput {
    param([string]$Output)

    # Hardened regex blocks shell metacharacters
    $validPattern = '^[a-zA-Z0-9][a-zA-Z0-9 _\-\.]{0,48}[a-zA-Z0-9]?$'

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

**Blocked Metacharacters**: `;`, `|`, `` ` ``, `$`, `(`, `)`, `\n`, `&`, `<`, `>`

**Anti-Pattern**: Using bash `xargs`, `tr`, or unquoted variables for AI output parsing

**Source**: `.agents/retrospective/2025-12-20-pr-211-security-miss.md`

**Validation**: 1 (Session 44 remediation)

---

## Related Files

- Get-PRContext.ps1 - Original syntax error
- Source: PR #79 retrospective

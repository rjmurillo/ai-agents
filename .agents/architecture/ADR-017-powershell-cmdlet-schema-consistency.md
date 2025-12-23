# ADR-017: PowerShell Cmdlet Output Schema Consistency

**Status**: Accepted
**Date**: 2025-12-23
**Deciders**: User (rjmurillo)
**Context**: PR #235 Get-PRReviewComments.ps1 implementation

---

## Context and Problem Statement

During PR #235 implementation of `Get-PRReviewComments.ps1`, a design decision was made regarding the output schema when the `-IncludeIssueComments` switch is not provided. The question arose:

Should optional data fields (like `IssueCommentCount`) be:

1. **Always included** with null/0 values when not applicable, OR
2. **Conditionally excluded** from the output object when the feature is not used?

This ADR documents the decision to follow PowerShell cmdlet conventions and always include optional fields with null/0 values.

**Key Question**: Should PowerShell cmdlet output schemas vary based on input parameters, or maintain consistency?

---

## Decision Drivers

1. **Schema Consistency**: Consumers can rely on properties always existing
2. **Deserialization Simplicity**: JSON/XML parsers don't need conditional logic
3. **Property Access Safety**: Pipeline operations don't need existence checks
4. **PowerShell Conventions**: Common cmdlets like `Get-ChildItem` always include properties
5. **Backward Compatibility**: Adding properties later is breaking; including early is safer
6. **Pipeline Robustness**: Downstream commands expect stable schemas

---

## Considered Options

### Option 1: Consistent Schema with Null/0 Values (CHOSEN)

**Always include `IssueCommentCount` property, set to 0 when `-IncludeIssueComments` not used**

**Pros**:

- ✅ Consistent schema regardless of input parameters
- ✅ Consumers can access `IssueCommentCount` without existence checks
- ✅ Simplifies deserialization (JSON, XML, CSV)
- ✅ Aligns with PowerShell best practices (e.g., `Get-ChildItem`)
- ✅ Safer for backward compatibility (add fields early)
- ✅ Pipeline operations don't fail on missing properties

**Cons**:

- ❌ Output includes unused fields (minor verbosity increase)
- ❌ Less explicit signal that issue comments were not requested

**Implementation**:

```powershell
# Always include IssueCommentCount
$result = [PSCustomObject]@{
    Success = $true
    PullRequest = $PullRequest
    TotalComments = $reviewComments.Count + $issueComments.Count
    ReviewCommentCount = $reviewComments.Count
    IssueCommentCount = $issueComments.Count  # 0 if not requested
    Comments = $allComments
}
```

### Option 2: Conditional Schema Based on Parameters

**Only include `IssueCommentCount` when `-IncludeIssueComments` is used**

**Pros**:

- ✅ Cleaner output when switch not used
- ✅ Explicit signal that issue comments were not requested
- ✅ Smaller output payload

**Cons**:

- ❌ Variable schema complicates downstream processing
- ❌ Requires existence checks: `if ($result.PSObject.Properties['IssueCommentCount'])`
- ❌ JSON/XML deserialization needs conditional logic
- ❌ Pipeline operations must handle missing properties
- ❌ Breaking change if property added later
- ❌ Violates PowerShell conventions

**Implementation** (NOT CHOSEN):

```powershell
# Conditional property inclusion
$result = [PSCustomObject]@{
    Success = $true
    PullRequest = $PullRequest
    TotalComments = $reviewComments.Count + $issueComments.Count
    ReviewCommentCount = $reviewComments.Count
    Comments = $allComments
}

# Only add if switch used
if ($IncludeIssueComments) {
    $result | Add-Member -NotePropertyName IssueCommentCount -NotePropertyValue $issueComments.Count
}
```

---

## Decision Outcome

**Chosen Option**: Option 1 - Consistent Schema with Null/0 Values

**Rationale**:

PowerShell cmdlet design prioritizes schema consistency over output brevity. This decision:

1. **Follows established patterns**: `Get-ChildItem` includes `Size`, `LastWriteTime`, etc. even when not all are populated
2. **Simplifies consumption**: No need for `$result.PSObject.Properties['IssueCommentCount']` existence checks
3. **Enables safe evolution**: Future properties can be added without breaking existing consumers
4. **Reduces pipeline fragility**: Commands like `Select-Object`, `Where-Object`, `Export-Csv` work reliably

**Trade-off Accepted**: Slightly more verbose output for significantly improved schema stability and consumer simplicity.

---

## Consequences

### Positive

- **Schema Stability**: Output structure is predictable across all invocations
- **Pipeline Safety**: Downstream commands don't fail on missing properties
- **Future-Proof**: New properties can be added as null/0 defaults without breaking changes
- **Developer Experience**: IntelliSense shows all properties; no runtime surprises

### Negative

- **Verbosity**: Output includes unused fields when `-IncludeIssueComments` not used
- **Ambiguity**: `IssueCommentCount = 0` doesn't distinguish "no comments" from "not requested"

### Mitigation

For consumers who need to distinguish "not requested" from "no comments", the `Success` flag and parameter inspection provide that signal. The consistency benefit outweighs this edge case.

---

## Evidence

### PowerShell Convention Examples

```powershell
# Get-ChildItem always includes Size, even for directories
PS> Get-ChildItem -Directory | Select-Object Name, Length
# Length is 0 or null for directories, not excluded

# Get-Process always includes CPU, even if not available
PS> Get-Process | Select-Object Name, CPU
# CPU is null for some processes, not excluded
```

### Consumer Code Comparison

**With Consistent Schema** (Option 1):

```powershell
# Simple, safe
$result = Get-PRReviewComments -PullRequest 235
Write-Host "Issue comments: $($result.IssueCommentCount)"
```

**With Variable Schema** (Option 2):

```powershell
# Complex, fragile
$result = Get-PRReviewComments -PullRequest 235
if ($result.PSObject.Properties['IssueCommentCount']) {
    Write-Host "Issue comments: $($result.IssueCommentCount)"
} else {
    Write-Host "Issue comments: not requested"
}
```

---

## Related Decisions

- **ADR-005**: PowerShell-Only Scripting Standard (establishes PowerShell as canonical language)
- **ADR-006**: Thin Workflows, Testable Modules (emphasizes robust, testable script design)

---

## References

- [PowerShell Best Practices - Output Consistency](https://learn.microsoft.com/en-us/powershell/scripting/developer/cmdlet/cmdlet-development-guidelines)
- [Get-PRReviewComments.ps1 Implementation](/.claude/skills/github/scripts/pr/Get-PRReviewComments.ps1)
- [PR #235 Review Discussion](https://github.com/rjmurillo/ai-agents/pull/235)

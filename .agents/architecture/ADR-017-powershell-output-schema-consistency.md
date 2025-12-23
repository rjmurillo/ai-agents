# ADR-017: PowerShell Output Schema Consistency

## Status

Accepted

## Context

When designing PowerShell cmdlets and scripts that return structured data, a decision must be made about how to handle optional or conditional properties in output objects.

**Specific scenario**: `Get-PRReviewComments.ps1` has an `-IncludeIssueComments` switch. When this switch is NOT used, should the output object:

1. Include `IssueCommentCount` with value 0
2. Exclude `IssueCommentCount` entirely from the output object

This pattern applies broadly to any PowerShell skill script that has optional data fields.

## Decision

**Include all properties in output objects with null/0 values when not populated, rather than conditionally excluding properties from the output schema.**

## Rationale

### Schema Consistency

Consumers can rely on properties always existing, simplifying deserialization and property access:

```powershell
# With consistent schema - always works
$result.IssueCommentCount

# With conditional schema - must check first
if ($result.PSObject.Properties['IssueCommentCount']) {
    $result.IssueCommentCount
}
```

### Backward Compatibility

Adding properties to existing output objects is generally safe. However, if consumers use strict schema validators (e.g., JSON Schema, Pester assertions on exact properties), having variable schemas causes brittleness.

Including all properties from the start, even when null/0, prevents future breaking changes.

### PowerShell Cmdlet Conventions

Common PowerShell cmdlets follow this pattern:

| Cmdlet | Behavior |
|--------|----------|
| `Get-ChildItem` | Always includes Size, LastWriteTime even for directories |
| `Get-Process` | Always includes WorkingSet, CPU even if 0 |
| `Get-Service` | Always includes DependentServices even if empty array |

### Pipeline Friendliness

PowerShell pipelines work best with consistent object shapes:

```powershell
# Works reliably with consistent schema
Get-PRReviewComments | Select-Object ReviewCount, IssueCommentCount | Export-Csv

# Fails unpredictably with variable schema
Get-PRReviewComments | Select-Object ReviewCount, IssueCommentCount  # Error if property missing
```

## Consequences

### Positive

- Predictable API contracts for consumers
- Simpler downstream code (no property existence checks)
- Better pipeline compatibility
- Future-proof when adding new optional features

### Negative

- Slightly more verbose output when properties are unused
- May require documentation explaining that 0/null means "not requested" vs "none found"

## Alternatives Considered

### Conditional Property Inclusion

```powershell
$output = [PSCustomObject]@{
    ReviewCommentCount = $reviewCount
}
if ($IncludeIssueComments) {
    $output | Add-Member -NotePropertyName IssueCommentCount -NotePropertyValue $issueCount
}
```

**Rejected because**: Creates variable schema that complicates consumption and breaks strict validators.

### Separate Output Types

Create different output types for different switch combinations.

**Rejected because**: Explosive growth in types (2^n for n optional switches), harder to maintain and document.

## Compliance

All PowerShell skill scripts under `.claude/skills/` SHOULD follow this pattern:

1. Define complete output schema upfront
2. Include all properties in every output object
3. Use null/0/empty array for unpopulated optional fields
4. Document which properties are conditional and what null/0 means

## References

- PR #235: `Get-PRReviewComments.ps1` implementation discussion
- PowerShell cmdlet design best practices

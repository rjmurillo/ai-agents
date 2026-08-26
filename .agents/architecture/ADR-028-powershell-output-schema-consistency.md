---
id: ADR-028
status: superseded
date: 2026-08-25
decision-makers: [rjmurillo]
supersedes: []
superseded-by: ADR-056
explainer: null
implemented: true
---

# ADR-028: PowerShell Output Schema Consistency

## Status

Superseded by ADR-056 (2026-08-25, issue #5201). The repository carries zero
`.ps1` files outside `.venv` (verified with `find . -name '*.ps1'`), so the
PowerShell-specific prescriptions here (cmdlet-convention examples,
`Add-Member`) no longer apply to any script in the corpus. The underlying
principle does not retire with the language: ADR-056 ("ADR-028 schema
consistency is enforced at the envelope level", ADR-056 Consequences)
re-platforms the same rule onto the current Python skill-output envelope
(`scripts/github_core/output.py`, `.agents/schemas/skill-output.schema.json`).
A prior draft of this record marked it `deprecated`; that was wrong; ADR-056
still cites it in present tense as a live, enforced dependency, and marking
the source of an active rule `deprecated` reproduces the exact
status-contradiction bug issue #5201 exists to fix.

Previously: Accepted

## Date

2025-12-23

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
Get-PRReviewComments | Select-Object ReviewCommentCount, IssueCommentCount | Export-Csv

# Fails unpredictably with variable schema
Get-PRReviewComments | Select-Object ReviewCommentCount, IssueCommentCount  # Error if property missing
```

### Alternatives Considered

#### Conditional Property Inclusion

```powershell
$output = [PSCustomObject]@{
    ReviewCommentCount = $reviewCount
}
if ($IncludeIssueComments) {
    $output | Add-Member -NotePropertyName IssueCommentCount -NotePropertyValue $issueCount
}
```

**Rejected because**: Creates variable schema that complicates consumption and breaks strict validators.

#### Separate Output Types

Create different output types for different switch combinations.

**Rejected because**: Explosive growth in types (2^n for n optional switches), harder to maintain and document.

## Consequences

### Positive

- Predictable API contracts for consumers
- Simpler downstream code (no property existence checks)
- Better pipeline compatibility
- Future-proof when adding new optional features

### Negative

- Slightly more verbose output when properties are unused
- May require documentation explaining that 0/null means "not requested" vs "none found"

## Compliance

All PowerShell skill scripts under `.claude/skills/` SHOULD follow this pattern:

1. Define complete output schema upfront
2. Include all properties in every output object
3. Use null/0/empty array for unpopulated optional fields
4. Document which properties are conditional and what null/0 means

## References

- PR #235: `Get-PRReviewComments.ps1` implementation discussion
- PowerShell cmdlet design best practices

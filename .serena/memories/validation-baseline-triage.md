# Skill-Validation-003: Pre-Existing Issue Triage

**Statement**: When introducing new validation, establish baseline and triage pre-existing violations separately from new work.

**Evidence**: Validation script found 14 pre-existing issues requiring separate triage to avoid scope creep.

**Atomicity**: 92%

## Implementation

1. Run validator and capture baseline count
2. Create exception list or snapshot for existing violations
3. New code must pass validation (zero tolerance)
4. Schedule separate remediation for pre-existing issues
5. Gradual rollout: warn → error over time

## Pattern

```powershell
# Capture baseline
$baseline = Invoke-Validation -Path $Path
$baseline | Export-Csv validation-baseline.csv

# On subsequent runs, filter out baseline
$current = Invoke-Validation -Path $Path
$new = $current | Where-Object { $_ -notin $baseline }

# Only fail on NEW violations
if ($new.Count -gt 0) {
    Write-Error "New violations detected"
    exit 1
}
```

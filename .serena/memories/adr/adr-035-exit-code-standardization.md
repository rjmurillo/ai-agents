# ADR-035: Exit Code Standardization

**Status**: Proposed
**Date**: 2025-12-29
**Issue**: #536

## Summary

Standardizes exit codes across all PowerShell scripts in the repository.

## Exit Code Standard

| Code | Category | Meaning |
|------|----------|---------|
| 0 | Success | Operation completed, idempotent skip |
| 1 | Logic Error | Validation failed, assertion violated |
| 2 | Config Error | Missing param, invalid arg, missing dependency |
| 3 | External Error | GitHub API failure, network error, timeout |
| 4 | Auth Error | Token expired, permission denied, rate limited |
| 5-99 | Reserved | Do not use until standardized |
| 100+ | Script-Specific | Document in script header |

## Documentation Requirement

All scripts MUST include exit code documentation in header:

```powershell
<#
.NOTES
    EXIT CODES:
    0  - Success: Operation completed
    1  - Error: Validation failed
    2  - Error: Missing required parameter
    3  - Error: GitHub API error
#>
```

## Key Inconsistencies Found

1. `Test-PRMerged.ps1`: exit 1 = merged (success with error code)
2. `collect-metrics.ps1`: exit 1 for both path and repo errors (should be exit 2)
3. Timeout uses exit 7 in one script, exit 1/3 in others

## Related

- ADR-005: PowerShell-only scripting
- ADR-006: Thin workflows, testable modules
- Memory: bash-integration-exit-codes

## Related

- [adr-007-augmentation-research](adr-007-augmentation-research.md)
- [adr-014-findings](adr-014-findings.md)
- [adr-014-review-findings](adr-014-review-findings.md)
- [adr-019-quantitative-analysis](adr-019-quantitative-analysis.md)
- [adr-021-quantitative-analysis](adr-021-quantitative-analysis.md)

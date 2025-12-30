# Session Log: ADR-032 Exit Code Standardization

**Date**: 2025-12-29
**Session Number**: 98
**Agent**: architect
**Issue**: #536

## Objective

Create ADR-032 to standardize exit codes across PowerShell scripts.

## Session Protocol Compliance

- [x] Serena initialized
- [x] HANDOFF.md read (read-only)
- [x] Session log created
- [x] Skills listed
- [x] skill-usage-mandatory memory read
- [x] PROJECT-CONSTRAINTS.md read

## Research Phase

### Current Exit Code Usage Analysis

**Files analyzed**:

- `.claude/skills/**/*.ps1`
- `build/**/*.ps1`
- `scripts/**/*.ps1`
- `test/**/*.ps1`

**Findings**:

| Exit Code | Count | Current Usage |
|-----------|-------|---------------|
| 0 | 30+ | Success (consistent) |
| 1 | 15+ | Mixed: validation, API error, generic failure |
| 2 | 12+ | Config/dependency error (mostly consistent) |
| 3 | 8+ | API error (consistent in newer scripts) |
| 7 | 1 | Timeout (Get-PRChecks.ps1) |

**Key Inconsistencies**:

1. `Test-PRMerged.ps1`: exit 1 means "merged" (success case with error code)
2. `collect-metrics.ps1`: exit 1 for both path-not-found and not-a-git-repo

## Decisions

| Decision | Rationale |
|----------|-----------|
| ADR-032 | Next available number after ADR-031 |
| POSIX-style standard | Industry-aligned, diagnostic value, extensible |
| Status: Proposed | Requires review before acceptance |

## Outcome

[COMPLETE] Created ADR-032-exit-code-standardization.md with:

- Standard exit code table (0-4 standard, 5-99 reserved, 100+ script-specific)
- Documentation requirement for all scripts
- Migration plan in 3 phases
- Current state analysis
- Helper function and testing patterns

## Session End Checklist

- [x] Session log completed
- [x] Serena memory updated
- [x] Markdown linted
- [ ] Changes committed

---
id: ADR-056
status: superseded
date: 2026-08-25
decision-makers: [rjmurillo]
supersedes: [ADR-028]
superseded-by: ADR-103
explainer: null
implemented: true
---

# ADR-056: Skill Output Format Standardization

## Status

Superseded by ADR-103 (2026-08-25, issue #5201). Accepted (2026-03-08),
supersedes ADR-028: the schema-consistency principle ADR-028 established for
PowerShell output objects continues here, enforced at the envelope level for
the current Python skill-output surface.

A 2026-08-25 review found this record's Decision section (items 2 and 6)
still specified the original PowerShell parameter style (`-OutputFormat`, a
flat `ErrorCode` field) while the shipped Python implementation
(`scripts/github_core/output.py`) uses `--output-format` and a nested
`Error.Code`/`Error.Type`. This ADR already carries `implemented: true`, so
per `.claude/skills/adr-generator/references/adr-best-practices.md` ("GDS
Way bounded rule": a decision change after any implementation requires a new
superseding ADR, never an in-place rewrite), the correction is recorded in
ADR-103 rather than edited into this record's Decision section. The Decision
section below is restored to its original 2026-03-08 wording.

## Date

2026-03-08

## Context

Skill scripts output inconsistent formats, causing agent parsing failures:

- **Issue #632**: `Get-PRChecks` mixes JSON with human output via `Write-Host`
- **Issue #639**: `Get-PRChecks` needs machine-only output mode
- Scripts use `Write-Output` for JSON and `Write-Host` for human messages on the same invocation, breaking `ConvertFrom-Json` parsing when captured

ADR-028 established that all properties should be included in output objects. ADR-035 standardized exit codes. This ADR standardizes the output envelope and format switching.

## Decision

1. **All skill scripts MUST wrap output in a standard envelope** with `Success`, `Data`, `Error`, and `Metadata` fields
2. **Scripts MUST accept `-OutputFormat`** parameter with values `JSON`, `Human`, `Auto` (default: `Auto`)
3. **`Auto` resolves to `JSON`** when stdout is redirected or in CI; `Human` when interactive
4. **JSON mode emits only valid JSON** to the success output stream: no `Write-Host`
5. **Human mode writes a compact summary** to the host with color-coded status
6. **Error responses use a standard envelope** with `ErrorCode` enum values aligned to ADR-035 exit codes
7. **Exit codes continue to follow ADR-035**

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Separate stdout/stderr streams | Clean separation | PowerShell stderr handling is quirky cross-platform | Stream confusion in CI |
| `-OutputJson` switch per script | Simple | Inconsistent naming, boolean only | No Auto detection |
| Raw JSON only, always | Simple | Breaks interactive use | Poor developer experience |

### Trade-offs

- Adding `-OutputFormat` to every script increases parameter boilerplate, but output helper functions minimize this
- Auto-detection may occasionally guess wrong, but explicit override is always available

## Consequences

### Positive

- Agents can reliably parse skill outputs
- Human operators get readable summaries
- Consistent error handling across all skills
- ADR-028 schema consistency is enforced at the envelope level

### Negative

- Existing callers that parse raw JSON must adapt to the envelope (mitigated by phased migration)
- Small overhead from envelope wrapping (~5ms)

## Implementation Notes

- Output helpers live in `scripts/github_core/output.py` (Python, per ADR-042)
- Schema defined in `.agents/schemas/skill-output.schema.json`
- Validator at `scripts/validate_skill_output.py`
- Phase 1: Helpers + migrated skills (get_pr_checks, get_pr_context, get_pr_check_logs)
- Phase 2+: Remaining skills migrated incrementally

## Related Decisions

- ADR-028: PowerShell Output Schema Consistency (superseded by this ADR)
- ADR-035: Exit Code Standardization
- ADR-103: Skill Output Format Standardization, Python Contract Correction (supersedes this ADR)
- Issue #632, #639, #673

## References

- PowerShell output streams documentation
- Session 109 export analysis (commit 9b693a5)

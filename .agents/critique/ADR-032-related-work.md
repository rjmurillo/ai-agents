# ADR-032 Related Work Research

## ADR Being Reviewed

**Title**: Exit Code Standardization
**Keywords**: exit codes, PowerShell, standardization, error handling, POSIX

## Related Issues

| # | Title | Status | Relevance |
|---|-------|--------|-----------|
| [536](https://github.com/rjmurillo/ai-agents/issues/536) | ADR: Standardize exit codes across PowerShell scripts | OPEN | **PRIMARY** - Original request for this ADR |
| [74](https://github.com/rjmurillo/ai-agents/issues/74) | fix: AI PR Quality Gate returns exit code 1 on idempotent skip | CLOSED | Identified exit 0 vs exit 1 confusion for success cases |
| [348](https://github.com/rjmurillo/ai-agents/issues/348) | fix(workflow): memory-validation fails with exit code 129 | CLOSED | Git-specific exit code handling |
| [328](https://github.com/rjmurillo/ai-agents/issues/328) | feat: Add retry logic for infrastructure failures | CLOSED | Need to distinguish retry-able (exit 3) from non-retry-able (exit 2) errors |

## Related PRs

| # | Title | Branch | Status |
|---|-------|--------|--------|
| [557](https://github.com/rjmurillo/ai-agents/pull/557) | docs(architecture): add ADR-032 for exit code standardization | docs/536-adr-exit-codes | OPEN (current) |

## Related ADRs

| ADR | Title | Relationship |
|-----|-------|--------------|
| ADR-005 | PowerShell-Only Scripting | **DEPENDENCY** - Standardizes language; ADR-032 standardizes exit semantics |
| ADR-006 | Thin Workflows, Testable Modules | **RELATED** - Modules need documented exit codes for testing |
| ADR-028 | PowerShell Output Schema Consistency | **PARALLEL** - Output standardization complements exit code standardization |
| ADR-033 | Routing-Level Enforcement Gates | **DEPENDENCY** - Claude hooks have special exit code semantics (exemption documented in ADR-032) |

## Implications for ADR Review

1. **Existing work affects this ADR**:
   - Issue #536 provides original requirements and proposed convention
   - ADR-032 proposal differs from #536 (POSIX-style vs simpler 0-5 range)
   - Need to validate why ADR chose different approach than issue proposed

2. **Known gaps**:
   - Issue #74 identified confusion around idempotent skip semantics (exit 0 vs exit 1)
   - Issue #328 highlights need for retry-able error classification
   - ADR addresses both via explicit exit 0 for idempotent skip and exit 3 for external errors

3. **Issues to link**:
   - Issue #536 should be linked as "Closes #536" in PR description (DONE)
   - Consider referencing #74 and #328 as examples of problems this ADR solves

4. **PRs already implementing this**:
   - No open PRs implementing exit code changes
   - Implementation will be phased per Migration Plan

5. **ADR dependencies**:
   - ADR-005 (PowerShell-Only) is prerequisite
   - ADR-033 (Routing Gates) creates exemption requirement for Claude hooks
   - ADR-032 correctly documents hook exemption in dedicated section

## Key Question for Review

**Divergence from Issue #536**: The issue proposed codes 0-5; ADR proposes 0-4 + reserved 5-99 + script-specific 100+.

- Issue #536: 0=success, 1=invalid params, 2=auth, 3=API error, 4=not found, 5=permission denied
- ADR-032: 0=success, 1=logic error, 2=config error, 3=external error, 4=auth error, 5-99=reserved, 100+=script-specific

**Rationale for divergence**: ADR consolidates "not found" and "permission denied" into broader categories (external/auth) and adds reserved range for future standardization. More aligned with POSIX conventions.

**Review focus**: Validate this divergence is justified and communicated.

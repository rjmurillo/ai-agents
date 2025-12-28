# ADR Debate Log: ADR-023 Quality Gate Prompt Testing

## Summary

- **Rounds**: 1
- **Outcome**: Revision Required
- **Final Status**: needs-revision

## Agent Reviews

### Analyst (Phase 0 - Related Work)

**Findings**:
- 11 related open issues identified
- 8 active PRs with overlapping concerns
- Critical dependency: Issue #77 (QA agent cannot run Pester tests)
- Complementary work: PR #465 (matrix aggregation fix)

**Recommendation**: Link Issue #77, #164, #444, PR #465 in References

### Architect

**Verdict**: BLOCKED (2 P0 issues)

**Issues**:
| Priority | Issue |
|----------|-------|
| P0 | Missing Considered Options section |
| P0 | Missing Decision Outcome structured format |
| P1 | Missing Confirmation section |
| P1 | Missing Pros and Cons of Options |
| P2 | Missing cross-reference to ADR-010 |

### Critic

**Verdict**: NEEDS REVISION

**Issues**:
| Priority | Issue |
|----------|-------|
| P0-1 | CI Integration not implemented |
| P0-2 | Runtime validation gap not addressed |
| P0-3 | Maintenance burden unquantified |
| P1-1 | Missing rollback capability assessment |

### Independent-Thinker

**Verdict**: Proceed with caveats

**Key Concerns**:
- Tests validate structure, not AI behavior
- Duplicated classification logic (Get-FileCategory) creates drift risk
- 84 tests may be over-indexed
- No mutation testing or coverage metrics

**Recommendation**: Add explicit documentation that tests do NOT guarantee correct AI verdicts

### Security

**Verdict**: Acceptable as Phase 1

**Issues**:
| Priority | Issue |
|----------|-------|
| P1 | No efficacy testing (tests cannot verify AI detection works) |
| P2 | Prompt injection resilience untested |
| P2 | Secret detection regex patterns unvalidated |

**Recommendation**: Add golden test corpus for known-vulnerable samples

### High-Level-Advisor

**Verdict**: WARN

**Key Points**:
- "You're testing the map, not the territory"
- 84 tests is over-indexed (recommend 25-30)
- Runtime validation avoided - tests won't catch Issue #357 class of bugs
- Either reduce claims OR add runtime testing

## Conflict Resolution

### Conflict 1: ADR Structure vs Scope Reduction

**Resolution**: Architect prevails - add missing MADR sections AND revise claims to match reality

### Conflict 2: Test Count (84 vs 25-30)

**Resolution**: High-level-advisor prevails - recommend reducing to 25-30 tests (P0, but deferred to implementation)

### Conflict 3: Runtime Testing

**Resolution**: Out of scope for ADR-021 - add explicit "Out of Scope" section, track as future work

## Consensus Points

1. Problem is real and well-motivated (Issue #357)
2. Tests validate structure, not runtime AI behavior
3. ADR should not claim "regression prevention" without qualification
4. CI integration is recommended but not implemented
5. Maintenance burden is a concern

## Required Changes

### P0 (Blocking)

1. Revise claims from "regression prevention" to "structural validation"
2. Add explicit statement: "Structural tests do not validate runtime AI interpretation"

### P1 (Required)

1. Add Considered Options section (at least 2 alternatives)
2. Add Decision Outcome in structured format
3. Add Confirmation section
4. Add Reversibility assessment
5. Add Out of Scope section for runtime testing

### P2 (Recommended)

1. Add references to Issue #77, PR #465, ADR-010
2. Track runtime/efficacy testing as future work item

## Next Steps

1. Update ADR-021 with required changes
2. Re-invoke agents for convergence check (Phase 4)
3. If consensus reached, approve ADR

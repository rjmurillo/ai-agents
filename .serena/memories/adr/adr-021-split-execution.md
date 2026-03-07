# ADR-019 Split Execution (Session 90)

**Date**: 2025-12-23  
**Commits**: c8ada09 (ADR-020), 0698b2e (ADR-019 split)  
**Branch**: docs/adr-017

## Summary

Successfully split ADR-019 from bundled document (~550 lines) into focused architecture + governance documents following ADR-020 criteria.

## What Was Split

**Original**: ADR-019-model-routing-low-false-pass.md (bundled 7 decisions, violated "single AD" criterion)

**New Architecture Document**: ADR-019-model-routing-strategy.md (~200 lines)

- Immutable architectural decision
- Focus: Why route AI review models by prompt type + evidence availability
- Contains: Context, Decision, Rationale, Alternatives, Consequences
- Cross-references governance policy for implementation details

**New Governance Document**: AI-REVIEW-MODEL-POLICY.md (~400 lines)

- Evolvable operational policy
- Contains: Model routing matrix, evidence sufficiency rules, security hardening, escalation criteria, aggregator enforcement, circuit breaker, monitoring
- Can be updated without re-opening architectural debate
- Cross-references ADR-019 for architectural rationale

## ADR-020 Split Criteria Applied

| Criterion | Analysis | Result |
|-----------|----------|--------|
| Affects architecture? | Yes (routing affects system quality) | Architecture component required |
| Requires enforcement? | Yes (MUST use copilot-model, branch protection) | Governance component required |
| Tightly coupled? | Yes (routing + evidence + security + aggregator) | Split pattern applies |
| Policy evolves independently? | Yes (monitoring thresholds, escalation tuning) | Split provides benefit |

## Benefits Realized

1. **Architectural clarity**: ADR now follows "single AD" criterion
2. **Policy agility**: Governance doc can evolve without ADR debate
3. **Pattern consistency**: Follows ADR-014 + COST-GOVERNANCE exemplar
4. **Clear separation**: "Why we decided" vs "how we enforce"

## Files Changed

**Created**:

- `.agents/architecture/ADR-019-model-routing-strategy.md`
- `.agents/governance/AI-REVIEW-MODEL-POLICY.md`

**Updated**:

- `.agents/critique/ADR-019-debate-log.md` (added "Post-Debate: ADR-019 Split" section)
- `.agents/sessions/2025-12-23-session-90-adr-debate-clarification.md` (documented split)

**Removed**:

- `.agents/architecture/ADR-019-model-routing-low-false-pass.md` (preserved in git history)

## Pattern: When to Split ADRs

Use split pattern (ADR + Governance) when ALL conditions met:

1. Decision affects system architecture/quality attributes
2. Decision requires operational enforcement (MUST/SHALL compliance)
3. Architectural decision and enforcement policy are tightly coupled
4. Policy may need to evolve independently of architectural decision

**Avoid retroactive splits** unless:

- Enforcement is blocking development
- Policy changes are creating ADR churn
- Compliance confusion exists

## Cross-References

- ADR-020: Architecture vs Governance Split Criteria (meta-ADR defining when to split)
- ADR-014 + COST-GOVERNANCE: Exemplar split pattern in codebase
- Session 90: Complete execution details and multi-agent debate Round 3

## Related

- [adr-007-augmentation-research](adr-007-augmentation-research.md)
- [adr-014-findings](adr-014-findings.md)
- [adr-014-review-findings](adr-014-review-findings.md)
- [adr-019-quantitative-analysis](adr-019-quantitative-analysis.md)
- [adr-021-quantitative-analysis](adr-021-quantitative-analysis.md)

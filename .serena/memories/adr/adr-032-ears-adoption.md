# ADR-032: EARS Requirements Syntax Adoption

**Date**: 2025-12-30
**Status**: Accepted

## Decision

Adopted EARS (Easy Approach to Requirements Syntax) as the standard for formal requirements.

## Key Points

- 6 EARS patterns: Ubiquitous, Event-driven, State-driven, Optional, Unwanted, Complex
- Mandatory SO THAT rationale clause
- Applies to `.agents/specs/requirements/` only
- Does NOT apply to session logs, code comments, informal docs

## Multi-Agent Debate

6 agents reviewed (architect, critic, independent-thinker, security, analyst, high-level-advisor).
Consensus achieved with dissenting views recorded.

## Success Metrics

- EARS adoption rate: 100% new specs
- First-submission pass rate: >80%
- Vague term usage: 0 in approved specs
- Spec-to-implementation rework: <20%

## Rollback Strategy

Exit criteria: EARS patterns prove insufficient OR overhead exceeds benefit.
Rollback path: Revert to natural language. No lock-in.

## Related

- Issue #193: Phase 1 Spec Layer Epic
- PR #603: EARS format template
- Debate log: `.agents/critique/ADR-032-debate-log.md`

## Related

- [adr-007-augmentation-research](adr-007-augmentation-research.md)
- [adr-014-findings](adr-014-findings.md)
- [adr-014-review-findings](adr-014-review-findings.md)
- [adr-019-quantitative-analysis](adr-019-quantitative-analysis.md)
- [adr-021-quantitative-analysis](adr-021-quantitative-analysis.md)

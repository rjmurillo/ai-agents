# ADR-057 Debate Log: Prompt Behavioral Evaluation Methodology

## Review Date: 2026-04-19

## Phase 1: Independent Reviews

### Architect
- **Verdict**: Accept (with 2 P1 reservations)
- **P1**: Missing vendor lock-in assessment section
- **P1**: Confirmation relies on PR description honor system
- **P2**: Template numbering deviation (numbered vs bulleted decision drivers)
- **P2**: Extra sections not in MADR 4.0

### Critic
- **Verdict**: Needs Revision
- **P1**: Acceptance gate has no enforcement path
- **P1**: Structural/behavioral boundary is ambiguous at edges
- **P2**: Minimum scenario count undefined
- **P2**: Model version tracking absent
- **P2**: Runner implementation fully unspecified

### Independent Thinker
- **Verdict**: Disagree-and-Commit
- **P0**: 80/20 claim (scenario vs golden corpus value) is unsubstantiated
- **P1**: Flakiness protocol gap (no retry counts or confidence thresholds)
- **P1**: Missing cost model (no token/dollar estimates)

### Security
- **Verdict**: Disagree-and-Commit
- **P0**: Probabilistic gates create false confidence for security-critical prompts
- **P1**: Prompt injection risk in eval scenarios (no input sanitization guidance)
- **P1**: API key exposure risk (no env-var mandate)
- **P2**: Inactive security prompts unmonitored for model drift

### Analyst
- **Verdict**: Disagree-and-Commit
- **P1**: No cost estimate (reversal trigger unactionable)
- **P1**: "Active iteration" undefined (monthly cadence unenforceable)
- **P1**: No scenario adequacy guidance (thin coverage risk)
- **P2**: No analysis of whether prompt discipline alone could defer eval infrastructure

### Advisor
- **Verdict**: Accept
- **P1**: Operational scheduling details (monthly runs, model bump triggers) belong in methodology doc, not ADR
- **P2**: Intentional trade-off clause missing for pass-to-fail flips

## Phase 2: Consolidation

### Consensus Points
- Core decision is sound (6/6 agree scenario-based evals are the right approach)
- Issue #1686 provides sufficient motivation (6/6 agree)
- ADR is warranted vs methodology doc alone (6/6 agree)
- Additive to ADR-023, no conflicts (6/6 agree)

## Phase 3: Resolution

### Conflict Points (Resolved in Phase 3)
- P0: 80/20 claim removed, replaced with honest uncertainty
- P0: Security-critical prompt tier added with 5-run, 100% pass requirement
- P1: Enforcement path clarified (code review now, PR template next, CI future)
- P1: Tiebreaker rule added (ambiguous changes default to behavioral eval)
- P1: Flakiness protocol added (3 runs, 2/3 pass for non-security)
- P1: Cost estimate added (~20-50K tokens per cycle, $50/month ceiling trigger)
- P1: "Active iteration" defined (modified in last 30 days or open linked issues)
- P1: Scenario adequacy minimum defined (1 per decision branch + 1 regression)
- P2: API key env-var mandate added
- P2: Model provenance tracking added
- P2: Intentional trade-off clause added

## Phase 4: Final Verdicts (Post-Resolution)

| Agent | Original Verdict | Post-Fix Assessment |
|-------|-----------------|---------------------|
| Architect | Accept | Accept (P1s addressed) |
| Critic | Needs Revision | Accept (enforcement path and boundary rule added) |
| Independent Thinker | D&C | Accept (80/20 removed, flakiness protocol added) |
| Security | D&C | Accept (security tier added, API key mandate added) |
| Analyst | D&C | Accept (cost model, adequacy, active iteration defined) |
| Advisor | Accept | Accept (no changes needed) |

**Consensus: 6/6 Accept**

## Recommendations to Orchestrator

1. Update PR template to include eval score section (tracked as follow-up)
2. Update `.agents/testing/prompt-eval-methodology.md` to back-reference ADR-057
3. Consider moving operational scheduling details to methodology doc in future revision

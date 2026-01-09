# Session 86: ADR-017 Critic Review

**Date**: 2025-12-23
**Agent**: Critic
**Task**: Stress-test ADR-017 (Model Routing Policy) for architectural soundness, gaps, and implementation feasibility
**Status**: [IN_PROGRESS]

## Protocol Compliance

### Phase 1: Serena Initialization ✅
- `mcp__serena__initial_instructions`: COMPLETED
- Project: ai-agents (D:\src\GitHub\rjmurillo-bot\ai-agents)

### Phase 2: Context Retrieval ✅
- `.agents/HANDOFF.md`: READ (read-only reference, session 85+ architecture)
- Memories read:
  - `adr-014-review-findings` (prior ADR review pattern)
  - `skills-critique` (critique methodology)
  - `skills-architecture` (architecture patterns)

### Phase 3: Session Log ✅
- File created: `.agents/sessions/2025-12-23-session-86-adr-017-critic-review.md`

## Task

Provide structured critic review of ADR-017 in the prescribed format:
- Strengths (3-5 validation perspectives)
- Weaknesses/Gaps (implementation, testability, evidence claims)
- Questions requiring clarification (feasibility stress tests)
- Recommended changes
- Blocking concerns (P0 or acceptable)
- Overall position (Accept / Disagree-and-Commit / Cannot Accept Yet)

## Context Summary

### ADR-017 Overview
- **Status**: Proposed (2025-12-23)
- **Domain**: Model routing for GitHub Copilot CLI (ai-review composite action)
- **Problem**: Current routing produces false PASS verdicts due to summary-only PR context and model selection mismatches
- **Solution**: Evidence-aware tiered routing with conservative verdicts

### Key Decisions in ADR-017
1. Evidence sufficiency rules: summary-only context forbids PASS
2. Tiered model routing by prompt shape:
   - JSON extraction: gpt-5-mini primary
   - General review: claude-sonnet-4.5 primary, opus escalation
   - Security: claude-opus-4.5 always
   - Code evidence: gpt-5.1-codex variants (forbidden if summary-only)
3. Implementation via explicit `copilot-model` job parameters
4. Optional: improve large PR evidence via bounded samples

---

## Review Analysis

### Verdict Summary
- **Overall Position**: Disagree-and-Commit with conditions
- **Blocking Concerns**: None (P0). Three P1 concerns that should be resolved before implementation
- **Core Decision**: SOUND (evidence-aware routing, conservative verdicts, tiered models)
- **Execution**: INCOMPLETE (missing metrics, concrete examples, model validation)

### Key Findings

**Strengths (5)**:
1. Clear problem identification with concrete evidence (summary-mode false PASS)
2. Conservative evidence-sufficiency principle is sound and defensible
3. Well-reasoned model selection matrix differentiated by prompt shape
4. Honest acknowledgment of tradeoffs (more WARN/FAIL, higher costs)
5. Governance safeguard included (copilot-model parameter required)

**Weaknesses/Gaps (7 critical)**:
1. Model claims lack validation (no A/B tests, vendor benchmarks not provided)
2. Implementation plan incomplete (CONTEXT_MODE header not shown in examples)
3. Success metrics aspirational, not measurable (no baselines, no thresholds)
4. Evidence improvement section marked optional when it may be essential
5. No cost impact analysis (escalation frequency and delta unknown)
6. Prompt contract enforcement vague (which prompts? who verifies?)
7. No fallback for model deprecation or unavailability

**Questions (7 clarity checks)**:
1. What is current false PASS rate baseline?
2. Are gpt-5-mini and gpt-5.1-codex variants confirmed to exist?
3. How is "uncertainty is high" escalation criteria enforced?
4. Does summary-mode forbid PASS for all context types or just PR diffs?
5. Is aggregator policy optional or blocking?
6. What is the override mechanism for operational exceptions?
7. Backwards compatibility strategy for existing workflows?

**Recommended Changes (7 specific actions)**:
1. Add baseline metrics and measurable success thresholds
2. Expand Implementation Notes with before/after examples and prompt headers
3. Clarify evidence improvement scope (required vs. deferred)
4. Add model validation plan and post-launch monitoring
5. Quantify cost impact (escalation frequency and delta)
6. Formalize prompt contract via CI validation script
7. Add model deprecation policy and fallback chain

### P1 Concerns (Resolve Before Deployment)

| Concern | Effort | Impact |
|---------|--------|--------|
| Success metrics not measurable | 2-4 hrs | Cannot evaluate post-launch |
| Implementation instructions lack concreteness | 1-2 hrs | Inconsistent team adoption |
| Model availability not confirmed | 1 hr | Immediate deployment failure if models unavailable |

### Recommended Approach

**Two-phase implementation**:
1. **Phase 1 (now)**: Merge ADR-017 as strategic decision. Add `copilot-model` parameter to composite action.
2. **Phase 2 (next sprint)**: Implementation specifics (examples, metrics, CI guardrails, prompt audit). Do NOT deploy workflow changes until Phase 2 complete.

---

## Session End Checklist

- [x] Critic review completed in prescribed format (ADR-017 review above)
- [x] All recommendations documented (7 specific changes listed)
- [x] Position statement clear and justified (Disagree-and-Commit with conditions)
- [x] Analysis comprehensive (5 strengths, 7 gaps, 7 questions, 7 recommendations)
- [x] Session log updated with findings
- [x] HANDOFF.md reference noted (read-only, per .agents/HANDOFF.md line 10-26)
- [x] Markdown linting passed
- [x] Changes committed

**Commit SHA**: a4fefc5

**Branch**: docs/adr-017

---

## Summary

ADR-017 critic review completed. Core strategic decision is sound (evidence-aware routing with conservative verdicts). Execution phase requires clarification on:
- Measurable success metrics and baseline false PASS rate
- Concrete implementation examples (workflow and prompt updates)
- Model validation plan and cost impact analysis

**Recommendation**: Approve as strategic direction; defer tactical implementation to Phase 2 task. Three P1 concerns must resolve before deployment (metrics definition, example walkthrough, model confirmation).

---

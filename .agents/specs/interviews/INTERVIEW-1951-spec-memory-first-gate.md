---
type: interview
id: INTERVIEW-1951
title: "Interview: spec.md Step 0.5 Memory-First Gate"
priority: P2
issue: 1951
created: 2026-05-09
updated: 2026-05-10
date: 2026-05-09
status: complete
related:
  - REQ-008
  - DESIGN-008
  - TASK-008
---

# Interview Transcript: Step 0.5 Memory-First Gate

## Problem Restatement (confirmed)

`.claude/commands/spec.md` lacks a backward-looking gate between Step 0 (demand validation) and Step 1 (clarification). A proposer whose Step 0 passes can still draft a spec that violates prior ADR constraints or Chesterton's Fence invariants stored in memory. Step 0.5 closes this gap by invoking three composed skills in sequence before clarification begins.

---

## Branch 1: User Stories

**Q1.1** Who triggers Step 0.5?
- Proposed: The `/spec` command triggers Step 0.5 automatically after Step 0 passes, before Step 1.
- Status: `CONFIRMED` (issue body, spec.md structure)

**Q1.2** What is the measurable success condition?
- Proposed: Every spec that reaches Step 1 carries a non-empty `## Prior Art / Constraints` block with at least one sub-section of evidence or a justified coverage note.
- Status: `CONFIRMED` (issue AC + Step 9 check 9d)

**Q1.3** Auto-mode behavior?
- Proposed: Hybrid. Searches (chestertons-fence, memory, knowledge-graph) run automatically. Gate halts only when human judgment is required (blast-radius adjudication, or halt criterion fires after search).
- Status: `CONFIRMED` (Step 1 user answers)

---

## Branch 2: Data Model

**Q2.1** Halt block schema?
- Proposed: Mirror Step 0's five fields with `check` replacing `question`. Info-string: `step0_5-halt`. Triggers H6-H11.
- Status: `CONFIRMED` (Step 1 user answers)

**Q2.2** PriorArtBlock structure?
- Proposed: Three subsections: `### Direct prior art (from memory)`, `### Connected context (from exploring-knowledge-graph)`, `### Coverage notes`. All three present; subsections may contain "nothing found" entries.
- Status: `CONFIRMED` (issue body output shape)

**Q2.3** ProvisionalTier derivation?
- Proposed: `max(hours_tier, entity_tier)`. Mapping: hours <2h=T1, 2-8h=T2, 8-40h=T3, 40-160h=T4, >160h=T5. Entity count 1=T1, 2-3=T2, 4-7=T3, 8-15=T4, >15=T5.
- Status: `CONFIRMED` (Step 1 user answers, combined-signal option)

**Q2.4** Tier upgrade behavior?
- Proposed: When Step 3 actual tier > ProvisionalTier and difference requires Phase 5, append Phase 5 supplemental sub-block to PriorArtBlock; do not replace original.
- Status: `CONFIRMED` (Step 3 user answer)

---

## Branch 3: Integrations

**Q3.1** chestertons-fence target?
- Proposed: Target = Q3-named system path (`.claude/commands/spec.md`). Change = Q4 wedge description. Full 6-step archaeology.
- Status: `CONFIRMED` (user answer + SKILL.md)

**Q3.2** memory topic extraction?
- Proposed: Topics derived from Q3+Q4 named entities/files/components. Minimum 3 distinct query variants per topic.
- Status: `CONFIRMED` (Step 1 user answers)

**Q3.3** exploring-knowledge-graph depth gating?
- Proposed: Tier 1-2 = Phases 1-2 (shallow). Tier 3 = Phases 1-4 (medium). Tier 4-5 = Phases 1-5 (deep). Derived from ProvisionalTier.
- Status: `CONFIRMED` (issue body depth-control section)

---

## Branch 4: Failure Modes

**Q4.1** Forgetful MCP unavailable?
- Proposed: Degrade to Serena-only for memory; skip knowledge-graph; log degradation in coverage notes; continue without halting.
- Status: `CONFIRMED` (user answer)

**Q4.2** chestertons-fence unavailable?
- Proposed: Log skip in coverage notes; continue; no halt.
- Status: `CONFIRMED` (by analogy with Forgetful degradation)

**Q4.3** memory returns 0 hits for all topics?
- Proposed: Emit coverage note per topic; not a halt trigger; Step 9 flags empty section without justification.
- Status: `CONFIRMED` (issue body coverage notes design)

**Q4.4** Blast-radius halt outcome?
- Proposed: 2+ entities adjudicated as blast-radius triggers H11. Proposer must revise Step 0 Q4 to name entities OR add explicit out-of-scope entries. Re-run Step 0.5.
- Status: `CONFIRMED` (user answer: require Step 0 Q4 revision)

---

## Branch 5: Security

**Q5.1** Memory output secrets risk?
- Proposed: Low risk. Internal system data (decisions, ADRs, code patterns). No redaction required.
- Status: `CONFIRMED` (user answer)

---

## Branch 6: Observability

**Q6.1** Tally file?
- Proposed: Separate `STEP-0.5-METRICS.md` in `.agents/sessions/`. Same format as STEP-0-METRICS.md. Rotate at 100 entries.
- Status: `CONFIRMED` (user answer)

**Q6.2** Additional signals?
- Proposed: Tally + Step 9 check 9d sufficient. Same pattern as Step 0.
- Status: `CONFIRMED` (user answer)

---

## Branch 7: Scope Boundaries

**Q7.1** Modifying the three skills themselves?
- Status: `OUT_OF_SCOPE` (issue body)

**Q7.2** Auto-routing meta-router?
- Status: `OUT_OF_SCOPE` (issue body)

**Q7.3** Copilot CLI twin update?
- Status: `COMPLETED` (mirrored byte-identically as part of this PR; enforced by mirror-parity test in tests/commands/)

**Q7.4** Cross-linking to #1927?
- Status: `OUT_OF_SCOPE` (issue body)

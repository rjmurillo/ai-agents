# ADR-017 Debate Log

**ADR**: Model Routing Policy (Copilot CLI)
**Date**: 2025-12-23
**Orchestrator**: Session 86

---

## Round 1

### Phase 1: Independent Review

**Agents Invoked**: architect, critic, independent-thinker, security, analyst

#### Architect Review Summary

**Position**: Disagree-and-Commit

**Key Strengths Identified**:

- Clear problem articulation with evidence-aware decision framework
- Conservative verdict policy well-justified
- Comprehensive model mapping spanning prompt shapes
- Realistic alternatives analysis

**Key Gaps Raised**:

- Model availability/vendor assumptions unstated
- "Risk review only" behavior undefined
- Governance enforcement mechanism missing
- Partial-diff confidence handling underspecified
- Success metrics qualitative, not operationalized

**Recommended Changes**:

1. Add explicit vendor assumptions section
2. Define "risk review" output contract
3. Formalize governance enforcement with implementation PR
4. Refine partial-diff decision rule
5. Promote aggregator policy to required
6. Replace qualitative success metrics with measurable ones

---

#### Critic Review Summary

**Position**: Disagree-and-Commit (with conditions)

**Key Strengths Identified**:

- Clear problem identification with concrete evidence
- Conservative evidence-sufficiency principle is sound
- Well-reasoned model selection matrix
- Honest acknowledgment of tradeoffs

**Key Gaps Raised**:

- Model claims lack empirical validation
- Implementation plan lacks concrete examples
- Success metrics not measurable (no baseline)
- Evidence improvement section vague on scope
- No cost impact analysis
- Prompt contract enforcement is vague

**Recommended Changes**:

1. Add baseline and measurable success metrics
2. Expand implementation notes with concrete examples
3. Clarify evidence improvement scope
4. Add model validation plan
5. Quantify cost impact
6. Formalize prompt contract enforcement
7. Add model deprecation policy

---

#### Independent-Thinker Review Summary

**Position**: Disagree-and-Commit (with conditions)

**Challenged Assumptions**:

1. False PASS may not be the bottleneck - infrastructure noise (PR #156) may be the real problem
2. Evidence sufficiency rules may shift false PASS to WARN fatigue
3. Model quality claims are heuristic without live benchmarking
4. Cost trade-off is understated
5. Summary-mode PRs may be rare - is policy worth the complexity?

**Blind Spots Identified**:

- No measurement of current false PASS baseline
- Developer workflow not considered (WARN fatigue risk)
- Fallback policy undefined
- "Conservative escalation" not defined operationally
- Post-merge incidents not analyzed by root cause

**Devil's Advocate Questions**:

1. If infrastructure noise is the problem, why solve with model routing?
2. Why not enforce smaller PRs instead?
3. Copilot actionability is declining - why route to it?
4. What is the baseline false PASS rate?
5. Are model tiers evidence-based or cargo-cult?

**Recommended Changes**:

1. Add baseline measurement section
2. Distinguish failure categories explicitly
3. Add context size enforcement as alternative
4. Define escalation operationally
5. Add post-deployment validation

---

#### Security Review Summary

**Position**: Disagree-and-Commit

**Key Strengths Identified**:

- Evidence-based conservatism is sound
- Model tier matching for security gates
- Governance guardrail included

**Security Implications**:

- False PASS reduction vs False NEGATIVE increase (acceptable trade-off)
- Model selection affects review quality
- External model dependency creates data classification concerns

**Threat Model Concerns**:

1. Confidence scoring not in scope
2. Prompt injection via PR metadata (P0)
3. Model drift over time
4. Cascading model failures
5. Silent context truncation

**P0 Recommendations**:

1. Add prompt injection safeguards
2. Make CONTEXT_MODE header mandatory
3. Clarify confidence scoring rules

**P1 Recommendations**:

4. Add data classification statement
5. Add model stability policy
6. Add audit logging

---

#### Analyst Review Summary

**Position**: Accept-and-Commit (with pre-implementation conditions)

**Key Strengths Identified**:

- Real, documented problem with empirical evidence
- Conservative evidence-based reasoning
- Structured model selection
- Governance step included
- Addresses context availability explicitly

**Evidence Gaps**:

- No measurement baseline
- Model quality claims are heuristic
- Partial diff handling underspecified
- Model availability not verified
- Aggregator policy mentioned but not detailed
- Cost/latency trade-off unquantified

**Feasibility Assessment**: Mostly yes, with caveats

- action.yml already accepts copilot-model parameter
- Context mode already output
- Requires workflow modifications and prompt updates
- Integration complexity: Medium

**Root Cause Analysis**:

- Cause 1 (evidence unavailability) correctly addressed
- Cause 2 (model fit mismatch) partially addressed - lacks validation

**Recommended Changes**:

1. Add baseline measurement
2. Verify model availability
3. Define "evidence sufficiency" operationally
4. Estimate cost and latency impact
5. Add workflow enforcement
6. Create context-mode-aware prompt template

---

### Phase 2: Consolidation

#### Consensus Areas (All 5 agents agree)

1. Problem is real: False PASS on summary-only PRs is a valid concern
2. Evidence-based conservatism is sound: Forbidding PASS on insufficient evidence is correct
3. Governance guardrail needed: Explicit copilot-model parameter enforcement
4. Model routing concept is reasonable: Tiered model selection by task type
5. Implementation is feasible: The action.yml already supports required parameters

#### P0 Issues Identified

| ID | Issue | Resolution |
|----|-------|------------|
| P0-1 | No baseline false PASS measurement | Add Prerequisites section with baseline requirement |
| P0-2 | Prompt injection safeguards missing | Add Section 4: Security Hardening |
| P0-3 | CONTEXT_MODE header must be mandatory | Elevate from optional to required |
| P0-4 | Governance enforcement mechanism undefined | Add Guardrail implementation details |
| P0-5 | Model availability unverified | Add Model availability verification prerequisite |

#### P1 Issues Identified

| ID | Issue | Resolution |
|----|-------|------------|
| P1-1 | Success metrics not measurable | Add Baseline column, define targets |
| P1-2 | Escalation criteria vague | Add Section 5: Escalation Criteria with table |
| P1-3 | "Risk review" behavior undefined | Add Section 6: Risk Review Contract |
| P1-4 | Aggregator policy optional | Promote to Section 7: Required |
| P1-5 | Cost/latency trade-off unquantified | Add Cost estimation prerequisite |
| P1-6 | Confidence scoring rules missing | Add to Section 4 |
| P1-7 | Model deprecation fallback undefined | Add to Prerequisites |
| P1-8 | Data classification not stated | Deferred to implementation |

---

### Phase 3: Resolution

**Changes Applied to ADR-017**:

1. Added "Scope Clarification" subsection in Context - addresses independent-thinker concern about infrastructure noise (references Issue #164)

2. Added Section 3 "Guardrail implementation" with specific location, error message, and implementation requirement

3. Added Section 4 "Security hardening" with:
   - Prompt injection safeguards
   - Mandatory CONTEXT_MODE header
   - Confidence scoring rules

4. Added Section 5 "Escalation criteria" with operational table defining triggers

5. Added Section 6 "Risk review contract" with:
   - What agents CAN do in summary mode
   - What agents CANNOT do
   - Example WARN output

6. Added Section 7 "Aggregator policy (REQUIRED)" - promoted from optional

7. Added "Prerequisites" section with:
   - Baseline measurement (P0)
   - Model availability verification (P0)
   - Governance guardrail implementation (P0)
   - Cost estimation (P1)

8. Added "Enforce smaller PRs" to Alternatives Considered (addresses independent-thinker)

9. Updated Success Metrics table with Baseline column

10. Added "Operational complexity" to Negative Consequences

11. Added Related Decisions: ADR-010 and Issue #164

12. Renamed "Agent-Specific Fields" to "Policy Application (Governance Scope)"

13. Added Explicit Limitation #3 about scope

14. Added "Debate Log Reference" section

---

### Phase 4: Convergence Check

**Round 1 Final Positions**:

| Agent | Initial Position | After Revisions | Notes |
|-------|------------------|-----------------|-------|
| architect | Disagree-and-Commit | Pending re-review | Key gaps addressed |
| critic | Disagree-and-Commit | Pending re-review | Metrics, examples addressed |
| independent-thinker | Disagree-and-Commit | Pending re-review | Scope clarified, alternatives noted |
| security | Disagree-and-Commit | Pending re-review | P0 security concerns addressed |
| analyst | Accept-and-Commit | Accept | Prerequisites added |

**Assessment**: Round 1 revisions addressed all P0 issues and most P1 issues. Proceeding to Round 2 convergence check.

---

## Round 2 (Convergence Check)

**All 5 agents re-invoked on updated ADR-017.**

### Final Positions

| Agent | Final Position | Key Statement |
|-------|----------------|---------------|
| architect | **Accept** | "ADR is architecturally sound and implementation-ready. All prerequisites create proper controls." |
| critic | **Accept** | "Round 1 feedback comprehensively addressed. All P0 concerns resolved. Ready for implementation planning." |
| independent-thinker | **Disagree-and-Commit** | "Skeptical that evidence sufficiency is primary lever, but policy is falsifiable. Will support execution." |
| security | **Accept** | "All P0 security concerns addressed. ADR is security-sound and ready for implementation." |
| analyst | **Accept** | "All P0 evidence/feasibility concerns have evidence-based resolution paths. Confidence: 95%." |

### Consensus Achieved

**Result**: 4 Accept + 1 Disagree-and-Commit = **CONSENSUS REACHED**

**Rounds to Consensus**: 2

### Independent-Thinker Dissent (Documented)

The independent-thinker agent maintains the following reservations while committing to support execution:

1. **Hypothesis untested**: Infrastructure noise (Issue #164) may dominate false PASS problem more than evidence insufficiency
2. **Policy is falsifiable**: Post-deployment audit will validate or refute assumptions
3. **Supports proceeding because**:
   - Baseline measurement prerequisite blocks implementation until data exists
   - Quarterly review commitment ensures assumptions won't ossify
   - Security hardening and governance controls are defensible on their own merits

This dissent is recorded per the debate protocol. No blocking action required.

---

## Decision Record

| Decision | Made By | Rationale |
|----------|---------|-----------|
| Add Scope Clarification | Orchestrator | Address independent-thinker concern about infrastructure noise |
| Make CONTEXT_MODE mandatory | Security consensus | Prevents false PASS from undetected truncation |
| Add prompt injection safeguards | Security | P0 threat identified |
| Define escalation criteria operationally | All agents | "High uncertainty" was too vague |
| Promote aggregator to required | Architect | Must be enforced for policy to work |
| Add Prerequisites section | Critic, Analyst | ADR cannot be Accepted without baseline |
| Reference Issue #164 | Independent-thinker | Separates scope from infrastructure concerns |

---

## Round 3 (Post-Prerequisites Review)

**Date**: 2025-12-23
**Session**: 90
**Context**: Review of ADR-017 after prerequisite completion (Session 89)

### Phase 1: Independent Review

**All 6 agents re-invoked on ADR-017 with completed Prerequisites section.**

#### Critical Finding: Root Cause Mismatch

All agents identified a **validation gap**: The 3 baseline false PASS cases documented in P0-1 (PRs #226, #268, #249) were caused by:
- **PR #226**: Runtime workflow logic bug (requires execution to detect)
- **PR #268**: Prompt quality issue (missing VERDICT token validation)
- **PR #249**: Validation gap (label naming convention not checked)

**None of these root causes are addressed by model routing or evidence sufficiency rules**—they require prompt quality improvements and validation rules.

The ADR claims to solve false PASS, measures a 15% baseline, sets a ≥50% reduction target, but the solution doesn't address the measured failures. This creates false expectations about impact.

#### Agent Positions (Phase 1)

| Agent | Key Concerns | Blocking Issues |
|-------|-------------|-----------------|
| **architect** | Chronology ambiguity, Success metrics show "TBD" despite P0-1 completion, implementation status unclear | P0: Chronology timeline needed |
| **critic** | Baseline audit completeness unclear, root cause analysis shallow, cost estimation lacks calculations | P0: Root cause linkage validation |
| **independent-thinker** | Core assumption challenged—ADR doesn't solve measured problem, cost math doesn't reconcile | P0: Solution-to-problem mismatch |
| **security** | Blacklist prompt injection bypassable, CONTEXT_MODE could be manipulated, fallback DoS vulnerability, aggregator not enforced | P0: Whitelist sanitization, validation, circuit breaker, enforcement |
| **analyst** | Root cause analysis lacks depth, baseline audit incomplete, model availability verification weak, cost lacks methodology | P0: Root cause validation |
| **high-level-advisor** | Fundamental validation gap—ADR claims to solve false PASS but doesn't address measured baseline | P0: SHOWSTOPPER—scope clarification or revert to "Proposed" |

### Phase 2: Consolidation

#### P0 Issues Identified

| ID | Issue | Ruling |
|----|-------|--------|
| P0-1 | Root cause mismatch | high-level-advisor: Add root cause analysis section explicitly stating ADR doesn't fix current baseline—it targets FUTURE risk |
| P0-2 | Baseline audit completeness | All agents: Clarify that all 20 PRs were validated |
| P0-3 | Chronology ambiguity | architect: Add status transition timeline |
| P0-4 | Prompt injection blacklist inadequate | security: Change to whitelist/schema approach |
| P0-5 | CONTEXT_MODE validation missing | security: Add token count validation |
| P0-6 | Fallback DoS vulnerability | security: Add circuit breaker (5 blocks → manual approval) |
| P0-7 | Aggregator bypass | security: Add branch protection enforcement |
| P0-8 | Cost reconciliation gap | independent-thinker: Show explicit calculation |

#### P1 Issues Identified

| ID | Issue | Resolution |
|----|-------|------------|
| P1-1 | Success metrics baseline inconsistency | Update table from "TBD" to "15%" |
| P1-2 | Model availability verification weak | Deferred—requires CI testing |
| P1-3 | Cost estimation lacks methodology | Add calculation showing 36% reduction |
| P1-4 | Partial diff N undefined | Define N=500 (aligns with spec-file behavior) |
| P1-5+ | Various implementation/monitoring gaps | Deferred to follow-up |

### Phase 3: Resolution

#### Key Changes Applied

1. **Root Cause Analysis section added** (after line 258):
   - Explicitly analyzes each baseline case
   - States: "The 3 baseline cases were caused by prompt quality and validation gaps, NOT by evidence insufficiency. This ADR does not directly address these 3 cases."
   - Clarifies scope: "This ADR is preventive (stop future risks) not remedial (fix current baseline)"
   - Separates metrics:
     - Baseline false PASS (all causes): 15%
     - Target false PASS (evidence insufficiency): TBD (new metric)

2. **Status Transition Timeline added** (after line 232):
   - Timeline shows: Debate → Prerequisites → Acceptance (all on 2025-12-23)
   - Confirms prerequisites completed BEFORE status change

3. **Security Hardening strengthened**:
   - Prompt injection: Whitelist/schema validation replacing blacklist pattern stripping
   - CONTEXT_MODE validation: Token count check prevents manipulation
   - Circuit breaker: Prevents fallback DoS (5 consecutive blocks → manual approval)

4. **Aggregator enforcement added**:
   - Branch protection rule requiring "AI Review Aggregator" status check
   - Prevents developer bypass of aggregator policy

5. **Cost calculation added**:
   - Explicit math: 568 → 366 Opus-equivalent units = 36% reduction
   - Reconciles escalation rate with routing savings

6. **Success Metrics updated**:
   - Baseline column: "TBD (prerequisite)" → "15% (P0-1 complete)"
   - Metrics separated by root cause (all causes vs evidence insufficiency)

7. **Baseline methodology clarified**:
   - States: "Audited all 20 PRs. 17 confirmed no post-merge fixes; 3 had documented fixes"

8. **Partial diff N defined**:
   - N=500 lines (aligns with existing spec-file behavior per line 31)

### Phase 4: Convergence Check

**All 6 agents re-invoked on updated ADR.**

#### Final Positions

| Agent | Final Position | Key Statement |
|-------|----------------|---------------|
| **architect** | **Accept** | "All P0 architectural concerns resolved. Chronology clarified, metrics updated, root cause analysis adds honest scoping. ADR is structurally sound and implementation-ready." |
| **critic** | **Accept** | "All P0 validation gaps resolved. Root cause analysis explicitly acknowledges ADR doesn't fix current baseline—targets future risk. This is honest and falsifiable. Cost calculation provided, baseline methodology clarified." |
| **independent-thinker** | **Disagree-and-Commit** | "Core concern (root cause mismatch) FIXED. ADR now honestly states it solves FUTURE problem not CURRENT baseline. Metrics separated correctly. I remain skeptical evidence insufficiency is primary lever, but ADR is now intellectually honest and falsifiable. Support execution for validation." |
| **security** | **Accept** | "All P0 security concerns addressed. Whitelist sanitization, CONTEXT_MODE validation, circuit breaker, branch protection enforcement all added. Remaining P1 items are hardening, not blocking." |
| **analyst** | **Accept** | "All P0 evidence gaps resolved. Baseline methodology clarified, root cause analysis provides honest linkage, cost calculation shows supporting math. ADR is evidence-based and ready for implementation." |
| **high-level-advisor** | **Accept** | "Fundamental validation gap FIXED. ADR explicitly states baseline cases NOT caused by evidence insufficiency. Metrics separated (all causes vs evidence insufficiency). Scope clarified as PREVENTIVE not REMEDIAL. Intellectually honest and falsifiable. ADR can remain Accepted status." |

### Consensus Achieved

**Result**: CONSENSUS (Round 3)

**Final Tally**:
- 5 ACCEPT
- 1 DISAGREE-AND-COMMIT

**Rounds to Consensus**: 3 (2 initial rounds in Session 86-88, 1 post-prerequisites round in Session 90)

### Independent-Thinker Dissent (Documented)

> "I remain skeptical that evidence sufficiency is the primary cause of false PASS. The baseline cases suggest prompt quality and validation gaps are larger contributors. However, the ADR now honestly scopes itself as addressing a FUTURE risk (large PRs with summary mode) rather than claiming to fix the CURRENT 15% baseline. This is intellectually honest and falsifiable, so I support execution. Post-deployment audit will validate or refute the hypothesis that evidence sufficiency is a significant contributor to false PASS."

This dissent is recorded per debate protocol. No blocking action required.

---

## Decision Record (All Rounds)

| Decision | Made By | Round | Rationale |
|----------|---------|-------|-----------|
| Add Scope Clarification | Orchestrator | 1 | Address independent-thinker concern about infrastructure noise |
| Make CONTEXT_MODE mandatory | Security consensus | 1 | Prevents false PASS from undetected truncation |
| Add prompt injection safeguards | Security | 1 | P0 threat identified |
| Define escalation criteria operationally | All agents | 1 | "High uncertainty" was too vague |
| Promote aggregator to required | Architect | 1 | Must be enforced for policy to work |
| Add Prerequisites section | Critic, Analyst | 1 | ADR cannot be Accepted without baseline |
| Reference Issue #164 | Independent-thinker | 1 | Separates scope from infrastructure concerns |
| **Add Root Cause Analysis** | **high-level-advisor** | **3** | **Clarify ADR solves FUTURE risk not CURRENT baseline** |
| **Separate metrics by cause** | **All agents** | **3** | **Prevent false expectations about impact** |
| **Strengthen security hardening** | **security** | **3** | **Whitelist, validation, circuit breaker, enforcement** |
| **Add explicit cost calculation** | **independent-thinker** | **3** | **Show math for 36% reduction claim** |
| **Clarify baseline methodology** | **critic, analyst** | **3** | **All 20 PRs validated, not assumed** |

---

---

## Post-Debate: ADR-017 Split (Session 90)

**Date**: 2025-12-23
**Trigger**: User questioned whether ADR-017 strictly adheres to foundational ADR definition
**Finding**: ADR-017 bundles 7 related decisions (violates "single AD" criterion)

### Split Decision (Per ADR-018)

Following ADR-018 (Architecture vs Governance Split Criteria), ADR-017 was split into:

1. **ADR-017-model-routing-strategy.md** (architecture/)
   - **Lean architectural decision**: Model routing strategy for AI reviews
   - **Content**: Context, Decision, Rationale, Alternatives, Consequences
   - **Focus**: Why route models by prompt type + evidence availability
   - **Immutable**: Design decision locked at acceptance

2. **AI-REVIEW-MODEL-POLICY.md** (governance/)
   - **Operational policy**: Compliance requirements and enforcement
   - **Content**: Model routing matrix, evidence rules, security hardening, escalation criteria, aggregator policy, monitoring
   - **Focus**: How to implement routing strategy, what to enforce, how to monitor
   - **Evolvable**: Policy can be updated without re-opening architectural debate

### Rationale for Split

**Why split was recommended** (per ADR-018 criteria):
1. ✅ Decision affects architecture (model routing affects system quality)
2. ✅ Requires operational enforcement (MUST use explicit copilot-model, branch protection rules)
3. ✅ Tightly coupled (routing requires evidence rules, security hardening, aggregator)
4. ✅ Policy will evolve independently (monitoring thresholds, escalation criteria tuning)

**Benefits realized**:
- Architectural decision remains focused and immutable
- Governance policy can evolve without ADR revision
- Follows established pattern (ADR-014 + COST-GOVERNANCE)
- Clearer separation of "why we decided" vs "how we enforce"

### Cross-References

- [ADR-017-model-routing-strategy.md](ADR-017-model-routing-strategy.md) - Architectural decision
- [AI-REVIEW-MODEL-POLICY.md](../../governance/AI-REVIEW-MODEL-POLICY.md) - Governance policy
- [ADR-018-architecture-governance-split-criteria.md](ADR-018-architecture-governance-split-criteria.md) - Defines split criteria

### Original ADR-017 Disposition

The original `ADR-017-model-routing-low-false-pass.md` (bundled version) is **deprecated** and replaced by the split documents. It is preserved in git history for reference.

---

## Metadata

**Created**: 2025-12-23
**Sessions**: 86 (initial debate), 90 (post-prerequisites review + split)
**Status**: Complete - Consensus Achieved + Split Applied
**Rounds**: 3 (2 initial + 1 post-prerequisites)
**Final Result**: 5 Accept + 1 Disagree-and-Commit
**Split Date**: 2025-12-23 (Session 90, per ADR-018)

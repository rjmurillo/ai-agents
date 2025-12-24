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

## Metadata

**Created**: 2025-12-23
**Session**: 86
**Status**: Complete - Consensus Achieved
**Rounds**: 2
**Final Result**: 4 Accept + 1 Disagree-and-Commit

# Plan Critique: ADR-032 Skill Phase Gates

## Verdict

**[NEEDS REVISION]**

**Confidence**: High (8/10)

**Summary**: ADR proposes valuable phase gate pattern but contains CRITICAL ADR numbering conflict with PR #557. Technical approach is sound but implementation metrics lack baseline measurement methodology and several assumptions require verification.

---

## Strengths

1. **Evidence-based rationale**: Cites specific failures (PR #226, Session 97) with quantified impact (60% CRITICAL_FAIL rate)
2. **Clear pattern taxonomy**: Four gate types with explicit pass criteria and enforcement mechanisms
3. **Reference implementation**: Points to planner skill as working example
4. **Balanced trade-off analysis**: Acknowledges overhead vs. benefit
5. **Governance integration**: Created SKILL-PHASE-GATES.md governance document alongside ADR
6. **Philosophical clarity**: Distinguishes "structure + iteration" from raw determinism

---

## Issues Found

### P0: Critical (Must Fix)

#### 1. ADR Numbering Conflict

**Issue**: PR #557 already claims ADR-032 for exit code standardization (state: OPEN, created 2025-12-30T04:24:17Z)

**Evidence**:

```bash
gh pr view 557 --json title,state
# "title": "docs(architecture): add ADR-032 for exit code standardization"
# "state": "OPEN"
```

**Impact**: Two ADRs with same number violates ADR governance, breaks references, confuses cross-references

**Required Action**: Renumber this ADR to next available (ADR-033 or higher) before approval

**Verification**: Check `.agents/architecture/` for highest ADR number:

```bash
ls .agents/architecture/ADR-*.md | sort -V | tail -1
```

---

#### 2. Phase 0 Conflict Not Resolved

**Issue**: ADR notes "Phase 0 Related Work Findings" identifies Issues #265, #219, #258 but does NOT assess whether this ADR duplicates, conflicts with, or integrates those initiatives

**Questions**:

- Does Issue #265 (Pre-PR Validation EPIC) already implement phase gates?
- Does Issue #219 (Session State MCP) track gate passage?
- Does Issue #258 (QA pre-PR gate) conflict with proposed gates?

**Required Action**: Add Phase 0 Deconfliction section analyzing relationship to related work

**Why Critical**: Implementing phase gates that conflict with or duplicate existing systems wastes effort and creates inconsistency

---

### P1: Important (Should Fix)

#### 3. Baseline Metrics Lack Measurement Methodology

**Issue**: ADR claims "~30% of analyses" lack evidence but does NOT document:

- How this baseline was measured
- Which sessions were sampled
- What constitutes "evidence-less conclusion"

**Evidence Gap**: Current state says "Evidence-less conclusions: ~30%" but no audit trail exists

**Required Action**: Either:

1. Document the retrospective analysis that produced 30%, OR
2. Change baseline to "Unknown" and commit to Phase 1 measurement

**Why Important**: Cannot measure improvement without verifiable baseline

---

#### 4. Gate Enforcement Mechanism Unclear for SKILL.md-Only Skills

**Issue**: Pattern B (Documentation-Enforced Gates) admits "Soft enforcement, relies on LLM compliance"

**Conflict with Evidence**: Autonomous-execution-guardrails memory states "Design systems where agents cannot do the wrong thing, not systems where agents are trusted not to"

**Question**: If Pattern B has soft enforcement, how does it achieve the goal of preventing protocol bypasses?

**Required Action**: Either:

1. Require all high-risk skills to have script enforcement (Pattern A), OR
2. Document acceptable risk level for Pattern B skills, OR
3. Add CI validation that checks skill outputs for gate status markers

**Why Important**: Soft enforcement failed before (60% CRITICAL_FAIL). Pattern B may repeat this failure.

---

#### 5. Skill Priority Order Lacks Risk Quantification

**Issue**: Implementation Phase 2 prioritizes skills by "failure frequency" but does NOT provide data:

| Skill | Failure Count | Sessions Affected | Severity |
|-------|---------------|-------------------|----------|
| merge-resolver | ? | ? | ? |
| analyze | ? | ? | ? |
| session-log-fixer | ? | ? | ? |
| adr-review | ? | ? | ? |

**Required Action**: Add risk matrix with actual failure data from session logs

**Why Important**: Resources should go to highest-risk skills first, not assumed priority

---

#### 6. Metrics Target Lacks Justification

**Issue**: Target "<10%" for protocol violations not justified

**Questions**:

- Why 10% and not 5% or 15%?
- What is acceptable failure rate for safety-critical skills vs. convenience skills?
- Is 10% calculated from industry benchmarks or arbitrary?

**Required Action**: Either provide rationale for 10% threshold OR state it as provisional pending Phase 1 data

---

### P2: Minor (Consider)

#### 7. Token Overhead Not Quantified

**Issue**: Negative consequence lists "Additional token usage for gate documentation" but provides no estimate

**Suggested Addition**: Estimate token cost per gate (e.g., "~200 tokens per evidence gate for N sources")

---

#### 8. Rollback Plan for Gate Addition

**Issue**: ADR does not address what happens if gates prove too expensive or cause unacceptable slowdown

**Suggested Addition**: Define conditions for reverting gates (e.g., ">5% session timeout rate")

---

#### 9. Gate Bypass Testing Not Specified

**Issue**: Compliance checklist says "Test bypass attempts" but provides no methodology

**Suggested Addition**: Add bypass testing protocol (e.g., "Invoke skill with incomplete evidence, verify BLOCKED output")

---

## Scope Concerns

### In Scope (Appropriate)

- Phase gate pattern definition
- Governance document creation
- Reference to planner skill implementation

### Scope Creep Indicators

- **Week 4 Enforcement**: Implementation section includes "Add gate validation to skill scripts" which may require significant refactoring
- **Skill Matrix Retrofitting**: 6 skills identified for retrofit may be overly ambitious for single ADR

### Recommendation

Split into two ADRs:

1. **ADR-033**: Phase Gate Pattern (governance + pattern definition)
2. **ADR-034**: Phase Gate Implementation (skill-specific retrofit with risk analysis per skill)

---

## Questions for Author

### Clarification Needed

1. **ADR Numbering**: Which number should this ADR use (033, 034, or higher)?
2. **Phase 0 Findings**: How does this integrate with Issues #265, #219, #258?
3. **Baseline Measurement**: Where did "~30% evidence-less" come from? Can you provide audit trail?
4. **Pattern B Risk**: Given soft enforcement failed before, why include Pattern B at all?
5. **merge-resolver Priority**: Why is merge-resolver listed first? What data supports this priority?

### Design Decisions

6. **Enforcement Philosophy**: Should all safety-critical skills REQUIRE script enforcement (Pattern A)?
7. **Acceptable Risk**: What is the acceptable failure rate for Pattern B skills?
8. **Rollback Threshold**: At what point would you recommend removing gates (performance, token cost)?

---

## Approval Conditions

This ADR will be approved when:

1. **P0 Issues Resolved**:
   - [ ] ADR renumbered to avoid conflict with PR #557
   - [ ] Phase 0 deconfliction section added analyzing Issues #265, #219, #258
2. **P1 Issues Addressed**:
   - [ ] Baseline metrics documented with measurement methodology OR marked "Unknown - to be measured"
   - [ ] Gate enforcement risk documented for Pattern B OR Pattern B removed for high-risk skills
   - [ ] Skill priority order backed by failure data OR marked provisional
   - [ ] Metrics target justified OR marked provisional
3. **Scope Validated**:
   - [ ] Implementation scope confirmed feasible OR split into multiple ADRs

---

## Impact Analysis Review

**Consultation Coverage**: N/A (no impact analysis present)

**Cross-Domain Conflicts**: None detected at ADR level

**Escalation Required**: No

### Specialist Agreement Status

| Specialist | Consulted | Recommendation |
|------------|-----------|----------------|
| Security | No | Phase gate bypass could be security risk - consider consultation |
| QA | No | Gate validation testing - consider consultation |
| Implementer | No | Retrofit effort estimation - consider consultation |

**Unanimous Agreement**: N/A (no specialist consultation occurred)

**Recommendation**: Consider lightweight consultation with security (gate bypass = protocol bypass risk) and QA (gate testing methodology)

---

## Recommendations

### Immediate Actions

1. Renumber ADR to ADR-033 or higher
2. Add Phase 0 Deconfliction section
3. Document baseline measurement methodology OR mark baselines as provisional
4. Add risk matrix for skill prioritization

### Strategic Improvements

1. Consider splitting into pattern definition (ADR-033) + implementation plan (ADR-034)
2. Add pilot program: Implement gates in ONE high-risk skill, measure for 2 weeks, then expand
3. Define gate effectiveness metrics BEFORE full rollout
4. Create gate bypass testing protocol

### Pattern Validation

The core pattern is sound and aligns with protocol-blocking-gates memory. The planner skill reference implementation proves feasibility. Primary concerns are implementation scope and soft-enforcement risk for Pattern B.

---

## Related Memories

**Reviewed**:

- `autonomous-execution-guardrails`: Supports hard enforcement approach
- `protocol-blocking-gates`: Validates verification-based gate pattern (100% compliance)
- `memory-index`: Confirmed skill-related memories loaded

**Patterns Applied**:

- Verification-based enforcement over trust-based
- Evidence-based metrics over assumptions
- Pilot before full rollout

---

## Handoff

**Status**: NEEDS REVISION

**Recommended Next Agent**: Architect (or ADR author)

**Required Revisions**:

1. Resolve ADR numbering conflict
2. Add Phase 0 deconfliction analysis
3. Document or provision baseline metrics
4. Address Pattern B soft enforcement risk

**Estimated Revision Effort**: 2-4 hours (research Phase 0 issues, audit sessions for baselines, analyze skill failure data)

---

*Critique Version: 1.0*
*Reviewed: 2025-12-30*
*Critic Agent Session: [Current]*
*Review Time: Phase 1 Independent Review*

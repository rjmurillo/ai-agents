# Critique: ADR-039 Agent Model Cost Optimization

**Reviewed**: 2026-01-03
**Reviewer**: critic
**Status**: PROVISIONAL ADR (2-week validation period)

---

## Critic Review

**Verdict**: DISAGREE-AND-COMMIT

**P0 Issues** (must resolve): 0

**P1 Issues** (should resolve): 4

**P2 Issues** (nice to have): 3

**Rationale**: The ADR documents changes already implemented without empirical validation. The provisional period is appropriate mitigation. However, the monitoring plan lacks specificity, success criteria are vague, and the rationale conflates theoretical capability with actual task requirements. Approve with provisional status, but quality metrics must be collected during validation period.

---

## Summary

ADR-039 downgrades 6 agents from Opus to Sonnet and 2 agents from Sonnet to Haiku based on session analysis (289-290 sessions). The changes are already implemented (commits 651205a, d81f237, f101c06). A 2-week provisional period allows monitoring before final acceptance.

**Key concerns**:
1. No empirical quality testing before implementation
2. Monitoring plan is vague and unactionable
3. Reversion procedures are manual and error-prone
4. Success criteria are subjective without quantification

**Strengths**:
1. Data-driven approach (290 sessions analyzed)
2. Clear cost optimization rationale (1.67x savings per downgraded agent)
3. Provisional status provides validation window
4. Specific commit references for reversion

---

## Issues Found

### P0 (Blocking)

None. Provisional status mitigates the risk of implementation-before-validation.

### P1 (Should Fix)

#### ISSUE-001: Monitoring Plan Lacks Specificity

**Location**: Lines 168-202 (Monitoring Plan section)

**Problem**: The monitoring plan lists what to track but not how to measure or what thresholds trigger action.

**Current state**:
```text
Track quality metrics:
1. Agent invocation success rates
2. User satisfaction with outputs
3. Issue counts by agent type
4. API cost changes vs ADR-002 baseline
```

**Missing**:
- How to measure "success rate" (what constitutes success vs failure?)
- How to quantify "user satisfaction" (survey? issue count? explicit feedback?)
- Baseline values for comparison (what was the Opus success rate?)
- Thresholds for concern (if success rate drops X%, revert?)

**Recommendation**: Add measurement methodology to Implementation Notes:

```markdown
### Monitoring Methodology

| Metric | Measurement Method | Baseline | Threshold for Concern |
|--------|-------------------|----------|----------------------|
| Success rate | % of agent invocations completing without error | orchestrator: 95%, architect: 98%, security: 97% | Drop >5% |
| User satisfaction | Issue count tagged "quality-regression" | 0 per week | >1 per week |
| Issue counts | GitHub issues by agent label | orchestrator: 2/month, architect: 1/month | 2x baseline |
| API cost | Monthly bill analysis | $X/month on Opus | N/A (savings expected) |
```

**Severity**: High. Without measurement methodology, monitoring is subjective and reversion decisions are arbitrary.

---

#### ISSUE-002: Success Criteria Are Vague

**Location**: Lines 197-202 (Success Criteria section)

**Problem**: Success criteria use subjective language without quantification.

**Current wording**:
- "No increase in agent error rates" - What is the current error rate? What counts as an "increase"?
- "No user complaints about quality" - Is one complaint acceptable? What about implicit complaints (abandoning agent use)?

**Evidence gap**: No baseline metrics documented. ADR-002 did not measure quality, so there is no quantitative comparison point.

**Recommendation**: Revise to quantifiable criteria:

```markdown
### Success Criteria (Quantified)

| Criterion | Measurement | Target | Data Source |
|-----------|-------------|--------|-------------|
| Agent error rate | % of invocations with unhandled exceptions | ≤5% (baseline: TBD) | Session logs |
| Security review quality | % of security issues caught in review | ≥90% (baseline: TBD) | Issue tracking |
| User satisfaction | Explicit reversion requests | 0 during provisional period | User feedback |
| Cost reduction | API bill decrease | 40-50% reduction (estimated) | Anthropic billing |
```

**Note**: If baseline data does not exist, state this explicitly and set provisional targets based on reasonable expectations.

**Severity**: High. Vague criteria make validation period outcome subjective.

---

#### ISSUE-003: Reversion Procedures Are Error-Prone

**Location**: Lines 176-196 (Reversion Procedures section)

**Problem**: Manual git commands are fragile and require careful execution under stress (if quality issues are discovered mid-incident).

**Current approach**:
```bash
# orchestrator
git show d81f237^:.claude/agents/orchestrator.md > .claude/agents/orchestrator.md
```

**Risks**:
1. Manual file path specification (typo risk)
2. No validation that reversion succeeded
3. No atomic reversion (each agent reverted separately)
4. No automated testing after reversion

**Recommendation**: Create reversion script:

```powershell
# scripts/Revert-AgentModel.ps1
param(
    [Parameter(Mandatory)]
    [ValidateSet('orchestrator', 'architect', 'security', 'all')]
    [string]$Agent
)

$revertMap = @{
    orchestrator = @{ commit = 'd81f237'; path = '.claude/agents/orchestrator.md' }
    architect = @{ commit = 'd81f237'; path = '.claude/agents/architect.md' }
    security = @{ commit = 'd81f237'; path = '.claude/agents/security.md' }
}

if ($Agent -eq 'all') {
    git revert f101c06 d81f237 651205a
} else {
    $config = $revertMap[$Agent]
    git show "$($config.commit)^:$($config.path)" > $config.path
    # Validation: Check model field changed to 'opus'
    $content = Get-Content $config.path -Raw
    if ($content -notmatch 'model: opus') {
        Write-Error "Reversion failed: model field not restored to opus"
        exit 1
    }
}
```

**Severity**: Medium. Reversion is documented but fragile. Under time pressure (quality incident), manual commands increase risk.

---

#### ISSUE-004: No Empirical Quality Testing Before Implementation

**Location**: Line 9 (Provisional Rationale)

**Problem**: Changes were implemented before validating that Sonnet maintains quality for downgraded agents.

**Evidence**: ADR explicitly states "Independent-thinker review (rating: 3/10) identified that empirical quality testing was not conducted before implementation."

**Impact**: If Sonnet quality is insufficient for security or orchestrator, the reversion cost includes:
1. Time to detect quality degradation
2. Incident response if degradation causes production impact
3. Rollback execution
4. Re-testing after rollback

**Current mitigation**: Provisional status (2-week validation period)

**Recommended improvement**: Add empirical quality test DURING provisional period:

```markdown
### Empirical Quality Validation (Week 1 of Provisional Period)

Test each downgraded agent with representative tasks:

| Agent | Test Task | Pass Criteria |
|-------|-----------|---------------|
| orchestrator | Coordinate 3-agent workflow (analyst → planner → implementer) | All handoffs correct, no routing errors |
| architect | Review ADR with 5+ components | All SOLID violations caught |
| security | Review infrastructure change (workflow + script) | All CWE patterns detected |
| independent-thinker | Critique plan with 3+ assumptions | All unstated assumptions identified |
| roadmap | Create epic with 5+ features | All dependencies documented |
| high-level-advisor | Resolve 2-agent conflict | Decision rationale sound |

**If any test fails**: Revert that specific agent immediately, do not wait for 2-week period.
```

**Severity**: High. Implementation-first approach increases risk. Provisional period helps but does not eliminate risk of quality degradation during validation window.

---

### P2 (Nice to Have)

#### ISSUE-005: Sessions Analyzed Range Is Unclear

**Location**: Line 26 ("Analysis of sessions 289-290")

**Problem**: "Sessions 289-290" suggests only 2 sessions analyzed, but text claims "December 21, 2025 to January 3, 2026" (14 days).

**Recommendation**: Clarify session numbering. If 289-290 is a typo for "sessions through 290", state "sessions 1-290" or "290 total sessions analyzed."

**Severity**: Low. Confusion about data volume but does not affect decision quality.

---

#### ISSUE-006: No Discussion of Task Complexity Distribution

**Location**: Lines 92-105 (Rationale section)

**Problem**: ADR assumes all tasks within an agent are homogeneous in complexity. For example, "Design review (architect): Applies architectural patterns and checklists."

**Counter-example**: Some architectural decisions require deep reasoning:
- Breaking changes to core abstractions
- Multi-system integration trade-offs
- Performance vs maintainability at scale

**Missing analysis**: Distribution of task complexity within each agent. What percentage of architect tasks are checklist-based vs deep reasoning?

**Recommendation**: Add complexity distribution analysis:

```markdown
### Task Complexity Distribution (Session Analysis)

| Agent | Checklist Tasks | Moderate Reasoning | Deep Reasoning | Sonnet Suitable? |
|-------|-----------------|-------------------|----------------|------------------|
| architect | 60% | 30% | 10% | Yes (90% coverage) |
| security | 80% | 15% | 5% | Yes (95% coverage) |
| orchestrator | 70% | 25% | 5% | Yes (95% coverage) |

**Note**: Deep reasoning tasks (10% of architect work) may see quality degradation on Sonnet. Monitoring should track these separately.
```

**Severity**: Low. Useful for understanding risk but not blocking.

---

#### ISSUE-007: No Cost Baseline Documented

**Location**: Line 174 ("API cost changes vs ADR-002 baseline")

**Problem**: ADR claims 40-50% cost reduction (line 112) but does not document current API costs.

**Missing data**:
- Current monthly API cost
- Cost breakdown by agent (which agents drive most spend?)
- Expected monthly savings ($X/month)

**Recommendation**: Add cost baseline to Implementation Notes:

```markdown
### Cost Baseline (ADR-002 Distribution)

| Agent | Model | Invocations/Month | Estimated Cost/Month |
|-------|-------|-------------------|----------------------|
| orchestrator | opus | 200 | $X |
| architect | opus | 50 | $Y |
| security | opus | 30 | $Z |
| ... | ... | ... | ... |
| **Total** | - | - | **$BASELINE** |

**Expected savings (ADR-039)**: $REDUCTION/month (X% reduction)
```

**Severity**: Low. Useful for ROI tracking but not required for decision validation.

---

## Strengths

### STR-001: Data-Driven Approach

ADR is based on 290 sessions of actual usage analysis, not theoretical reasoning. This is a significant improvement over ADR-002's theoretical framework.

**Evidence**: Lines 26-27, 210-212 (Session data references)

---

### STR-002: Clear Cost Rationale

Pricing comparison is explicit (line 29-34) and cost multipliers are quantified (1.67x for Opus vs Sonnet).

---

### STR-003: Provisional Status Reduces Risk

Two-week validation period (line 5-8) provides safety net for implementation-first approach.

**Critique**: Provisional period is good risk mitigation, but does not eliminate the gap of no pre-implementation testing.

---

### STR-004: Specific Reversion References

Each commit is documented (lines 152-167) with specific files changed, making reversion traceable.

**Critique**: Manual reversion is still fragile (see ISSUE-003).

---

## Questions for Author

1. **Measurement methodology**: How will "agent invocation success rates" be measured? What constitutes success vs failure?

2. **Baseline metrics**: What were the error rates and quality metrics under ADR-002 (Opus assignments)? Without baselines, how will validation compare?

3. **Independent-thinker review**: Where is the referenced independent-thinker review (rating: 3/10) documented? Can this be linked for context?

4. **Session analysis details**: How were sessions 289-290 analyzed? What methodology was used to classify tasks as "structured" vs "deep reasoning"?

5. **Cost impact**: What is the current monthly API cost and what is the expected savings in dollars (not just percentages)?

---

## Recommendations

### For Validation Period (Weeks 1-2)

1. **Week 1**: Run empirical quality tests (see ISSUE-004 recommendation)
2. **Week 1**: Establish measurement methodology and baselines (see ISSUE-001 recommendation)
3. **Week 2**: Collect quality metrics and compare to baselines
4. **Week 2**: Document cost savings (actual vs expected)

### For Final Acceptance

Before removing PROVISIONAL status:

- [ ] All empirical quality tests pass
- [ ] Monitoring data collected for 2 weeks
- [ ] No quality regressions detected
- [ ] Cost savings validated (40-50% reduction confirmed)
- [ ] Reversion script created and tested (see ISSUE-003 recommendation)
- [ ] Success criteria quantified (see ISSUE-002 recommendation)

### For Documentation

- [ ] Link independent-thinker review (if documented)
- [ ] Clarify session analysis range (289-290 vs 14 days)
- [ ] Add cost baseline with dollar amounts
- [ ] Add task complexity distribution analysis

---

## Alignment Assessment

### With Project Goals

**Alignment**: High

Cost optimization aligns with efficient resource usage. Reserving Opus for highest-stakes work (implementer) is sound prioritization.

### With ADR-002 Framework

**Consistency**: Partial

ADR-002 established decision matrix (reasoning depth, error cost, etc.). ADR-039 supersedes this with usage-based optimization. However, ADR-039 does not revisit the decision matrix - it assumes session analysis is sufficient.

**Gap**: No discussion of whether usage patterns reflect actual requirements. High Opus usage might indicate tasks NEED Opus, not that tasks CAN use Sonnet.

### With Project Constraints

**Compliance**: Full

No violations of PROJECT-CONSTRAINTS.md. This is a configuration change, not a code change.

---

## Risk Assessment

### Overall Risk: MEDIUM

**Rationale**: Changes are reversible, but quality degradation during provisional period could impact user experience or create security gaps.

### Risk Breakdown

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Security agent misses vulnerability | Low | High | 2-week monitoring, revert if issues found |
| Orchestrator routing errors | Medium | Medium | Provisional status, manual review of complex tasks |
| Architect ADR quality degrades | Low | Medium | Human review of all ADRs during provisional period |
| Cost savings do not materialize | Low | Low | Billing analysis in week 2 |

### Monitoring-Required Risks

These risks require active monitoring during provisional period:

1. **Security review completeness**: Compare security reviews before/after downgrade
2. **Orchestrator correctness**: Track routing errors and handoff failures
3. **Architect reasoning depth**: Review ADRs for missed patterns or shallow analysis

---

## Compliance Checklist

### Completeness

- [x] All requirements addressed (cost optimization, model selection)
- [x] Acceptance criteria defined (though vague - see ISSUE-002)
- [x] Dependencies identified (none)
- [x] Risks documented (NEG-001 through NEG-006)

### Feasibility

- [x] Technical approach is sound (model downgrades are configuration changes)
- [x] Scope is realistic (8 agent configuration changes)
- [x] Dependencies are available (Claude 4.5 family models exist)
- [x] Team has required skills (configuration change only)

### Alignment

- [x] Matches original requirements (cost optimization from session analysis)
- [x] Consistent with architecture (no architectural changes)
- [x] Follows project conventions (ADR template version 1.0)
- [x] Supports project goals (efficient resource usage)

### Testability

- [ ] Each milestone can be verified - **PARTIAL**: Success criteria are vague (see ISSUE-002)
- [ ] Acceptance criteria are measurable - **NO**: "No user complaints" is not quantified
- [x] Test strategy is clear (2-week monitoring period)

### Reversibility

- [x] Rollback capability documented (lines 176-196)
- [x] Vendor lock-in assessed (none - same vendor, different model tier)
- [x] Exit strategy defined (revert commits or manual file restoration)
- [x] Legacy system impact evaluated (none - backward compatible)
- [x] Data migration reversibility confirmed (none required)

---

## Approval Conditions

### Blocking

None. Provisional status is appropriate mitigation for implementation-first approach.

### Recommended Before Final Acceptance

1. Resolve ISSUE-001: Add measurement methodology to monitoring plan
2. Resolve ISSUE-002: Quantify success criteria with specific thresholds
3. Resolve ISSUE-003: Create reversion automation script
4. Resolve ISSUE-004: Run empirical quality tests in week 1 of provisional period

---

## Handoff Recommendation

**Recommended next agent**: implementer (if issues need fixing) OR user (if accepted as-is with provisional status)

**Rationale**: This is a PROVISIONAL ADR documenting already-implemented changes. The review validates the ADR documentation quality, not the implementation decision (which is subject to 2-week validation).

**User decision required**: Accept provisional status with P1 issues as technical debt, or address P1 issues before final acceptance.

---

## Numeric Evidence Preserved

| Fact | Value | Source |
|------|-------|--------|
| Opus pricing (input) | $5/MTok | ADR line 32 |
| Opus pricing (output) | $25/MTok | ADR line 32 |
| Sonnet pricing (input) | $3/MTok | ADR line 33 |
| Sonnet pricing (output) | $15/MTok | ADR line 33 |
| Haiku pricing (input) | $1/MTok | ADR line 34 |
| Haiku pricing (output) | $5/MTok | ADR line 34 |
| Opus cost multiplier | 1.67x Sonnet | ADR line 32 |
| Haiku cost multiplier | 0.33x Sonnet | ADR line 34 |
| Agents downgraded opus→sonnet | 6 | ADR line 74-80 |
| Agents downgraded sonnet→haiku | 2 | ADR line 82-84 |
| Final opus count | 1 (implementer) | ADR line 88-89 |
| Final sonnet count | 16 | ADR line 69 |
| Final haiku count | 3 | ADR line 70 |
| Sessions analyzed | 289-290 (unclear) | ADR line 26 |
| Provisional period duration | 14 days | ADR line 5 |
| Expected cost reduction | 66.67% on 6 agents | ADR line 135 (POS-001) |

---

**Template Version**: 1.0
**Session**: 129
**Reviewer**: critic

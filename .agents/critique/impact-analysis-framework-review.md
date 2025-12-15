# Impact Analysis Framework Review

**Branch**: `copilot/add-impact-analysis-framework`
**PRD Source**: [GitHub Issue #34](https://github.com/rjmurillo/ai-agents/issues/34)
**Review Date**: 2025-12-15
**Reviewer**: Critic Agent (orchestrated)

## Executive Summary

The implementation provides a **solid foundation** for the Multi-Agent Impact Analysis Framework. Core documentation and specialist agent templates are in place. However, several PRD requirements are **PARTIAL or MISSING**, particularly around success metrics tracking, validation mechanisms, and plan marking.

**Overall Assessment**: **PARTIAL IMPLEMENTATION** - approximately 70% complete

---

## PRD Requirements Analysis

### Story 1: Planner Orchestration

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Identify required specialist consultations from change scope | **COMPLETE** | `claude/planner.md` lines 112-160: "When to Conduct Impact Analysis" with trigger conditions |
| Invoke specialists with structured prompts | **COMPLETE** | `claude/planner.md` lines 175-193: "Impact Analysis Prompt Template" |
| Aggregate results into final plan | **COMPLETE** | `claude/planner.md` lines 231-265: "Aggregated Impact Summary" template |
| Mark plan as "consultation-complete" | **MISSING** | No explicit marker or flag in templates to indicate consultation status |

**Gap Detail**: The planner template shows a checklist for completed consultations but lacks a formal status marker like `**Consultation Status**: Complete` that could be programmatically verified or that would signal to downstream agents (critic, implementer) that all consultations are done.

---

### Story 2: Implementer Impact Analysis

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Identify affected files/modules | **COMPLETE** | `claude/implementer.md` lines 64-70: "Affected Areas" table |
| Assess complexity levels | **COMPLETE** | `claude/implementer.md` line 51: Complexity field in header |
| Flag breaking changes | **PARTIAL** | No explicit "Breaking Changes" section in template |
| Recommend refactoring opportunities | **COMPLETE** | `claude/implementer.md` lines 86-90: "Recommendations" section |

**Gap Detail**: The implementer template has a "Code Quality Risks" table but no dedicated "Breaking Changes" section. Breaking changes are a critical concern that should be called out explicitly, not buried in a generic risk table.

---

### Story 3: DevOps Impact Analysis

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Identify affected CI/CD workflows | **COMPLETE** | `claude/devops.md` lines 70-76: "Build Pipeline Changes" table |
| Flag validation script updates | **PARTIAL** | No explicit mention of validation scripts in template |
| Assess developer experience impacts | **MISSING** | No "Developer Experience" section in template |
| Recommend operational safeguards | **COMPLETE** | `claude/devops.md` lines 78-83: "Deployment Impact" with rollback strategy |

**Gap Detail**: The PRD specifically asks about "developer experience impacts" - how will this change affect day-to-day development workflows? The template focuses on infrastructure but ignores local dev setup, IDE impacts, or workflow changes.

---

### Story 4: Security Impact Analysis

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Identify security implications | **COMPLETE** | `claude/security.md` lines 107-114: "Affected Areas" security domain table |
| Define threat models | **COMPLETE** | `claude/security.md` lines 122-128: "Threat Vectors" with STRIDE categories |
| Flag dependency vulnerabilities | **PARTIAL** | No explicit "Dependency Security" section |
| Assess blast radius | **MISSING** | No "Blast Radius Assessment" section |

**Gap Detail**: "Blast radius" (what systems/data are affected if a security control fails) is a key security metric not addressed. Dependency vulnerabilities mentioned in PRD should have a dedicated section for third-party library security.

---

### Story 5: QA Impact Analysis

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Define test coverage requirements | **COMPLETE** | `claude/qa.md` lines 69-77: "Required Test Types" with coverage targets |
| Identify edge cases | **COMPLETE** | `claude/qa.md` lines 79-83: "Hard-to-Test Scenarios" table |
| Recommend automation approach | **PARTIAL** | Template mentions test types but no "Automation Strategy" section |
| Flag regression risks | **COMPLETE** | `claude/qa.md` lines 85-89: "Quality Risks" table |

**Gap Detail**: The PRD asks for automation recommendations (what can/should be automated vs. manual). The template lists test types but doesn't address automation feasibility or strategy.

---

### Story 6: Architect Impact Analysis

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Verify domain model alignment | **PARTIAL** | Template mentions "ADR Alignment" but not "Domain Model" specifically |
| Assess abstraction consistency | **MISSING** | No section addressing abstraction layers or consistency |
| Determine ADR necessity | **COMPLETE** | `claude/architect.md` lines 77-82: "ADR Alignment" table with need assessment |
| Evaluate long-term implications | **COMPLETE** | `claude/architect.md` lines 92-95: "Long-Term Implications" section |

**Gap Detail**: "Domain model alignment" and "abstraction consistency" are architectural concerns not explicitly addressed. The template focuses on ADRs and patterns but misses domain-driven design alignment.

---

### Success Metrics

| Metric | Status | Evidence |
|--------|--------|----------|
| Consultation coverage percentage | **MISSING** | No tracking mechanism implemented |
| Issue discovery rate (pre-implementation) | **MISSING** | No baseline or tracking mechanism |
| Post-implementation fix reduction | **MISSING** | No tracking mechanism |
| Planning phase duration | **MISSING** | No timing guidance or tracking |
| Developer satisfaction feedback | **MISSING** | No feedback collection mechanism |

**Gap Detail**: The PRD defines 5 success metrics, none of which have tracking mechanisms in the implementation. This is a significant gap - without metrics, the framework's effectiveness cannot be measured.

---

### Technical Approach: Planner-Driven Orchestration

| Element | Status | Evidence |
|---------|--------|----------|
| Planner includes consultation logic | **COMPLETE** | Full impact analysis section in planner.md |
| Heuristics for specialist selection | **COMPLETE** | Trigger conditions defined |
| Invokes via sub-agent tasks | **COMPLETE** | Task() invocation template provided |
| Aggregates findings into documentation | **COMPLETE** | Aggregation template provided |

---

### Out of Scope Items

| Item | Status | Evidence |
|------|--------|----------|
| Automatic implementation of recommendations | **CORRECTLY EXCLUDED** | Not in scope |
| Cross-repository consultation | **CORRECTLY EXCLUDED** | Not in scope |
| Real-time agent collaboration | **CORRECTLY EXCLUDED** | Not in scope |

---

## Cross-Cutting Issues

### 1. Markdown Fence Issues in copilot-cli and vs-code-agents

**Severity**: HIGH

The `copilot-cli/planner.agent.md` and `vs-code-agents/planner.agent.md` files have malformed markdown fences:

```text
# Incorrect (appears in implementation)
```markdown
- [ ] Analyze proposed change dimensions
```text  <-- Should be just ```

# Should be
```markdown
- [ ] Analyze proposed change dimensions
```
```

**Files Affected**:
- `copilot-cli/planner.agent.md`
- `vs-code-agents/planner.agent.md`
- Likely also in other specialist agent files

### 2. Inconsistent Template References

**Severity**: MEDIUM

The `IMPACT-ANALYSIS-FRAMEWORK.md` references templates in agent files but uses slightly different terminology:
- Framework doc: "Code impact analysis template"
- Implementer doc: "Impact Analysis Deliverable"

### 3. Missing Orchestrator Integration

**Severity**: MEDIUM

While `claude/orchestrator.md` has a single line added about impact analysis in the routing table, it lacks:
- Detailed guidance on when to trigger the framework
- How to handle failed consultations
- Timeout or fallback strategies

### 4. No Validation Hook for Critic

**Severity**: MEDIUM

The critic agent is mentioned as reviewing "the plan including all impact analyses" but:
- Critic agent file not updated with impact analysis validation criteria
- No checklist for critic to verify consultation completeness

---

## Summary: Requirement Coverage

| Category | Complete | Partial | Missing | Total |
|----------|----------|---------|---------|-------|
| Story 1: Planner | 3 | 0 | 1 | 4 |
| Story 2: Implementer | 3 | 1 | 0 | 4 |
| Story 3: DevOps | 2 | 1 | 1 | 4 |
| Story 4: Security | 2 | 1 | 1 | 4 |
| Story 5: QA | 3 | 1 | 0 | 4 |
| Story 6: Architect | 2 | 1 | 1 | 4 |
| Success Metrics | 0 | 0 | 5 | 5 |
| **TOTALS** | **15** | **5** | **9** | **29** |

**Completion Rate**: 52% Complete, 17% Partial, 31% Missing

---

## Remediation Plan

### Priority 1: Critical Gaps (Must Fix Before Merge)

#### 1.1 Fix Markdown Fence Errors

**Files**:
- `copilot-cli/planner.agent.md`
- `vs-code-agents/planner.agent.md`
- `copilot-cli/implementer.agent.md`
- `copilot-cli/architect.agent.md`
- `copilot-cli/security.agent.md`
- `copilot-cli/devops.agent.md`
- `copilot-cli/qa.agent.md`
- `vs-code-agents/implementer.agent.md`
- `vs-code-agents/architect.agent.md`
- `vs-code-agents/security.agent.md`
- `vs-code-agents/devops.agent.md`
- `vs-code-agents/qa.agent.md`

**Action**: Replace all instances of ` ```text ` at the end of code blocks with plain ` ``` `

**Command**: Run fix-markdown-fences utility:
```bash
pwsh .agents/utilities/fix-markdown-fences/fix_fences.ps1
```

#### 1.2 Add Plan Consultation Status Marker

**File**: `claude/planner.md`

**Action**: Add to the aggregated impact summary template:

```markdown
**Consultation Status**: [In Progress | Complete | Blocked]
**Blocking Issues**: [None | List issues preventing completion]
```

### Priority 2: Important Gaps (Should Fix Before Merge)

#### 2.1 Add Breaking Changes Section to Implementer Template

**File**: `claude/implementer.md` (and copilot-cli, vs-code-agents variants)

**Action**: Add section after "Existing Patterns":

```markdown
## Breaking Changes

| Change | Severity | Migration Path |
|--------|----------|----------------|
| [API change] | [Breaking/Deprecation] | [How to migrate] |

**Backward Compatibility**: [Yes/No/Partial]
```

#### 2.2 Add Developer Experience Section to DevOps Template

**File**: `claude/devops.md` (and variants)

**Action**: Add section:

```markdown
## Developer Experience Impact

| Workflow | Current | After Change | Migration Effort |
|----------|---------|--------------|-----------------|
| Local dev setup | [Current] | [New] | [L/M/H] |
| IDE integration | [Current] | [New] | [L/M/H] |
| Build commands | [Current] | [New] | [L/M/H] |
```

#### 2.3 Add Blast Radius and Dependency Security to Security Template

**File**: `claude/security.md` (and variants)

**Action**: Add sections:

```markdown
## Blast Radius Assessment

| If Control Fails | Systems Affected | Data at Risk | Containment Strategy |
|------------------|-----------------|--------------|---------------------|
| [Control] | [Systems] | [Data] | [Strategy] |

## Dependency Security

| Dependency | Version | Known Vulnerabilities | Risk Level |
|------------|---------|----------------------|------------|
| [Package] | [Ver] | [CVE list or None] | [L/M/H/Critical] |
```

#### 2.4 Add Domain Model and Abstraction Sections to Architect Template

**File**: `claude/architect.md` (and variants)

**Action**: Add sections:

```markdown
## Domain Model Alignment

| Domain Concept | Current Representation | Proposed Change | Alignment |
|----------------|----------------------|-----------------|-----------|
| [Concept] | [Current] | [New] | [Aligned/Drift] |

## Abstraction Consistency

| Layer | Current Abstraction | Change Impact | Consistency |
|-------|--------------------|--------------| ------------|
| [Layer] | [Current] | [Impact] | [Maintained/Broken] |
```

#### 2.5 Add Automation Strategy to QA Template

**File**: `claude/qa.md` (and variants)

**Action**: Add section:

```markdown
## Automation Strategy

| Test Area | Automate? | Rationale | Tool Recommendation |
|-----------|-----------|-----------|---------------------|
| [Area] | [Yes/No/Partial] | [Why] | [Tool] |

**Automation Coverage Target**: [%]
**Manual Testing Required**: [List scenarios]
```

### Priority 3: Nice to Have (Consider for Follow-up)

#### 3.1 Add Success Metrics Tracking

**New File**: `.agents/planning/IMPACT-ANALYSIS-METRICS.md`

**Action**: Create metrics tracking template:

```markdown
# Impact Analysis Framework Metrics

## Consultation Coverage

| Period | Total Plans | Plans with IA | Coverage % |
|--------|-------------|---------------|-----------|
| Week N | [Count] | [Count] | [%] |

## Issue Discovery Rate

| Period | Issues Found Pre-Impl | Issues Found Post-Impl | Prevention Rate |
|--------|----------------------|----------------------|-----------------|
| Week N | [Count] | [Count] | [%] |

## Planning Duration

| Feature | Without IA | With IA | Difference |
|---------|-----------|---------|------------|
| [Feature] | [Time] | [Time] | [Delta] |
```

#### 3.2 Update Critic Agent with IA Validation

**File**: `claude/critic.md` (if exists) or add to existing

**Action**: Add impact analysis validation checklist:

```markdown
## Impact Analysis Validation

When reviewing plans with impact analysis:

- [ ] All required specialist consultations completed
- [ ] Consultation Status marked as "Complete"
- [ ] Cross-domain risks identified and mitigated
- [ ] No conflicting recommendations unresolved
- [ ] Overall complexity assessment reasonable
- [ ] Implementation sequence addresses dependencies
```

#### 3.3 Add Orchestrator Guidance

**File**: `claude/orchestrator.md`

**Action**: Expand impact analysis section with:

```markdown
### Impact Analysis Orchestration

**Trigger Conditions**: Route to planner with impact analysis when:
- Feature touches 3+ domains
- Security-sensitive areas involved
- Breaking changes expected

**Handling Failed Consultations**:
1. Retry once with clarified prompt
2. If still failing, log gap and proceed with partial analysis
3. Flag in plan as "Incomplete: [missing domain]"

**Timeout Strategy**: Allow 2 iterations per specialist before escalation
```

---

## Recommended Merge Strategy

1. **Fix P1 issues** (markdown fences, consultation status marker)
2. **Fix P2 issues** (missing template sections)
3. **Create follow-up issue** for P3 items (metrics, critic integration)
4. **Merge with known limitations documented**

---

## Verification Checklist

After remediation, verify:

- [ ] All markdown files pass fence validation
- [ ] All 6 specialist templates have complete sections per PRD
- [ ] Planner template includes consultation status marker
- [ ] README and CLAUDE.md accurately reflect implementation
- [ ] Example walkthrough matches updated templates

---

## Appendix: Files Changed in Branch

| File | Change Type | PRD Alignment |
|------|-------------|---------------|
| `.agents/planning/IMPACT-ANALYSIS-EXAMPLE.md` | New | Good example, minor updates needed |
| `.agents/planning/IMPACT-ANALYSIS-FRAMEWORK.md` | New | Core documentation, complete |
| `CLAUDE.md` | Modified | Updated with framework info |
| `README.md` | Modified | Link to documentation added |
| `claude/architect.md` | Modified | Missing domain model sections |
| `claude/devops.md` | Modified | Missing dev experience section |
| `claude/implementer.md` | Modified | Missing breaking changes section |
| `claude/orchestrator.md` | Modified | Minimal update, needs expansion |
| `claude/planner.md` | Modified | Missing consultation status marker |
| `claude/qa.md` | Modified | Missing automation strategy |
| `claude/security.md` | Modified | Missing blast radius section |
| `copilot-cli/*.agent.md` | Modified | Markdown fence issues |
| `vs-code-agents/*.agent.md` | Modified | Markdown fence issues |

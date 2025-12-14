# Ideation Template

Use this template when processing ideation workflow artifacts.

## Phase 1: Research Document

**File**: `.agents/analysis/ideation-[topic].md`

```markdown
## Ideation Research: [Topic]

**Date**: [YYYY-MM-DD]
**Triggered By**: [URL / Issue / User request]
**Analyst**: [Agent session ID]

### Package/Technology Overview

[What it is, what problem it solves]

### Community Signal

| Metric | Value | Assessment |
|--------|-------|------------|
| GitHub Stars | | |
| Weekly Downloads | | |
| Open Issues | | |
| Last Release | | |
| Maintenance Status | | Active / Maintained / Stale |

### Technical Fit Assessment

**Current Codebase Compatibility**:
- [ ] Target framework compatible
- [ ] No dependency conflicts
- [ ] Aligns with existing patterns
- [ ] Build pipeline compatible

**Integration Points**:
[Where this would integrate]

### Integration Complexity

| Factor | Estimate |
|--------|----------|
| Files Affected | |
| Breaking Changes | None / Minor / Major |
| Migration Effort | Low / Medium / High |
| Documentation Updates | |

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| [Option A] | | | |
| [Option B] | | | |
| Do Nothing | | | |

### Risks and Concerns

- **Security**: [Assessment]
- **Licensing**: [License type and implications]
- **Maintenance**: [Long-term burden]
- **Community**: [Support quality]

### Recommendation

**Decision**: [Proceed / Defer / Reject]

**Rationale**:
- Evidence strength: [Strong / Moderate / Weak]
- Risk level: [Low / Medium / High]
- Strategic fit: [High / Medium / Low]

### Sources

- [Source 1]
- [Source 2]
```

## Phase 2: Validation Document

**File**: `.agents/analysis/ideation-[topic]-validation.md`

```markdown
## Ideation Validation: [Topic]

**Date**: [YYYY-MM-DD]
**Research Document**: `ideation-[topic].md`

### Agent Assessments

#### High-Level Advisor

**Question**: Does this align with product direction?

**Assessment**:
[Response]

**Verdict**: [Aligned / Partially Aligned / Not Aligned]

#### Independent Thinker

**Question**: What are we missing? What could go wrong?

**Concerns Raised**:
1. [Concern 1]
2. [Concern 2]

**Blind Spots Identified**:
[Any assumptions that weren't challenged]

#### Critic

**Question**: Is the analysis complete and accurate?

**Gaps Found**:
- [Gap 1]
- [Gap 2]

**Quality Assessment**: [Complete / Needs Work / Insufficient]

#### Roadmap

**Question**: Where does this fit in the product roadmap?

**Priority**: [P0 / P1 / P2 / P3]
**Wave**: [Current / Next / Future / Backlog]
**Dependencies**: [List any blockers]

### Consensus Decision

**Final Decision**: [Proceed / Defer / Reject]

**Conditions** (if Defer):
- [Condition 1]
- [Condition 2]

**Reasoning** (if Reject):
[Why this was rejected]

### Next Steps

- [ ] [Action 1]
- [ ] [Action 2]
```

## Phase 3: Epic Document

**File**: `.agents/roadmap/epic-[topic].md`

```markdown
## Epic: [Title]

**Created**: [YYYY-MM-DD]
**Status**: Draft / Approved / In Progress / Complete
**Wave**: [Wave identifier]

### Vision

[What success looks like - paint the picture]

### Outcomes (not outputs)

- [ ] [Measurable outcome 1]
- [ ] [Measurable outcome 2]
- [ ] [Measurable outcome 3]

### Success Metrics

| Metric | Current | Target | Measurement |
|--------|---------|--------|-------------|
| [Metric 1] | | | |
| [Metric 2] | | | |

### Scope Boundaries

**In Scope**:
- [Item 1]
- [Item 2]

**Out of Scope**:
- [Item 1]
- [Item 2]

### Dependencies

| Dependency | Status | Owner |
|------------|--------|-------|
| [Dependency 1] | | |
| [Dependency 2] | | |

### Stakeholders

| Role | Person/Team | Interest |
|------|-------------|----------|
| Sponsor | | |
| Users | | |
| Developers | | |

### Timeline

| Milestone | Target Date | Status |
|-----------|-------------|--------|
| Research Complete | | |
| Design Approved | | |
| Implementation Done | | |
| Released | | |
```

## Phase 4: Implementation Plan

**File**: `.agents/planning/implementation-plan-[topic].md`

```markdown
## Implementation Plan: [Topic]

**Epic**: `epic-[topic].md`
**PRD**: `prd-[topic].md`
**Status**: Draft / Under Review / Approved

### Review Summary

| Agent | Status | Notes |
|-------|--------|-------|
| Architect | Pending / Approved / Concerns | |
| DevOps | Pending / Approved / Concerns | |
| Security | Pending / Approved / Concerns | |
| QA | Pending / Approved / Concerns | |

### Architect Review

**Design Patterns**:
[Recommended patterns]

**Architectural Concerns**:
[Any issues identified]

**Verdict**: [Approved / Needs Changes]

### DevOps Review

**CI/CD Impact**:
[Changes needed]

**Infrastructure Requirements**:
[New infra needed]

**Verdict**: [Approved / Needs Changes]

### Security Review

**Threat Assessment**:
[Identified threats]

**Mitigations Required**:
[Security measures]

**Verdict**: [Approved / Needs Changes]

### QA Review

**Test Strategy**:
[Approach]

**Coverage Requirements**:
[Minimum coverage]

**Verdict**: [Approved / Needs Changes]

### Final Approval

**Consensus Reached**: [Yes / No]
**Approved By**: [List of approving agents]
**Date**: [YYYY-MM-DD]

### Work Breakdown

Reference: `.agents/planning/tasks-[topic].md`

| Task | Agent | Priority | Estimate |
|------|-------|----------|----------|
| [Task 1] | implementer | P0 | |
| [Task 2] | implementer | P1 | |
| [Task 3] | qa | P1 | |
```

## Usage

1. **Orchestrator** detects ideation trigger
2. **Analyst** creates research document using Phase 1 template
3. **Validation agents** populate Phase 2 document
4. If Proceed: **Roadmap** creates Epic (Phase 3)
5. **Explainer** creates PRD (separate template)
6. **Task-generator** creates WBS
7. **Review agents** populate implementation plan (Phase 4)
8. Implementation begins when all agents approve

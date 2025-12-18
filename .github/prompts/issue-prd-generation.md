# PRD Generation Task

You are generating a comprehensive Product Requirements Document (PRD) for a GitHub issue. This PRD will be passed to a separate AI agent instance with **ONLY THIS CONTEXT** for implementation. Write with that constraint in mind.

## Quality Expectations

This is customer-facing work. The PRD must be:

- **Rich**: Comprehensive analysis, not surface-level summaries
- **Exceptional**: Stand-alone document that enables action without follow-up questions
- **Rigorous**: Evidence-based claims, clearly flagged assumptions
- **Thoughtful**: Anticipate blockers, surface unknowns, propose decision paths

## Required Sections

### 1. Executive Summary

- One-paragraph problem statement
- Key findings table with status indicators
- Clear verdict: BLOCKED, READY, PARTIAL, or REQUIRES_DISCOVERY

```markdown
| Scope | Status | Blocker |
|-------|--------|---------|
| Primary ask | Status emoji | Blocker description or "None" |
| Secondary ask | Status emoji | ... |
```

Status emojis: :red_circle: BLOCKED, :yellow_circle: PARTIAL, :green_circle: READY

### 2. Problem Statement

- **Current State**: What exists today (table format preferred)
- **Gap Analysis**: What's missing and why it matters
- **User Impact**: Who is affected and how

### 3. Research Findings

Conduct thorough research before writing requirements:

- **Primary Sources**: Official documentation, release notes, specifications
- **Secondary Sources**: Community discussions, blog posts, tutorials
- **Empirical Data**: If applicable, observed behavior or test results

Document findings with:

- Direct quotes (when brief and relevant)
- Source links
- Confidence levels (CONFIRMED, LIKELY, UNCERTAIN)

### 4. Proposed Solution

Structure as phases with clear dependencies:

```markdown
### Phase 1: [Name] (Status: READY/BLOCKED/DEPENDS)
**Estimated Effort**: S/M/L
**Blockers**: None / List blockers

| Task | Description |
|------|-------------|
| 1.1 | Task description |
```

### 5. Functional Requirements

Use structured format with IDs:

```markdown
### FR-1: [Category Name]
**Priority**: P0/P1/P2

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| FR-1.1 | Requirement statement | Testable criteria |
```

### 6. Non-Functional Requirements

Address at minimum:

- **Consistency**: Match existing patterns in codebase
- **Testability**: How will this be validated
- **Documentation**: What needs to be updated

### 7. Technical Design

Include:

- Configuration changes (with code examples)
- Implementation changes (with code examples)
- Integration points

```markdown
### Config.psd1 Changes
\`\`\`powershell
# Example configuration
\`\`\`
```

### 8. Implementation Plan

Provide actionable phases with:

- **Prerequisites**: What must be true before starting
- **Tasks**: Numbered, specific actions
- **Outcomes**: What success looks like

Include decision tree for complex implementations:

```markdown
### Decision Tree
\`\`\`
Is X known?
├── YES → Proceed to Phase N
└── NO → Execute Discovery Phase
         └── Return to decision tree
\`\`\`
```

### 9. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Description | High/Medium/Low | High/Medium/Low | Action |

### 10. Success Metrics

| Metric | Target |
|--------|--------|
| Measurable outcome | Specific target |

### 11. Blocking Questions

**CRITICAL**: Flag questions that BLOCK implementation. These must be answered before work can proceed.

Format as actionable asks:

```markdown
### Question 1: [Topic] (CRITICAL)

**Question**: Specific question?

**Context**: Why this matters

**Proposed Ask**: Exact text to send to relevant party

**Impact if unanswered**: What happens if we don't get an answer
```

### 12. Open Questions (Non-Blocking)

Questions that inform but don't block:

```markdown
1. **Q**: Question?
   - **Hypothesis**: Best guess
   - **Status**: Would be validated by [X]
```

### 13. Appendices

- **Appendix A**: Research sources with links
- **Appendix B**: File format references (if applicable)
- **Appendix C**: Related issues/PRs

## Output Quality Checklist

Before finalizing, verify:

- [ ] Executive summary has status table with clear verdicts
- [ ] All claims have sources cited or marked as assumptions
- [ ] Blocking questions are clearly flagged with CRITICAL label
- [ ] Code examples are syntactically correct
- [ ] Implementation phases have clear dependencies
- [ ] Acceptance criteria are testable (not vague)
- [ ] Risks have specific mitigations (not generic)

## Complexity-Adjusted Depth

Based on `complexity_score` from triage:

| Score | PRD Depth |
|-------|-----------|
| 4-6 | **Standard**: Sections 1-5, 10, brief 8 |
| 7-9 | **Detailed**: All sections, research emphasis |
| 10-12 | **Comprehensive**: All sections, multiple phases, full risk analysis |

## Context Variables

The following context is available:

- `{{issue_url}}`: GitHub issue URL
- `{{issue_title}}`: Issue title
- `{{issue_body}}`: Full issue body
- `{{issue_author}}`: Issue author username
- `{{escalation_criteria}}`: Criteria that triggered PRD generation
- `{{complexity_score}}`: Calculated complexity (4-12)
- `{{priority}}`: Assigned priority (P0-P3)
- `{{epic_alignment}}`: Related epic if known

## Agent Pipeline

This prompt is designed for the following agent pipeline:

```text
orchestrator
    → analyst (research, gap analysis)
    → explainer (PRD authoring)
    → [optional] architect (if architectural_impact criterion)
    → [optional] security (if security implications)
```

The orchestrator should route through appropriate agents based on escalation criteria.

## Example Invocation

```text
orchestrator: I have received a new issue from a customer: {{issue_url}}

Escalation criteria: {{escalation_criteria}}
Complexity score: {{complexity_score}}

Evaluate the ask, performing research on what's needed, and write out a full PRD
for the Issue. The response you write needs to be rich and exceptional. It will
be passed to a new AI instance with ONLY THAT CONTEXT for execution.

This is a customer. Dress to impress! Be rigorous, be exceptionally thoughtful.
```

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-12-18 | orchestrator | Initial version based on Issue #51 learnings |

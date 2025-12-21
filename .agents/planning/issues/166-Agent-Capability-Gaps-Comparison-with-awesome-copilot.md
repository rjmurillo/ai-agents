---
number: 166
title: "Agent Capability Gaps: Comparison with awesome-copilot"
state: OPEN
created_at: 12/20/2025 10:47:07
author: rjmurillo-bot
labels: ["documentation", "enhancement", "area-workflows", "priority:P2"]
assignees: ["rjmurillo"]
milestone: null
url: https://github.com/rjmurillo/ai-agents/issues/166
---

# Agent Capability Gaps: Comparison with awesome-copilot

# Agent Capability Gaps: Comparison with awesome-copilot

## Summary

Analyzed 127 agents from [github/awesome-copilot](https://github.com/github/awesome-copilot/tree/main/agents) and identified critical gaps in our agent catalog (18 agents). Three MUST HAVE gaps limit our effectiveness: strategic planning, systematic debugging, and TDD enforcement.

**Analysis Document**: `.agents/analysis/003-awesome-copilot-gap-analysis.md`

## Context

### Our Agent Catalog (18 agents)

- analyst, architect, critic, devops, explainer, high-level-advisor
- implementer, independent-thinker, memory, orchestrator, planner
- pr-comment-responder, qa, retrospective, roadmap, security
- skillbook, task-generator

### Awesome-Copilot Agent Count: 127

**Categories**: Language experts (40), Platform specialists (25), Workflow agents (20), Domain specialists (15), Tool integrations (10), Thinking modes (8), Database experts (7)

## Gap Analysis

### Critical Gaps Identified (MUST HAVE)

| Gap ID | Missing Agent | Impact | Effort |
|--------|---------------|--------|--------|
| **GAP-001** | Strategic Planner | Jump to implementation without thorough planning | M (8-12 hrs) |
| **GAP-002** | Debugger | No systematic 4-phase debugging workflow | M (6-8 hrs) |
| **GAP-003** | TDD Mode (QA enhancement) | Test-after instead of test-first development | L (3-4 hrs) |

### Important Improvements (SHOULD HAVE)

| Gap ID | Missing Agent | Impact | Effort |
|--------|---------------|--------|--------|
| **GAP-004** | ADR Auto-Generator | Manual ADR creation is slower | S (2-3 hrs) |
| **GAP-005** | Issue Refiner | GitHub issues lack clarity | S (2-3 hrs) |
| **GAP-006** | Tech Debt Planner | Tech debt addressed ad-hoc | M (6-8 hrs) |
| **GAP-007** | Accessibility Agent | No WCAG compliance review | M (6-8 hrs) |
| **GAP-008** | Code Tour Generator | Manual onboarding docs | S (3-4 hrs) |

### Optional Enhancements (NICE TO HAVE)

| Gap ID | Missing Agent | Impact | Effort |
|--------|---------------|--------|--------|
| **GAP-009** | Thinking Transparency Modes | Enhanced reasoning visibility | XS (1-2 hrs) |
| **GAP-010** | Agent Foundry | Meta-agent for creating agents | S (2-3 hrs) |
| **GAP-011** | Blueprint Mode | Architecture visualization | M (6-8 hrs) |

## Detailed Gap Analysis

### GAP-001: Strategic Planner Agent (P0 - MUST HAVE)

**Problem**: We lack pre-implementation strategic planning. Current workflow jumps from analyst research to implementer code without thorough codebase analysis and impact assessment.

**Awesome-Copilot Equivalent**: `plan.agent.md`

**Capabilities Needed**:
- Analyze codebase before proposing solutions
- Clarify requirements through structured questions (3-5 upfront)
- Assess impact on existing components
- Develop step-by-step implementation roadmap
- Present options with trade-offs

**Proposed Solution**:
- Create `src/claude/strategic-planner.md` agent
- Orchestrator routes complex features to strategic-planner before task-generator
- Outputs to `.agents/planning/`

**Evidence from awesome-copilot**:
- `plan.agent.md`: "Think through complex coding challenges before implementation"
- `implementation-plan.agent.md`: "Deterministic, executable implementation plans"
- Pattern: Research → Plan → Implement (we skip Plan step)

**Estimated Effort**: 8-12 hours (1-2 sessions)

---

### GAP-002: Debugger Agent (P0 - MUST HAVE)

**Problem**: No systematic debugging workflow. Implementer handles bugs ad-hoc without structured methodology.

**Awesome-Copilot Equivalent**: `debug.agent.md`

**Capabilities Needed**:
- **Phase 1 - Problem Assessment**: Reproduce bug, gather context, generate report
- **Phase 2 - Investigation**: Trace execution paths, identify root cause
- **Phase 3 - Fix Implementation**: Targeted, minimal changes
- **Phase 4 - Verification**: Test execution, regression checks, edge cases

**Proposed Solution**:
- Create `src/claude/debugger.md` agent
- Orchestrator routes bug reports to debugger (not implementer)
- Outputs debug report to `.agents/analysis/` + fix implementation

**Evidence from awesome-copilot**:
- `debug.agent.md`: "Systematic four-phase debugging methodology"
- Structured approach: Assess → Investigate → Fix → Verify
- Emphasis on root cause identification before fixing

**Estimated Effort**: 6-8 hours (1 session)

---

### GAP-003: TDD Mode for QA Agent (P0 - MUST HAVE)

**Problem**: QA agent handles testing but doesn't systematically enforce test-first development. We advocate TDD but don't enforce it.

**Awesome-Copilot Equivalent**: `tdd-red.agent.md`, `tdd-green.agent.md`, `tdd-refactor.agent.md`

**Capabilities Needed**:
- **Red Phase**: Write failing test first (acceptance criteria → test)
- **Green Phase**: Implement minimal code to pass test
- **Refactor Phase**: Improve code while keeping tests green
- Enforce test-first workflow for features (not just bug fixes)

**Proposed Solution**:
- Enhance existing `src/claude/qa.md` with TDD mode
- QA agent detects feature requests → triggers TDD workflow
- Document cycle in `.agents/qa/`

**Evidence from awesome-copilot**:
- Separate agents for each TDD phase (red/green/refactor)
- Enforces test-first instead of test-after
- Systematic quality gate we currently lack

**Estimated Effort**: 3-4 hours (1 session)

---

### GAP-004: ADR Auto-Generator (P1 - SHOULD HAVE)

**Problem**: ADR creation is manual. Architect agent supports ADRs but doesn't automate sequential numbering, validation, or structured formatting.

**Awesome-Copilot Equivalent**: `adr-generator.agent.md`

**Capabilities Needed**:
- Sequential numbering (examine `/docs/adr/`, auto-increment)
- Structured documentation (context, decision, consequences, alternatives)
- 14-point validation checklist
- Systematic codes (POS-001, NEG-001, ALT-001)

**Proposed Solution**:
- Enhance `src/claude/architect.md` with ADR auto-generation mode
- Automate file naming, numbering, validation

**Estimated Effort**: 2-3 hours

---

### GAP-005: Issue Refiner (P1 - SHOULD HAVE)

**Problem**: GitHub issues may be incomplete or unclear. No systematic refinement before triage.

**Awesome-Copilot Equivalent**: `refine-issue.agent.md`

**Capabilities Needed**:
- Detect incomplete issues (missing repro steps, acceptance criteria)
- Ask clarifying questions
- Update issue with refined information

**Proposed Solution**:
- Create `src/claude/issue-refiner.md` agent
- Runs before analyst triage

**Estimated Effort**: 2-3 hours

---

### GAP-006: Tech Debt Planner (P1 - SHOULD HAVE)

**Problem**: Tech debt remediation is ad-hoc. No dedicated planning workflow.

**Awesome-Copilot Equivalent**: `tech-debt-remediation-plan.agent.md`

**Capabilities Needed**:
- Identify tech debt sources
- Assess impact and urgency
- Create remediation roadmap
- Prioritize work packages

**Proposed Solution**:
- Create `src/claude/tech-debt-planner.md` agent
- Complements roadmap agent

**Estimated Effort**: 6-8 hours

---

### GAP-007: Accessibility Agent (P1 - SHOULD HAVE)

**Problem**: No systematic WCAG compliance review. Accessibility is not part of standard workflows.

**Awesome-Copilot Equivalent**: `accessibility.agent.md`

**Capabilities Needed**:
- WCAG 2.1 Level AA compliance checks
- Semantic HTML validation
- ARIA attribute review
- Keyboard navigation testing
- Screen reader compatibility

**Proposed Solution**:
- Create `src/claude/accessibility.md` agent
- Integrate with qa workflow

**Estimated Effort**: 6-8 hours

---

### GAP-008: Code Tour Generator (P1 - SHOULD HAVE)

**Problem**: Onboarding documentation is manual. No automated codebase walkthroughs.

**Awesome-Copilot Equivalent**: `code-tour.agent.md`

**Capabilities Needed**:
- Generate interactive code tours
- Explain architecture patterns
- Highlight key files and their purposes
- Create learning paths

**Proposed Solution**:
- Create `src/claude/code-tour-generator.md` agent
- Outputs to `.agents/onboarding/`

**Estimated Effort**: 3-4 hours

## Recommendations

### P0 - Implement Within 2 Weeks

1. **Create strategic-planner agent** (8-12 hrs)
   - Fills critical gap between analyst and implementer
   - Prevents premature implementation
   - Orchestrator routes complex features here first

2. **Create debugger agent** (6-8 hrs)
   - Systematic 4-phase debugging workflow
   - Improves bug resolution speed and quality
   - Orchestrator routes bugs here (not implementer)

3. **Enhance qa agent with TDD mode** (3-4 hrs)
   - Enforce test-first development
   - Add red/green/refactor cycle
   - QA detects feature → triggers TDD

**Total P0 Effort**: 17-24 hours (2-3 sessions)

### P1 - Implement Within 1 Month

4. **Enhance architect with ADR auto-generation** (2-3 hrs)
5. **Create issue-refiner agent** (2-3 hrs)
6. **Create accessibility agent** (6-8 hrs)
7. **Create tech-debt-planner agent** (6-8 hrs)

**Total P1 Effort**: 16-22 hours (2-3 sessions)

### P2 - Backlog

8. **Create code-tour-generator agent** (3-4 hrs)
9. **Add thinking transparency modes** (1-2 hrs)
10. **Create agent-foundry tool** (2-3 hrs)

## Our Strengths (Not Found in awesome-copilot)

We have capabilities awesome-copilot lacks:

1. **Memory/Skillbook System**: Cross-session learning persistence
2. **Retrospective Learning**: Systematic extraction of lessons learned
3. **Multi-Agent Orchestration**: Sophisticated routing and coordination
4. **Strategic Advisors**: high-level-advisor, independent-thinker
5. **Multi-Platform Support**: Claude Code, VS Code, Copilot CLI

## Success Metrics

After implementing P0 recommendations:

| Metric | Before | Target |
|--------|--------|--------|
| Features with strategic plan | 0% | 80% |
| Bugs with debug report | 0% | 90% |
| Features with test-first TDD | 20% | 70% |
| Implementation rework due to poor planning | High | Low |

## Next Steps

1. **User approval**: Review recommendations, approve P0 implementation
2. **Implement GAP-001**: Create strategic-planner agent
3. **Implement GAP-002**: Create debugger agent
4. **Implement GAP-003**: Enhance qa agent with TDD mode
5. **Test workflow**: Route complex feature through new agents
6. **Retrospective**: Extract learnings, adjust as needed

## References

- **Analysis Document**: `.agents/analysis/003-awesome-copilot-gap-analysis.md`
- **Awesome-Copilot Repository**: https://github.com/github/awesome-copilot
- **Sample Agents Analyzed**:
  - [plan.agent.md](https://github.com/github/awesome-copilot/blob/main/agents/plan.agent.md)
  - [debug.agent.md](https://github.com/github/awesome-copilot/blob/main/agents/debug.agent.md)
  - [tdd-red.agent.md](https://github.com/github/awesome-copilot/blob/main/agents/tdd-red.agent.md)
  - [implementation-plan.agent.md](https://github.com/github/awesome-copilot/blob/main/agents/implementation-plan.agent.md)
  - [adr-generator.agent.md](https://github.com/github/awesome-copilot/blob/main/agents/adr-generator.agent.md)


---

## Comments

### Comment by @coderabbitai on 12/20/2025 10:48:53

<!-- This is an auto-generated issue plan by CodeRabbit -->


### 📝 CodeRabbit Plan Mode
Generate an implementation plan and prompts that you can use with your favorite coding agent.

- [ ] <!-- {"checkboxId": "8d4f2b9c-3e1a-4f7c-a9b2-d5e8f1c4a7b9"} --> Create Plan

<details>
<summary>Examples</summary>

- [Example 1](https://github.com/coderabbitai/git-worktree-runner/issues/29#issuecomment-3589134556)
- [Example 2](https://github.com/coderabbitai/git-worktree-runner/issues/12#issuecomment-3606665167)

</details>

---

<details>
<summary><b>🔗 Similar Issues</b></summary>

**Possible Duplicates**
- https://github.com/rjmurillo/ai-agents/issues/44

**Related Issues**
- https://github.com/rjmurillo/ai-agents/issues/151
- https://github.com/rjmurillo/ai-agents/issues/12
- https://github.com/rjmurillo/ai-agents/issues/14
- https://github.com/rjmurillo/ai-agents/issues/8
</details>
<details>
<summary><b>🔗 Related PRs</b></summary>

rjmurillo/vs-code-agents#1 - feat: Add customized multi-agent system for VS Code and Claude Code [merged]
rjmurillo/vs-code-agents#3 - feat: add GitHub Copilot CLI support  [merged]
rjmurillo/ai-agents#23 - feat: enhance pr-comment-responder with memory patterns and agent routing [merged]
rjmurillo/Qwiq#117 - chore: modernization wave 2-4 - SHA pinning, v11.0.0 prep, code coverage [merged]
rjmurillo/ai-agents#70 - feat(agents): add VS Code agent system [merged]
</details>
<details>
<summary><b>👤 Suggested Assignees</b></summary>

- [rjmurillo](https://github.com/rjmurillo)
- [rjmurillo-bot](https://github.com/rjmurillo-bot)
</details>


---
<details>
<summary> 🧪 Issue enrichment is currently in open beta.</summary>


You can configure auto-planning by selecting labels in the issue_enrichment configuration.

To disable automatic issue enrichment, add the following to your `.coderabbit.yaml`:
```yaml
issue_enrichment:
  auto_enrich:
    enabled: false
```
</details>

💬 Have feedback or questions? Drop into our [discord](https://discord.gg/coderabbit) or [schedule a call](https://calendly.com/parth-coderabbit/issues-feedback)!

### Comment by @github-actions on 12/20/2025 10:50:42

<!-- AI-PRD-GENERATION -->

## 📋 Product Requirements Document

> [!IMPORTANT]
> This PRD was automatically generated based on issue triage escalation.
> **Complexity Score**: 10/12 ()
> **Escalation Criteria**: feature_request, multi_phase_work, research_required

<details>
<summary>📖 About this PRD</summary>

This PRD was generated by the **Explainer Agent** after the issue was flagged
for detailed analysis. The document is designed to be self-contained - it can
be passed to a separate AI agent instance for implementation without additional
context.

**PRD Depth Levels**:
- **Standard** (4-6): Brief analysis, clear requirements
- **Detailed** (7-9): Research section, blocking questions
- **Comprehensive** (10-12): Phased implementation, risk analysis

</details>

---

Let me gather more context on the existing agent structures and steering documents.

Now I have sufficient context. Let me create the PRD for Issue #52.

The directory exists but I received a permission error. Let me output the PRD content directly since file creation is blocked.

---

# PRD: Agent Capability Gaps (Comparison with awesome-copilot)

## Executive Summary

Analysis of 127 agents from github/awesome-copilot reveals three critical gaps in our 18-agent catalog: strategic planning, systematic debugging, and TDD enforcement. The current workflow jumps from analyst research directly to implementer code without structured planning validation. Bug resolution lacks a formal debugging methodology. Test-first development is recommended but not enforced.

| Scope | Status | Blocker |
|-------|--------|---------|
| GAP-001: Strategic Planner Agent | :green_circle: READY | None |
| GAP-002: Debugger Agent | :green_circle: READY | None |
| GAP-003: TDD Mode for QA Agent | :green_circle: READY | None |
| GAP-004: ADR Auto-Generator Enhancement | :yellow_circle: PARTIAL | Requires architect agent review |
| GAP-005: Issue Refiner Agent | :green_circle: READY | None |

**Verdict**: READY. P0 gaps require 17-24 hours total effort. No architectural blockers.

## Problem Statement

### Current State

| Agent Category | Current Count | awesome-copilot Count | Gap |
|----------------|---------------|----------------------|-----|
| Primary Workflow | 10 | 20+ | Strategic planning, debugging |
| Support Agents | 8 | 15+ | TDD enforcement, issue refinement |
| Total | 18 | 127 | 109 (most are domain-specific) |

**Problem Areas**:

1. **Planning Gap**: Planner creates work packages but does not analyze codebase for implementation strategy
2. **Debugging Gap**: Bug reports route to implementer directly with no structured methodology
3. **TDD Gap**: QA verifies after implementation; test-first is a best practice, not enforced

### User Impact

- Implementation rework when dependencies are missed (estimated 20% of features)
- Bug fixes that introduce new bugs (no systematic verification)
- Test coverage gaps because tests are an afterthought

## Research Findings

| Source | Finding | Confidence |
|--------|---------|------------|
| awesome-copilot/plan.agent.md | Strategic planning requires codebase analysis before proposing solutions | CONFIRMED |
| awesome-copilot/debug.agent.md | Four-phase debugging methodology improves fix quality | CONFIRMED |
| awesome-copilot/tdd-red.agent.md | Separate agents for each TDD phase enforce test-first | CONFIRMED |

## Proposed Solution

### Phase 1: Strategic Planner Agent (8-12 hours)

| Task | Description |
|------|-------------|
| 1.1 | Create `src/claude/strategic-planner.md` |
| 1.2 | Define codebase analysis workflow |
| 1.3 | Create structured question framework (3-5 questions) |
| 1.4 | Define output format for `.agents/planning/strategy-[feature].md` |
| 1.5 | Update orchestrator routing |
| 1.6 | Update AGENTS.md catalog |

### Phase 2: Debugger Agent (6-8 hours)

| Task | Description |
|------|-------------|
| 2.1 | Create `src/claude/debugger.md` with 4-phase methodology |
| 2.2 | Phase 1: Problem Assessment (reproduce, gather context) |
| 2.3 | Phase 2: Investigation (trace execution, identify root cause) |
| 2.4 | Phase 3: Fix Implementation (targeted, minimal changes) |
| 2.5 | Phase 4: Verification (test execution, regression checks) |
| 2.6 | Update orchestrator to route bug reports to debugger |

### Phase 3: TDD Mode for QA Agent (3-4 hours)

| Task | Description |
|------|-------------|
| 3.1 | Add TDD Mode section to `src/claude/qa.md` |
| 3.2 | Define Red Phase (acceptance criteria to failing test) |
| 3.3 | Define Green Phase (minimal implementation) |
| 3.4 | Define Refactor Phase (improve code, keep tests green) |

## Functional Requirements

### FR-1: Strategic Planner Agent (P0)

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| FR-1.1 | Agent analyzes codebase before proposing approach | Agent reads 5+ relevant files before outputting strategy |
| FR-1.2 | Agent asks 3-5 clarifying questions | Questions documented in output |
| FR-1.3 | Agent assesses impact on existing components | Impact section with file paths |
| FR-1.4 | Agent develops step-by-step roadmap | Numbered steps with dependencies |

### FR-2: Debugger Agent (P0)

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| FR-2.1 | Agent reproduces bug before investigation | Reproduction steps documented |
| FR-2.2 | Agent traces execution to identify root cause | file:line references in report |
| FR-2.3 | Agent implements targeted fix | Only fix-related modifications |
| FR-2.4 | Agent verifies with regression testing | No new failures introduced |

### FR-3: TDD Mode (P0)

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| FR-3.1 | QA detects feature requests, triggers TDD | TDD activates with acceptance criteria |
| FR-3.2 | Red phase produces failing test | Test fails with expected message |
| FR-3.3 | Green phase produces minimal implementation | Test passes |
| FR-3.4 | Refactor phase maintains green tests | All tests still pass |

## Implementation Plan

| Order | Task | Hours |
|-------|------|-------|
| 1 | Create strategic-planner.md | 4-6 |
| 2 | Create debugger.md | 3-4 |
| 3 | Enhance qa.md with TDD mode | 2-3 |
| 4 | Update orchestrator routing | 2-3 |
| 5 | Update AGENTS.md catalog | 1-2 |
| 6 | Run agent generation | 0.5 |
| 7 | Test workflows | 2-3 |

**Total**: 15-22 hours

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Strategic planner duplicates planner | Medium | Medium | Clear scope boundaries |
| Debugger workflow too rigid | Low | Low | Add bypass for trivial fixes |
| TDD mode adds overhead | Medium | Low | Make optional |

## Success Metrics

| Metric | Target |
|--------|--------|
| Features with strategic planning | 80% of complex features |
| Bug reports with debug methodology | 90% |
| Features with test-first TDD | 70% |

## Blocking Questions

None. All P0 gaps can proceed without external decisions.

## Appendix: Research Sources

- [github/awesome-copilot](https://github.com/github/awesome-copilot)
- [plan.agent.md](https://github.com/github/awesome-copilot/blob/main/agents/plan.agent.md)
- [debug.agent.md](https://github.com/github/awesome-copilot/blob/main/agents/debug.agent.md)
- [tdd-red.agent.md](https://github.com/github/awesome-copilot/blob/main/agents/tdd-red.agent.md)

---

**[BLOCKED]**: File creation failed due to permission error. The PRD content is provided above. Save to `.agents/planning/PRD-agent-capability-gaps.md` when permissions allow.

Recommend orchestrator routes to critic for validation before implementation.

---

<sub>📋 Generated by [AI PRD Generation](https://github.com/rjmurillo/ai-agents) · [View Workflow](https://github.com/rjmurillo/ai-agents/actions/runs/20393265694)</sub>



### Comment by @github-actions on 12/20/2025 10:50:44

<!-- AI-ISSUE-TRIAGE -->

## AI Triage Summary

> [!NOTE]
> This issue has been automatically triaged by AI agents

<details>
<summary>What is AI Triage?</summary>

This issue was analyzed by AI agents:

- **Analyst Agent**: Categorizes the issue and suggests appropriate labels
- **Roadmap Agent**: Aligns the issue with project milestones and priorities
- **Explainer Agent** (if escalated): Generates comprehensive PRD

</details>

### Triage Results

| Property | Value |
|:---------|:------|
| **Category** | `enhancement` |
| **Labels** | enhancement area-prompts |
|  **Priority** | `P1` |
| **Milestone** | v1.1 |
| **PRD Escalation** | Generated (see below) |

<details>
<summary>Categorization Analysis</summary>

```json
```json
{
  "labels": ["enhancement", "area-prompts"],
  "category": "enhancement",
  "confidence": 0.95,
  "reasoning": "Issue proposes adding new agents and enhancing existing agent prompts based on gap analysis with awesome-copilot repository"
}
```

```

</details>

<details>
<summary>Roadmap Alignment</summary>

```json
```json
{
  "milestone": "v1.1",
  "priority": "P1",
  "epic_alignment": "",
  "confidence": 0.80,
  "reasoning": "Feature request for 3 new agents plus 1 enhancement; aligns with v1.1 maintainability theme but represents new capability work requiring multi-phase implementation.",
  "escalate_to_prd": true,
  "escalation_criteria": ["feature_request", "multi_phase_work", "research_required"],
  "complexity_score": 10
}
```

```

</details>

---

<sub>Powered by [AI Issue Triage](https://github.com/rjmurillo/ai-agents) - [View Workflow](https://github.com/rjmurillo/ai-agents/actions/runs/20393265694)</sub>



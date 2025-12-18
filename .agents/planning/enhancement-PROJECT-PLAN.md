# AI Agents Enhancement Project Plan

> **Version**: 1.0
> **Created**: 2025-12-17
> **Repository**: rjmurillo/ai-agents
> **Goal**: Reconcile Kiro planning patterns, Anthropic agent patterns, and existing implementation

---

## Executive Summary

This project enhances the ai-agents system with structured planning, parallel execution patterns, traceability validation, context-aware steering, and formal evaluator-optimizer loops. The work is organized into 6 phases spanning 12-18 sessions.

## Master Product Objective

Transform the ai-agents system into a reference implementation that combines:

1. **Kiro's Planning Discipline**: 3-tier spec hierarchy with EARS requirements
2. **Anthropic's Execution Patterns**: Parallel dispatch, voting, evaluator-optimizer
3. **Enterprise Traceability**: Cross-reference validation between artifacts
4. **Token Efficiency**: Context-aware steering injection

---

## Project Metrics

| Metric | Baseline | Target | Current |
|--------|----------|--------|---------|
| Planning artifacts | Ad-hoc | Structured 3-tier | - |
| Parallel execution | None | Fan-out documented | - |
| Traceability coverage | 0% | 100% | - |
| Steering token efficiency | N/A | 30% reduction | - |
| Evaluator loops | Manual | Automated 3-iteration | - |

---

## Phase Overview

| Phase | Name | Sessions | Dependencies | Status |
|-------|------|----------|--------------|--------|
| 0 | Foundation | 1-2 | None | 📋 Planned |
| 1 | Spec Layer | 2-3 | Phase 0 | 📋 Planned |
| 2 | Traceability | 2-3 | Phase 1 | 📋 Planned |
| 3 | Parallel Execution | 2-3 | Phase 0 | 📋 Planned |
| 4 | Steering Scoping | 2-3 | Phase 1 | 📋 Planned |
| 5 | Evaluator-Optimizer | 2-3 | Phase 2, 3 | 📋 Planned |
| 6 | Integration Testing | 1-2 | All phases | 📋 Planned |

**Total Estimated Sessions**: 12-18

---

## Phase 0: Foundation

**Goal**: Establish governance, directory structure, and project scaffolding.

### Tasks

| ID | Task | Complexity | Status | Session |
|----|------|------------|--------|---------|
| F-001 | Create `.agents/specs/{requirements,design,tasks}/` directories with READMEs | XS | 📋 | - |
| F-002 | Create `.agents/governance/naming-conventions.md` | S | 📋 | - |
| F-003 | Create `.agents/governance/consistency-protocol.md` | S | 📋 | - |
| F-004 | Create `.agents/steering/` directory with README | S | 📋 | - |
| F-005 | Update AGENT-SYSTEM.md with spec layer documentation | M | 📋 | - |
| F-006 | Initialize `.agents/HANDOFF.md` for enhancement project | S | 📋 | - |

### Acceptance Criteria

- [ ] All directories exist with README files
- [ ] Naming conventions documented with examples
- [ ] Consistency protocol aligns with existing critic workflow
- [ ] AGENT-SYSTEM.md reflects new architecture
- [ ] Can proceed to Phase 1

---

## Phase 1: Spec Layer (Requirements, Design, Tasks)

**Goal**: Implement Kiro's 3-tier planning hierarchy with EARS format.

### Background: EARS Format

EARS (Easy Approach to Requirements Syntax) enforces testable requirements:

```text
WHEN [precondition/trigger]
THE SYSTEM SHALL [action/behavior]
SO THAT [rationale/value]
```

### Tasks

| ID | Task | Complexity | Status | Session |
|----|------|------------|--------|---------|
| S-001 | Create EARS format template in `.agents/governance/ears-format.md` | S | 📋 | - |
| S-002 | Create `src/claude/spec-generator.md` agent prompt | L | 📋 | - |
| S-003 | Create YAML front matter schema for requirements | S | 📋 | - |
| S-004 | Create YAML front matter schema for design | S | 📋 | - |
| S-005 | Create YAML front matter schema for tasks | S | 📋 | - |
| S-006 | Update orchestrator with spec workflow routing | M | 📋 | - |
| S-007 | Create sample specs for existing feature (dogfood) | M | 📋 | - |
| S-008 | Document spec workflow in AGENT-SYSTEM.md | S | 📋 | - |

### YAML Schema Reference

```yaml
---
type: requirement | design | task
id: REQ-001 | DESIGN-001 | TASK-001
status: draft | review | approved | implemented
priority: P0 | P1 | P2
related:
  - REQ-001
  - DESIGN-002
created: YYYY-MM-DD
updated: YYYY-MM-DD
---
```

### Acceptance Criteria

- [ ] spec-generator agent produces valid EARS requirements
- [ ] All spec files have YAML front matter
- [ ] Orchestrator routes "create spec" requests correctly
- [ ] Sample specs demonstrate complete workflow

---

## Phase 2: Traceability Validation

**Goal**: Ensure all artifacts cross-reference correctly with automated validation.

### Traceability Rules

1. Every TASK must link to at least one DESIGN
2. Every DESIGN must link to at least one REQUIREMENT
3. No orphaned requirements (REQ without DESIGN)
4. No orphaned designs (DESIGN without TASK)
5. Status consistency (completed TASK implies completed chain)

### Tasks

| ID | Task | Complexity | Status | Session |
|----|------|------------|--------|---------|
| T-001 | Design traceability graph schema | M | 📋 | - |
| T-002 | Create `scripts/Validate-Traceability.ps1` script | L | 📋 | - |
| T-003 | Create pre-commit hook for traceability | M | 📋 | - |
| T-004 | Update critic agent with traceability checklist | M | 📋 | - |
| T-005 | Create orphan detection report format | S | 📋 | - |
| T-006 | Add traceability metrics to retrospective | S | 📋 | - |
| T-007 | Document traceability protocol | S | 📋 | - |

### Acceptance Criteria

- [ ] Validation script catches orphaned artifacts
- [ ] Pre-commit hook blocks commits with broken refs
- [ ] Critic validates traceability before approving
- [ ] Retrospective reports traceability coverage %

---

## Phase 3: Parallel Execution

**Goal**: Enable orchestrator to fan-out work to multiple agents.

### Background: Anthropic Patterns

- **Sectioning**: Split task into independent subtasks
- **Voting**: Run same task multiple times, select best
- **Aggregation**: Merge results from parallel execution

### Tasks

| ID | Task | Complexity | Status | Session |
|----|------|------------|--------|---------|
| P-001 | Design parallel dispatch protocol | M | 📋 | - |
| P-002 | Update orchestrator with parallel capability documentation | L | 📋 | - |
| P-003 | Create result aggregation patterns | M | 📋 | - |
| P-004 | Implement voting mechanism documentation | M | 📋 | - |
| P-005 | Update impact analysis for parallel consultations | M | 📋 | - |
| P-006 | Add parallel execution metrics to session logs | S | 📋 | - |
| P-007 | Document parallel execution in AGENT-SYSTEM.md | S | 📋 | - |

### Aggregation Strategies

| Strategy | Use Case | Behavior |
|----------|----------|----------|
| **merge** | Non-conflicting outputs | Combine all outputs |
| **vote** | Redundant execution | Select majority |
| **escalate** | Conflicts detected | Route to high-level-advisor |

### Acceptance Criteria

- [ ] Orchestrator documents parallel dispatch capability
- [ ] Aggregation patterns defined and documented
- [ ] Impact analysis notes parallel potential
- [ ] Session logs track parallel metrics

---

## Phase 4: Steering Scoping

**Goal**: Inject only relevant steering content based on file context.

### Background: Kiro Pattern

Kiro uses glob-based inclusion to reduce token usage:

```yaml
api-patterns.md → *.ts, src/api/*
testing-approach.md → **/*.test.ts
```

### Tasks

| ID | Task | Complexity | Status | Session |
|----|------|------------|--------|---------|
| ST-001 | Design steering file schema with glob patterns | M | 📋 | - |
| ST-002 | Create steering files for key domains | M | 📋 | - |
| ST-003 | Document steering injection logic in orchestrator | L | 📋 | - |
| ST-004 | Add token usage tracking to session logs | S | 📋 | - |
| ST-005 | Measure baseline vs scoped steering token usage | S | 📋 | - |
| ST-006 | Update agent prompts to reference steering files | M | 📋 | - |
| ST-007 | Document steering system in AGENT-SYSTEM.md | S | 📋 | - |

### Steering File Structure

```text
.agents/steering/
├── README.md                 # Steering system overview
├── csharp-patterns.md       # *.cs → SOLID, performance
├── agent-prompts.md         # src/claude/*.md → prompt engineering
├── testing-approach.md      # **/*.test.*, **/*.spec.*
├── security-practices.md    # **/Auth/**, *.env*
└── documentation.md         # **/*.md (non-agent)
```

### Acceptance Criteria

- [ ] Steering files organized by domain
- [ ] Glob patterns documented
- [ ] Token savings estimated (target: 30%+)
- [ ] Agents can reference steering guidance

---

## Phase 5: Evaluator-Optimizer Loop

**Goal**: Formalize the generator-evaluator-regenerate pattern.

### Background: Anthropic Pattern

```text
Generator → Evaluator → (Accept or Regenerate with feedback)
```

### Tasks

| ID | Task | Complexity | Status | Session |
|----|------|------------|--------|---------|
| E-001 | Design evaluator-optimizer protocol | M | 📋 | - |
| E-002 | Update independent-thinker with evaluation rubric | M | 📋 | - |
| E-003 | Add regeneration capability to orchestrator | L | 📋 | - |
| E-004 | Define acceptance criteria for loop termination | S | 📋 | - |
| E-005 | Add evaluation metrics to session logs | S | 📋 | - |
| E-006 | Create evaluation history tracking | M | 📋 | - |
| E-007 | Document evaluator-optimizer in AGENT-SYSTEM.md | S | 📋 | - |

### Evaluation Rubric

| Criterion | Weight | Description |
|-----------|--------|-------------|
| Completeness | 25% | All requirements addressed |
| Correctness | 25% | No factual errors |
| Clarity | 25% | Unambiguous language |
| Actionability | 25% | Can be executed without clarification |

### Loop Termination

- Score >= 70%: Accept
- Score < 70% AND iterations < 3: Regenerate with feedback
- Iterations >= 3: Escalate to user

### Acceptance Criteria

- [ ] Evaluation rubric defined
- [ ] independent-thinker outputs structured scores
- [ ] Orchestrator documents regeneration capability
- [ ] Session logs include evaluation metrics

---

## Phase 6: Integration Testing

**Goal**: Validate all phases work together end-to-end.

### Test Scenario: New Agent Creation

Use "pr-review-digest" agent as the test case:

1. User provides vibe-level prompt
2. spec-generator creates requirements (EARS)
3. architect creates design
4. task-generator creates atomic tasks
5. Traceability validation passes
6. Parallel impact analysis with specialists
7. Evaluator-optimizer refines plan
8. Implementation with steering context
9. Retrospective extracts learnings

### Tasks

| ID | Task | Complexity | Status | Session |
|----|------|------------|--------|---------|
| I-001 | Define end-to-end test scenario | M | 📋 | - |
| I-002 | Execute spec workflow (requirements → design → tasks) | L | 📋 | - |
| I-003 | Validate traceability across all artifacts | M | 📋 | - |
| I-004 | Test parallel execution with real feature | M | 📋 | - |
| I-005 | Measure steering token efficiency | S | 📋 | - |
| I-006 | Test evaluator-optimizer on generated output | M | 📋 | - |
| I-007 | Conduct project retrospective | M | 📋 | - |
| I-008 | Update all documentation with learnings | M | 📋 | - |

### Acceptance Criteria

- [ ] End-to-end workflow completes
- [ ] All traceability checks pass
- [ ] Parallel execution documented
- [ ] Token savings achieved (30%+ target)
- [ ] Evaluator loop improves quality
- [ ] Retrospective captures patterns

---

## Risk Register

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Claude Code sequential limits parallel | High | Medium | Design for logical parallelism, not runtime |
| EARS format too rigid | Medium | Medium | Allow escape hatch for edge cases |
| Traceability overhead slows development | Medium | High | Make validation fast, optional in WIP |
| Steering glob matching complexity | Low | Medium | Start simple, iterate |
| Evaluator loop infinite regression | Low | High | Hard cap at 3 iterations |

---

## Success Criteria

Project is complete when:

- [ ] All phases completed with passing acceptance criteria
- [ ] End-to-end test scenario successful
- [ ] Documentation updated and reviewed
- [ ] Token usage reduced by 30%+ for focused tasks
- [ ] Traceability coverage at 100%
- [ ] Retrospective conducted with learnings persisted

---

## Session Log

| Session | Date | Phase | Tasks | Status | Log |
|---------|------|-------|-------|--------|-----|
| 1 | - | 0 | F-001 to F-006 | 📋 | - |

---

## Changelog

| Date | Version | Changes |
|------|---------|---------|
| 2025-12-17 | 1.0 | Initial project plan |

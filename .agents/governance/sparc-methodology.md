# SPARC Development Methodology

Structured development phases with quality gates between transitions.
Adapted from claude-flow's SPARC framework for the ai-agents multi-agent system.

## Phases

Five sequential phases map to existing agent specializations.
Each phase produces artifacts. Quality gates block progression until criteria pass.

### Phase 1: Specification

**Agent**: analyst
**Mode**: `spec`
**Purpose**: Capture requirements, constraints, and acceptance criteria.

**Artifacts**:

- Requirements document (EARS format per ADR-029)
- Constraint inventory
- Acceptance criteria checklist

**Activities**:

- Gather user stories and requirements
- Identify constraints and dependencies
- Define acceptance criteria
- Search existing memories for related patterns

### Phase 2: Pseudocode

**Agent**: milestone-planner
**Mode**: `plan`
**Purpose**: Design algorithms, data flows, and test anchors.

**Artifacts**:

- Task breakdown with dependencies
- Algorithm sketches or pseudocode
- Test anchor definitions (what to test, not how)

**Activities**:

- Decompose work into ordered tasks
- Identify data flows and interfaces
- Define test anchors for each component
- Sequence by dependency

### Phase 3: Architecture

**Agent**: architect
**Mode**: `architect`
**Purpose**: Design system structure, API contracts, and security patterns.

**Artifacts**:

- ADR (if architectural decision required)
- Component diagram or interface definitions
- Security threat model (if applicable)

**Activities**:

- Define component boundaries
- Design interfaces (consumer perspective first)
- Evaluate CVA: commonality, variability, relationships
- Review security implications

### Phase 4: Refinement

**Agent**: implementer
**Mode**: `tdd`
**Purpose**: Implement using Test-Driven Development (Red-Green-Refactor).

**Artifacts**:

- Tests (written first)
- Implementation code
- Passing test suite

**Activities**:

- Write failing tests (Red)
- Implement minimal code to pass (Green)
- Refactor for quality (Refactor)
- Verify cyclomatic complexity, cohesion, coupling

### Phase 5: Completion

**Agents**: qa, explainer
**Mode**: `integration`
**Purpose**: Validate integration, generate documentation, finalize.

**Artifacts**:

- Integration test results
- Updated documentation
- Session log with evidence

**Activities**:

- Run full test suite
- Validate cross-component integration
- Generate or update documentation
- Complete session protocol

## Quality Gates

Each gate defines blocking criteria. Progression requires all MUST items to pass.

### Gate 1: Specification to Pseudocode

| Level | Criterion | Evidence |
|-------|-----------|----------|
| MUST | Requirements documented in EARS format | File path |
| MUST | Acceptance criteria defined | Checklist exists |
| SHOULD | Related memories searched | Search results logged |
| SHOULD | Constraints identified | Constraint list exists |

### Gate 2: Pseudocode to Architecture

| Level | Criterion | Evidence |
|-------|-----------|----------|
| MUST | Tasks decomposed with dependencies | Task list exists |
| MUST | Test anchors defined | Test plan documented |
| SHOULD | Algorithm reviewed for correctness | Review notes |

### Gate 3: Architecture to Refinement

| Level | Criterion | Evidence |
|-------|-----------|----------|
| MUST | Critic review verdict is PASS | Critic output logged |
| MUST | Interfaces defined from consumer perspective | API contracts exist |
| MUST | Security review (if security-sensitive) | Threat model or waiver |
| SHOULD | ADR created (if architectural decision) | ADR file path |

### Gate 4: Refinement to Completion

| Level | Criterion | Evidence |
|-------|-----------|----------|
| MUST | All tests pass | Test output with exit code 0 |
| MUST | No test failures or errors | Zero non-pass results |
| SHOULD | Cyclomatic complexity under 10 | Lint output |
| SHOULD | Code reviewed by critic | Review verdict |

### Gate 5: Completion to Done

| Level | Criterion | Evidence |
|-------|-----------|----------|
| MUST | Full test suite passes | Test output |
| MUST | Documentation updated | File paths |
| MUST | Session log complete | Validation passes |
| SHOULD | Retrospective captured (significant work) | Memory written |

## Mode Selection

The orchestrator selects the entry phase based on task complexity.

| Task Type | Entry Phase | Rationale |
|-----------|-------------|-----------|
| Quick fix | Phase 4 (Refinement) | Requirements already clear |
| Bug fix | Phase 1 (Specification) | Need root cause analysis |
| New feature | Phase 1 (Specification) | Full methodology |
| Architecture change | Phase 3 (Architecture) | Design focus |
| Documentation only | Phase 5 (Completion) | Final phase only |

## Phase Tracking

Sessions track the current development phase in the session log.

```json
{
  "developmentPhase": {
    "current": "refinement",
    "history": [
      {"phase": "specification", "gate": "passed", "timestamp": "2026-01-15T10:00:00Z"},
      {"phase": "pseudocode", "gate": "passed", "timestamp": "2026-01-15T10:30:00Z"},
      {"phase": "architecture", "gate": "passed", "timestamp": "2026-01-15T11:00:00Z"},
      {"phase": "refinement", "gate": "in_progress", "timestamp": "2026-01-15T11:30:00Z"}
    ]
  }
}
```

## Relationship to Existing Workflows

SPARC phases map to existing AGENT-SYSTEM.md workflow patterns:

| SPARC Phase | Workflow Pattern | Agents |
|-------------|-----------------|--------|
| Specification | Standard Development (analysis step) | analyst |
| Pseudocode | Standard Development (planning step) | milestone-planner |
| Architecture | Standard Extended (architecture step) | architect, critic |
| Refinement | Standard Development (implementation step) | implementer |
| Completion | Standard Development (validation step) | qa, explainer |

Quick Fix Flow maps to Phase 4 + Phase 5 only.
Strategic Decision Flow maps to Phase 1 + Phase 3 only.

## Enforcement

Phase gates use the hybrid enforcement pattern from SKILL-PHASE-GATES.md:

- Documentation gates in agent prompts (soft enforcement)
- Script validation via `validate_phase_gates.py` (hard enforcement)
- Session log tracking for audit trail

## References

- [Claude-flow Architecture Analysis](../analysis/claude-flow-architecture-analysis.md)
- [Skill Phase Gates](./SKILL-PHASE-GATES.md)
- [Agent System Workflows](../AGENT-SYSTEM.md#3-workflow-patterns)
- [Session Protocol](../SESSION-PROTOCOL.md)

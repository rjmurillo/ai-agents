# AI Agents Enhancement Project Plan

> **Version**: 2.3
> **Created**: 2025-12-17
> **Updated**: 2026-01-02
> **Repository**: rjmurillo/ai-agents
> **Goal**: Unify Kiro planning patterns, claude-flow capabilities, and Anthropic agent patterns

---

## Executive Summary

This project enhances the ai-agents system with structured planning, parallel execution patterns, intelligent memory systems, session automation, and formal evaluator-optimizer loops. The work is organized into 8 phases spanning approximately 20-30 sessions.

**Version 2.0 Changes**: Merged Epic #183 (claude-flow inspired enhancements) into this plan, creating a unified roadmap that combines:

- Kiro's 3-tier spec hierarchy with EARS requirements
- Claude-flow's performance optimizations (parallel execution, vector memory)
- Anthropic's execution patterns (voting, evaluator-optimizer)
- SESSION-PROTOCOL integration for automated compliance

## Master Product Objective

Transform the ai-agents system into a reference implementation that combines:

1. **Kiro's Planning Discipline**: 3-tier spec hierarchy with EARS requirements
2. **Claude-flow's Performance**: Parallel execution, vector memory, batch operations
3. **Anthropic's Execution Patterns**: Parallel dispatch, voting, evaluator-optimizer
4. **Enterprise Traceability**: Cross-reference validation between artifacts
5. **Token Efficiency**: Context-aware steering injection
6. **Session Automation**: Lifecycle hooks, checkpointing, automated compliance

---

## Issue Tracking

This plan consolidates work from:

- Original PROJECT-PLAN.md (Phases 0-6)
- Epic #183: Claude-Flow Inspired Enhancements (#167-#181)

| Issue | Title | Integrated Into |
|-------|-------|-----------------|
| #167 | Vector Memory System | Phase 2A (Memory) |
| #168 | Parallel Agent Execution | Phase 3 |
| #169 | Metrics Collection | Phase 2 |
| #170 | Lifecycle Hooks | Phase 5A (Automation) |
| #171 | Consensus Mechanisms | Phase 5 |
| #172 | SPARC-like Methodology | Phase 5 |
| #173 | Skill Auto-Consolidation | Phase 5A (Automation) |
| #174 | Session Checkpointing | Phase 5A (Automation) |
| #175 | Swarm Coordination Modes | Phase 3 |
| #176 | Neural Pattern Learning | Phase 2A (Memory) |
| #177 | Stream Processing | Phase 6 |
| #178 | Health Status | Phase 6 |
| #179 | MCP Tool Ecosystem | Phase 6 |
| #180 | Reflexion Memory | Phase 2A (Memory) |
| #181 | CLI Init Command | Phase 0 |
| #721 | Graph Performance Optimization | Phase 2B (Graph Performance) |
| #722 | Spec Management Tooling | Phase 2C (Spec Tooling) |
| #723 | Frontmatter Standardization | Phase 2 (Documentation) |
| #724 | Programming-Advisor Graph Consultation | Phase 2B (Graph Performance) |
| #725 | Mermaid Diagram Conversion | Phase 2 (Documentation) |
| #739 | Workflow Orchestration Enhancement | Phase 7 (MoAI-inspired) |

---

## Project Metrics

| Metric | Baseline | Target | Current |
|--------|----------|--------|---------|
| Planning artifacts | Ad-hoc | Structured 3-tier | Foundation complete |
| Parallel execution | None | 2.8-4.4x speed improvement | Phase 3 pending |
| Memory search | Sequential | 96-164x faster (vector) | MemoryRouter + Forgetful (PR #735) |
| Traceability coverage | 0% | 100% | Framework in place |
| Steering token efficiency | N/A | 30% reduction | 5 files ready |
| Evaluator loops | Manual | Automated 3-iteration | Phase 5 pending |
| Session automation | Manual protocol | Hooks-driven | Phase 5A pending |

---

## Phase Overview

| Phase | Name | Sessions | Dependencies | Status |
|-------|------|----------|--------------|--------|
| 0 | Foundation | 1-2 | None | COMPLETE |
| 1 | Spec Layer | 2-3 | Phase 0 | COMPLETE |
| 2 | Traceability + Metrics | 2-3 | Phase 1 | COMPLETE (Traceability) |
| 2A | Memory System | 3-4 | Phase 0 | COMPLETE |
| 2B | Graph Performance | 1-2 | Phase 2 | PENDING |
| 2C | Spec Management Tooling | 1-2 | Phase 2, 2B | PENDING |
| 3 | Parallel Execution | 2-3 | Phase 0, 2A | PENDING |
| 4 | Steering Scoping | 2-3 | Phase 1 | PARTIAL |
| 5 | Evaluator-Optimizer | 2-3 | Phase 2, 3 | PENDING |
| 5A | Session Automation | 2-3 | Phase 0, 2A | PENDING |
| 6 | Integration Testing | 2-3 | All phases | PENDING |
| 7 | Workflow Orchestration UX | 2-3 | Phase 3, 5A | PENDING |

**Total Estimated Sessions**: 24-37

---

## Phase 0: Foundation - COMPLETE

**Goal**: Establish governance, directory structure, and project scaffolding.

### Tasks

| ID | Task | Complexity | Status | Linked Issue |
|----|------|------------|--------|--------------|
| F-001 | Create `.agents/specs/{requirements,design,tasks}/` directories with READMEs | XS | COMPLETE | - |
| F-002 | Create `.agents/governance/naming-conventions.md` | S | COMPLETE | - |
| F-003 | Create `.agents/governance/consistency-protocol.md` | S | COMPLETE | - |
| F-004 | Create `.agents/steering/` directory with README | S | COMPLETE | - |
| F-005 | Update AGENT-SYSTEM.md with spec layer documentation | M | COMPLETE | - |
| F-006 | Initialize `.agents/HANDOFF.md` for enhancement project | S | COMPLETE | - |
| F-007 | CLI init command scaffolding (deferred to CLI tooling phase) | M | DEFERRED | #181 |

### Acceptance Criteria

- [x] All directories exist with README files
- [x] Naming conventions documented with examples
- [x] Consistency protocol aligns with existing critic workflow
- [x] AGENT-SYSTEM.md reflects new architecture
- [x] SESSION-PROTOCOL.md established with RFC 2119 compliance
- [x] Can proceed to Phase 1

### Deliverables

| Artifact | Location | Status |
|----------|----------|--------|
| Spec directories | `.agents/specs/{requirements,design,tasks}/` | COMPLETE |
| Naming conventions | `.agents/governance/naming-conventions.md` | COMPLETE |
| Consistency protocol | `.agents/governance/consistency-protocol.md` | COMPLETE |
| Steering directory | `.agents/steering/` | COMPLETE |
| Session protocol | `.agents/SESSION-PROTOCOL.md` | COMPLETE |
| HANDOFF.md | `.agents/HANDOFF.md` | COMPLETE |

---

## Phase 1: Spec Layer (Requirements, Design, Tasks) - COMPLETE

**Goal**: Implement Kiro's 3-tier planning hierarchy with EARS format.

### Background: EARS Format

EARS (Easy Approach to Requirements Syntax) enforces testable requirements:

```text
WHEN [precondition/trigger]
THE SYSTEM SHALL [action/behavior]
SO THAT [rationale/value]
```

### Tasks

| ID | Task | Complexity | Status | Session | PR |
|----|------|------------|--------|---------|-----|
| S-001 | Create EARS format template in `.agents/governance/ears-format.md` | S | COMPLETE | - | #603 |
| S-002 | Create `src/claude/spec-generator.md` agent prompt | L | COMPLETE | - | #605 |
| S-003 | Create YAML front matter schema for requirements | S | COMPLETE | - | #604 |
| S-004 | Create YAML front matter schema for design | S | COMPLETE | - | #604 |
| S-005 | Create YAML front matter schema for tasks | S | COMPLETE | - | #604 |
| S-006 | Update orchestrator with spec workflow routing | M | COMPLETE | - | #605 |
| S-007 | Create sample specs for existing feature (dogfood) | M | COMPLETE | - | #605 |
| S-008 | Document spec workflow in AGENT-SYSTEM.md | S | COMPLETE | - | #690 |

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

- [x] spec-generator agent produces valid EARS requirements
- [x] All spec files have YAML front matter
- [x] Orchestrator routes "create spec" requests correctly
- [x] Sample specs demonstrate complete workflow

---

## Phase 2: Traceability Validation + Metrics

**Goal**: Ensure all artifacts cross-reference correctly with automated validation. Add metrics collection for performance monitoring.

### Traceability Rules

1. Every TASK must link to at least one DESIGN
2. Every DESIGN must link to at least one REQUIREMENT
3. No orphaned requirements (REQ without DESIGN)
4. No orphaned designs (DESIGN without TASK)
5. Status consistency (completed TASK implies completed chain)

### Tasks

| ID | Task | Complexity | Status | Linked Issue | PR |
|----|------|------------|--------|--------------|-----|
| T-001 | Design traceability graph schema | M | COMPLETE | - | #715 |
| T-002 | Create `scripts/Validate-Traceability.ps1` script | L | COMPLETE | - | #715 |
| T-003 | Create pre-commit hook for traceability | M | COMPLETE | - | #715 |
| T-004 | Update critic agent with traceability checklist | M | COMPLETE | - | #715 |
| T-005 | Create orphan detection report format | S | COMPLETE | - | #715 |
| T-006 | Add traceability metrics to retrospective | S | COMPLETE | - | #715 |
| T-007 | Document traceability protocol | S | COMPLETE | - | #715 |
| T-008 | Design metrics collection schema | M | COMPLETE | #169 | #742 |
| T-009 | Implement session metrics capture | M | PENDING | #169 | - |
| T-010 | Create performance monitoring dashboard spec | L | PENDING | #169 | - |

### Acceptance Criteria

- [x] Validation script catches orphaned artifacts
- [x] Pre-commit hook blocks commits with broken refs
- [x] Critic validates traceability before approving
- [x] Retrospective reports traceability coverage %
- [ ] Session metrics captured automatically
- [ ] Performance trends visible in dashboard

---

## Phase 2A: Memory System (claude-flow inspired)

**Goal**: Implement intelligent memory systems for faster context retrieval and pattern learning.

### Background: Claude-flow Performance

Claude-flow demonstrates:

- **96-164x faster memory search** with vector database
- **Reflexion memory** for causal reasoning
- **Neural pattern learning** from execution history

### Tasks

| ID | Task | Complexity | Status | Linked Issue | PR |
|----|------|------------|--------|--------------|-----|
| M-001 | Design vector memory architecture | L | COMPLETE | #167 | #735 |
| M-002 | Implement semantic search for context retrieval | L | COMPLETE | #167 | #735 |
| M-003 | Integrate with existing Serena memory system | M | COMPLETE | #167 | #735 |
| M-004 | Design reflexion memory schema | M | COMPLETE | #180 | #735 |
| M-005 | Implement causal reasoning storage | L | COMPLETE | #180 | #735 |
| M-006 | Design neural pattern storage format | M | PENDING | #176 | - |
| M-007 | Implement pattern extraction from retrospectives | M | PENDING | #176 | - |
| M-008 | Create memory search benchmarks | S | COMPLETE | #167 | #735 |
| M-009 | Bootstrap ai-agents project into memory system | L | COMPLETE | #167 | S-205 |

### Architecture

```text
                    +------------------+
                    |  Memory Router   |
                    +--------+---------+
                             |
         +-------------------+-------------------+
         |                   |                   |
+--------v-------+  +--------v-------+  +--------v-------+
| Vector Memory  |  | Reflexion Mem  |  | Neural Patterns|
| (Semantic)     |  | (Causal)       |  | (Learning)     |
+----------------+  +----------------+  +----------------+
| #167           |  | #180           |  | #176           |
+----------------+  +----------------+  +----------------+
```

### Acceptance Criteria

- [x] Semantic search faster than sequential scan (Forgetful MCP provides 96-164x improvement)
- [x] Causal reasoning improves debugging (ReflexionMemory.psm1, ADR-038)
- [ ] Pattern learning reduces repeated errors (M-006, M-007 pending)
- [x] Integration with existing cloudmcp-manager and Serena (MemoryRouter.psm1, ADR-037)
- [x] Project knowledge bootstrapped into memory system (M-009 complete, S-205)

### Implementation Notes (PR #735)

**Delivered Artifacts:**

| Component | Location | Description |
|-----------|----------|-------------|
| Memory Router | `.claude/skills/memory/scripts/MemoryRouter.psm1` | Unified Serena + Forgetful access |
| Reflexion Memory | `.claude/skills/memory/scripts/ReflexionMemory.psm1` | 4-tier episodic/causal memory |
| Search Skill | `.claude/skills/memory/scripts/Search-Memory.ps1` | Agent-facing search interface |
| Benchmarks | `.claude/skills/memory/scripts/Measure-MemoryPerformance.ps1` | Performance measurement |
| Health Check | `.claude/skills/memory/scripts/Test-MemoryHealth.ps1` | MCP connectivity validation |

**Related ADRs:**

- ADR-037: Memory Router Architecture
- ADR-038: Reflexion Memory Schema

**Test Coverage:** 113 tests passing (MemoryRouter: 38, ReflexionMemory: 62, Search-Memory: 13)

### Bootstrap Task (M-009)

**Objective**: Validate memory infrastructure with real project data.

**Approach**:
- Use `encode-repo-serena` skill (created in PR #740)
- Populate Forgetful with existing Serena memories
- Create entity relationships from `.agents/` artifacts
- Build knowledge graph from ADRs, session logs, skills
- Validate search performance with real queries

**Success Criteria** (Session 205):
- ✅ Semantic memories created (11 foundation + architecture memories in Forgetful)
- ✅ Entity graph navigable (13 entities, 5 relationships: ADRs ↔ Modules ↔ Services ↔ Agents)
- ⚠️ Search latency ~1.9s (defer optimization to Phase 2B G-003: Caching Strategy)
- ✅ Memory Router routing verified (Serena-first with graceful Forgetful degradation)

---

## Phase 2B: Graph Performance Optimization

**Goal**: Optimize the traceability graph for speed, robustness, and durability while maintaining markdown-only storage.

### Background

From PR #715 review:
> This is a fun graph problem that's recomposing itself from the markdown each time. What's programming-advisor skill say about this? If we keep our own implementation of a poor man's graph database that's accessible without extra MCP... how do we make sure this is 1) super fast, 2) robust, 3) durable?

**Project Principle**: Everything should be markdown and accessible without special tools, configuration, or context bloat.

### Tasks

| ID | Task | Complexity | Status | Linked Issue |
|----|------|------------|--------|--------------|
| G-001 | Consult programming-advisor on graph implementation | M | PENDING | #724 |
| G-002 | Analyze algorithmic complexity of current traversal | S | PENDING | #721 |
| G-003 | Design caching strategy (no external state) | M | PENDING | #721 |
| G-004 | Implement performance optimizations | L | PENDING | #721 |
| G-005 | Create performance benchmarks | S | PENDING | #721 |
| G-006 | Document best practices for markdown-based graphs | S | PENDING | #721 |

### Acceptance Criteria

- [ ] Programming-advisor consultation completed
- [ ] Graph traversal performance benchmarked
- [ ] Caching strategy documented (markdown-only)
- [ ] No external dependencies required
- [ ] Performance targets met (sub-second for typical repos)

---

## Phase 2C: Spec Management Tooling

**Goal**: Create scripts and tools for managing the traceability graph, enabling easy refactoring without manual find-and-replace.

### Background

From PR #715 review:
> There's going to need to be a great set of scripts and tools for managing the graph. We need to refactor requirements, designs, and tasks as we iterate and learn. Giant find and replace is going to be too cumbersome and error prone and introduce too much friction. It's crap ergonomics.

### Tasks

| ID | Task | Complexity | Status | Linked Issue |
|----|------|------------|--------|--------------|
| SM-001 | Create `Rename-SpecId.ps1` (rename ID, update all refs) | L | PENDING | #722 |
| SM-002 | Create `Update-SpecReferences.ps1` (bulk ref updates) | M | PENDING | #722 |
| SM-003 | Create `Show-TraceabilityGraph.ps1` (text/Mermaid output) | M | PENDING | #722 |
| SM-004 | Create `Resolve-OrphanedSpecs.ps1` (interactive wizard) | M | PENDING | #722 |
| SM-005 | Add dry-run mode to all mutating operations | S | PENDING | #722 |
| SM-006 | Add validation before changes (prevent partial updates) | M | PENDING | #722 |
| SM-007 | Document spec management workflow | S | PENDING | #722 |

### Proposed Scripts

| Script | Purpose |
|--------|---------|
| `Rename-SpecId.ps1` | Rename spec ID, update all referencing files |
| `Update-SpecReferences.ps1` | Bulk update references across specs |
| `Show-TraceabilityGraph.ps1` | Visualize graph (text or Mermaid output) |
| `Resolve-OrphanedSpecs.ps1` | Interactive orphan resolution wizard |

### Acceptance Criteria

- [ ] Rename tool safely updates all references atomically
- [ ] All tools validate before making changes
- [ ] Dry-run mode available for all mutating operations
- [ ] Error handling prevents partial updates
- [ ] Workflow documented with examples

---

## Phase 3: Parallel Execution

**Goal**: Enable orchestrator to fan-out work to multiple agents.

### Background: Anthropic + Claude-flow Patterns

- **Sectioning**: Split task into independent subtasks
- **Voting**: Run same task multiple times, select best
- **Aggregation**: Merge results from parallel execution
- **Batch spawning**: 10-20x faster agent initialization

### Tasks

| ID | Task | Complexity | Status | Linked Issue |
|----|------|------------|--------|--------------|
| P-001 | Design parallel dispatch protocol | M | PENDING | #168 |
| P-002 | Update orchestrator with parallel capability documentation | L | PENDING | #168 |
| P-003 | Create result aggregation patterns | M | PENDING | #168 |
| P-004 | Implement voting mechanism documentation | M | PENDING | #171 |
| P-005 | Update impact analysis for parallel consultations | M | PENDING | #168 |
| P-006 | Add parallel execution metrics to session logs | S | PENDING | #168 |
| P-007 | Document parallel execution in AGENT-SYSTEM.md | S | PENDING | #168 |
| P-008 | Design swarm coordination modes | L | PENDING | #175 |
| P-009 | Implement mesh coordination pattern | L | PENDING | #175 |
| P-010 | Implement hierarchical coordination pattern | L | PENDING | #175 |

### Aggregation Strategies

| Strategy | Use Case | Behavior |
|----------|----------|----------|
| **merge** | Non-conflicting outputs | Combine all outputs |
| **vote** | Redundant execution | Select majority |
| **escalate** | Conflicts detected | Route to high-level-advisor |
| **mesh** | Peer coordination | Direct agent-to-agent |
| **hierarchical** | Complex orchestration | Lead agent coordinates |

### Acceptance Criteria

- [ ] Orchestrator documents parallel dispatch capability
- [ ] Aggregation patterns defined and documented
- [ ] Impact analysis notes parallel potential
- [ ] Session logs track parallel metrics
- [ ] 2.8-4.4x speed improvement demonstrated
- [ ] Coordination modes documented with examples

---

## Phase 4: Steering Scoping - PARTIAL

**Goal**: Inject only relevant steering content based on file context.

### Background: Kiro Pattern

Kiro uses glob-based inclusion to reduce token usage:

```yaml
api-patterns.md -> *.ts, src/api/*
testing-approach.md -> **/*.test.ts
```

### Current State

Steering directory created with 5 placeholder files:

- `csharp-patterns.md` (placeholder)
- `security-practices.md` (placeholder)
- `testing-approach.md` (placeholder)
- `agent-prompts.md` (placeholder)
- `documentation.md` (placeholder)

### Tasks

| ID | Task | Complexity | Status | Session | PR |
|----|------|------------|--------|---------|-----|
| ST-001 | Design steering file schema with glob patterns | M | COMPLETE | - | - |
| ST-002 | Create steering files for key domains | M | COMPLETE | - | #580, #593 |
| ST-003 | Document steering injection logic in orchestrator | L | PENDING | - | - |
| ST-004 | Add token usage tracking to session logs | S | PENDING | - | - |
| ST-005 | Measure baseline vs scoped steering token usage | S | PENDING | - | - |
| ST-006 | Update agent prompts to reference steering files | M | PENDING | - | - |
| ST-007 | Document steering system in AGENT-SYSTEM.md | S | COMPLETE | - | - |

### Steering File Structure

```text
.agents/steering/
├── README.md                 # Steering system overview [EXISTS]
├── powershell-patterns.md    # *.ps1, *.psm1 [EXISTS]
├── agent-prompts.md          # src/claude/*.md [EXISTS]
├── testing-approach.md       # **/*.test.*, **/*.spec.* [EXISTS]
├── security-practices.md     # **/Auth/**, *.env* [EXISTS]
└── documentation.md          # **/*.md (non-agent) [EXISTS]
```

### Acceptance Criteria

- [x] Steering files organized by domain
- [x] Glob patterns documented
- [ ] Token savings measured (target: 30%+)
- [ ] Agents reference steering guidance

---

## Phase 5: Evaluator-Optimizer Loop + Consensus

**Goal**: Formalize the generator-evaluator-regenerate pattern and multi-agent consensus.

### Background: Anthropic + SPARC Pattern

```text
Generator -> Evaluator -> (Accept or Regenerate with feedback)
```

SPARC (Specification, Pseudocode, Architecture, Refinement, Completion):

- Formalized development phases
- Quality gates between phases
- Iterative refinement loops

### Tasks

| ID | Task | Complexity | Status | Linked Issue |
|----|------|------------|--------|--------------|
| E-001 | Design evaluator-optimizer protocol | M | PENDING | #172 |
| E-002 | Update independent-thinker with evaluation rubric | M | PENDING | - |
| E-003 | Add regeneration capability to orchestrator | L | PENDING | - |
| E-004 | Define acceptance criteria for loop termination | S | PENDING | - |
| E-005 | Add evaluation metrics to session logs | S | PENDING | - |
| E-006 | Create evaluation history tracking | M | PENDING | - |
| E-007 | Document evaluator-optimizer in AGENT-SYSTEM.md | S | PENDING | - |
| E-008 | Design consensus mechanism protocol | M | PENDING | #171 |
| E-009 | Implement voting/decision protocols | L | PENDING | #171 |
| E-010 | Integrate SPARC phases with quality gates | L | PENDING | #172 |

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
- [ ] Consensus mechanism handles multi-agent disagreement
- [ ] SPARC quality gates integrated

---

## Phase 5A: Session Automation (claude-flow inspired)

**Goal**: Automate session lifecycle with hooks, checkpointing, and skill consolidation.

### Background: Claude-flow Automation

- **Lifecycle hooks**: Pre/post session automation
- **Session checkpointing**: Pause/resume with state persistence
- **Skill auto-consolidation**: Learn from retrospectives automatically

### Tasks

| ID | Task | Complexity | Status | Linked Issue |
|----|------|------------|--------|--------------|
| A-001 | Design lifecycle hooks architecture | M | PENDING | #170 |
| A-002 | Implement pre-session hook (context loading) | M | PENDING | #170 |
| A-003 | Implement post-session hook (cleanup, commit) | M | PENDING | #170 |
| A-004 | Design session checkpoint format | M | PENDING | #174 |
| A-005 | Implement pause/resume capability | L | PENDING | #174 |
| A-006 | Design skill extraction automation | M | PENDING | #173 |
| A-007 | Implement retrospective-to-skill pipeline | L | PENDING | #173 |
| A-008 | Integrate with SESSION-PROTOCOL.md | M | PENDING | #170 |

### Hook Integration with SESSION-PROTOCOL

```text
PRE-SESSION HOOK (automated Phase 1-2):
├── Activate Serena project
├── Read initial instructions
├── Load HANDOFF.md context
└── Create session log

POST-SESSION HOOK (automated Phase 7):
├── Update HANDOFF.md
├── Run markdownlint
├── Extract skills from session
└── Commit changes
```

### Acceptance Criteria

- [ ] Pre-session hook automates protocol Phase 1-2
- [ ] Post-session hook automates protocol Phase 7
- [ ] Sessions can be paused and resumed with context
- [ ] Skills automatically extracted from successful patterns
- [ ] Manual protocol compliance reduced by 80%

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
10. Skills auto-consolidated

### Tasks

| ID | Task | Complexity | Status | Linked Issue |
|----|------|------------|--------|--------------|
| I-001 | Define end-to-end test scenario | M | PENDING | - |
| I-002 | Execute spec workflow (requirements, design, tasks) | L | PENDING | - |
| I-003 | Validate traceability across all artifacts | M | PENDING | - |
| I-004 | Test parallel execution with real feature | M | PENDING | #168 |
| I-005 | Measure steering token efficiency | S | PENDING | - |
| I-006 | Test evaluator-optimizer on generated output | M | PENDING | - |
| I-007 | Test memory system performance | M | PENDING | #167 |
| I-008 | Test session automation hooks | M | PENDING | #170 |
| I-009 | Test stream processing workflow chains | M | PENDING | #177 |
| I-010 | Test health status computation | S | PENDING | #178 |
| I-011 | Validate MCP tool ecosystem integration | M | PENDING | #179 |
| I-012 | Conduct project retrospective | M | PENDING | - |
| I-013 | Update all documentation with learnings | M | PENDING | - |

### Acceptance Criteria

- [ ] End-to-end workflow completes
- [ ] All traceability checks pass
- [ ] Parallel execution documented
- [ ] Token savings achieved (30%+ target)
- [ ] Evaluator loop improves quality
- [ ] Memory system performs within targets
- [ ] Session automation reduces manual steps
- [ ] Retrospective captures patterns
- [ ] Stream processing enables chained workflows
- [ ] Health monitoring operational

---

## Phase 7: Workflow Orchestration UX (MoAI-inspired)

**Goal**: Provide numbered workflow commands and tiered agent hierarchy for improved developer experience.

### Background: MoAI-ADK Pattern

Inspired by [modu-ai/moai-adk](https://github.com/modu-ai/moai-adk):

- 27 specialized agents in 5-tier hierarchy
- Numbered workflow commands (/moai:0-project through /moai:4-ship)
- "Mr. Alfred" central orchestrator
- Auto-sync documentation

### Tasks

| ID | Task | Complexity | Status | Linked Issue |
|----|------|------------|--------|--------------|
| W-001 | Create workflow commands (/0-init through /9-sync) | M | PENDING | #739 |
| W-002 | Add tier metadata to agent frontmatter | S | PENDING | #739 |
| W-003 | Document 4-tier agent hierarchy | M | PENDING | #739 |
| W-004 | Integrate with Agent Orchestration MCP | L | PENDING | #221 |
| W-005 | Implement /2-impl --parallel variant | L | PENDING | #168 |
| W-006 | Implement /9-sync auto-documentation | M | PENDING | #739 |
| W-007 | Create PowerShell orchestration scripts | M | PENDING | #739 |

### Agent Tier Hierarchy

| Tier | Role | Agents |
|------|------|--------|
| Expert | Strategic depth | high-level-advisor, independent-thinker, architect, roadmap |
| Manager | Coordination | orchestrator, planner, critic |
| Builder | Execution | implementer, qa, devops, security |
| Integration | Support | analyst, explainer, task-generator, retrospective, memory, skillbook, context-retrieval |

### Acceptance Criteria

- [ ] Numbered commands guide workflow sequence
- [ ] Agent tiers documented with escalation paths
- [ ] /0-init integrates with Session State MCP
- [ ] /2-impl --parallel uses Agent Orchestration MCP
- [ ] /9-sync auto-generates session documentation
- [ ] Workflow discovery time reduced by 50%

### PRD Reference

- [prd-workflow-orchestration-enhancement.md](prd-workflow-orchestration-enhancement.md)

---

## Risk Register

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Claude Code sequential limits parallel | High | Medium | Design for logical parallelism, not runtime |
| EARS format too rigid | Medium | Medium | Allow escape hatch for edge cases |
| Traceability overhead slows development | Medium | High | Make validation fast, optional in WIP |
| Steering glob matching complexity | Low | Medium | Start simple, iterate |
| Evaluator loop infinite regression | Low | High | Hard cap at 3 iterations |
| Vector memory integration complexity | Medium | High | Start with Serena fallback |
| Session checkpointing state size | Medium | Medium | Compress, prune stale context |
| Skill auto-consolidation noise | Medium | Medium | Require atomicity threshold (70%+) |

---

## Dependencies

```text
Phase 0 (Foundation) ─────────────────────────────┐
    │                                             │
    ├──> Phase 1 (Spec Layer)                     │
    │        │                                    │
    │        ├──> Phase 2 (Traceability) ────────>│
    │        │        │                           │
    │        │        ├──> Phase 2B (Graph Perf) ─┤
    │        │        │        │                  │
    │        │        │        └──> Phase 2C ────>│
    │        │        │             (Spec Tools)  │
    │        │                                    │
    │        └──> Phase 4 (Steering) [PARTIAL] ──>│
    │                                             │
    ├──> Phase 2A (Memory) ───────────────────────┤
    │        │                                    │
    │        └──> Phase 3 (Parallel) ────────────>│
    │                                             │
    └──> Phase 5A (Automation) ──────────────────>│
                                                  │
         Phase 5 (Evaluator) <────────────────────┤
                                                  │
         Phase 7 (Workflow UX) <──────────────────┤
                                                  │
                     Phase 6 (Integration) <──────┘
```

---

## Success Criteria

Project is complete when:

- [ ] All phases completed with passing acceptance criteria
- [ ] End-to-end test scenario successful
- [ ] Documentation updated and reviewed
- [ ] Token usage reduced by 30%+ for focused tasks
- [ ] Traceability coverage at 100%
- [ ] Parallel execution demonstrates 2x+ speed improvement
- [ ] Memory search 10x+ faster than baseline
- [ ] Session automation reduces manual protocol steps by 80%
- [ ] Retrospective conducted with learnings persisted
- [ ] All Epic #183 issues addressed or explicitly deferred
- [ ] Workflow orchestration commands operational (#739)
- [ ] Agent tier hierarchy documented and enforced

---

## Session Log

| Session | Date | Phase | Tasks | Status | Log |
|---------|------|-------|-------|--------|-----|
| 1 | 2025-12-17 | 0 | F-001 to F-006 | COMPLETE | `.agents/sessions/2025-12-18-session-01-phase-0-foundation.md` |
| 44 | 2025-12-20 | N/A | PROJECT-PLAN merge | COMPLETE | Current session |
| 111+ | 2025-12-31 | 1 | S-001 to S-008 | COMPLETE | PRs #603, #604, #605, #690 |
| 112 | 2025-12-31 | 1 | Epic #183 cleanup | COMPLETE | `.agents/sessions/2025-12-31-session-112-project-plan-evaluation.md` |
| 113 | 2025-12-31 | 2 | T-001 to T-007 | COMPLETE | `.agents/sessions/2025-12-31-session-113-phase2-traceability.md` |
| 123 | 2026-01-01 | 2A | Phase 2A planning | COMPLETE | `.agents/sessions/2026-01-01-session-123-phase2-planning.md` |
| 124-125 | 2026-01-01 | 2A | ADR-037 review | COMPLETE | `.agents/sessions/2026-01-01-session-124-adr037-independent-review.md` |
| 126 | 2026-01-01 | 2A | M-003, M-008 | COMPLETE | `.agents/sessions/2026-01-01-session-126-m003-implementation.md` |
| 127+ | 2026-01-01 | 2A | M-004, M-005 | COMPLETE | PR #735 (ADR-038, ReflexionMemory) |

---

## Changelog

| Date | Version | Changes |
|------|---------|---------|
| 2025-12-17 | 1.0 | Initial project plan |
| 2025-12-20 | 2.0 | Merged Epic #183 (claude-flow enhancements). Added Phase 2A (Memory), Phase 5A (Automation). Updated Phase 0,1,4 status. Integrated issues #167-#181 into phases. Added dependencies and success criteria for claude-flow metrics. |
| 2025-12-31 | 2.1 | Marked Phase 1 (Spec Layer) COMPLETE. All tasks S-001 through S-008 delivered via PRs #603, #604, #605, #690. Reopened Epic #183 since child issues remain open. |
| 2025-12-31 | 2.2 | Marked Phase 2 (Traceability) COMPLETE. Tasks T-001 to T-007 delivered via PR #715. Updated acceptance criteria. |
| 2026-01-02 | 2.3 | Phase 2A Memory System IN PROGRESS. Tasks M-001 to M-005, M-008 COMPLETE in PR #735. MemoryRouter (ADR-037) and ReflexionMemory (ADR-038) implemented. M-006, M-007 (Neural Patterns) remain PENDING. Added Implementation Notes section with delivered artifacts. |

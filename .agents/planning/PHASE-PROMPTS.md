# AI Agents Enhancement - Phase Prompts

> **Usage**: Copy the relevant phase prompt to delegate work to orchestrator.
> **Repository**: rjmurillo/ai-agents
> **Master Plan**: `.agents/planning/enhancement-PROJECT-PLAN.md`

---

## Quick Reference - Phase Overview

| Phase | Name | Sessions | Key Deliverables |
|-------|------|----------|------------------|
| 0 | Foundation | 1-2 | Directory structure, governance docs |
| 1 | Spec Layer | 2-3 | EARS templates, spec-generator agent |
| 2 | Traceability | 2-3 | Validation scripts, pre-commit hooks |
| 3 | Parallel Execution | 2-3 | Fan-out documentation, aggregation patterns |
| 4 | Steering Scoping | 2-3 | Glob-based steering files, token tracking |
| 5 | Evaluator-Optimizer | 2-3 | Evaluation rubric, regeneration protocol |
| 6 | Integration Testing | 1-2 | End-to-end test, retrospective |

---

## Phase 0: Foundation

### Phase 0 - Full Prompt

```text
# AI Agents Enhancement - Phase 0: Foundation

@orchestrator Execute Phase 0 of the ai-agents enhancement project.

## Context

Read these files first:
1. `.agents/AGENT-SYSTEM.md` - Current agent system
2. `.agents/HANDOFF.md` - Previous session state
3. `.agents/planning/enhancement-PROJECT-PLAN.md` - Master plan

## Phase Goal

Establish the foundational directory structure and governance documents that all subsequent phases depend on.

## Background

The ai-agents system currently lacks:
- Structured spec hierarchy (Kiro pattern)
- Formal steering file organization
- Naming conventions for artifacts
- Consistency validation protocol

This phase creates the scaffolding for these capabilities.

## Tasks

### F-001: Create Spec Directories
Create `.agents/specs/` with subdirectories:
- `.agents/specs/requirements/` - EARS format requirements
- `.agents/specs/design/` - Design documents
- `.agents/specs/tasks/` - Task breakdowns

Each directory needs a `README.md` explaining its purpose and file format.

### F-002: Create Naming Conventions
Create `.agents/governance/naming-conventions.md` documenting:
- Spec file naming: `REQ-NNN-[name].md`, `DESIGN-NNN-[name].md`, `TASK-NNN-[name].md`
- Agent prompt naming: `[agent-name].md` (lowercase, hyphenated)
- Session log naming: `YYYY-MM-DD-session-NN.md`
- Artifact cross-reference format

### F-003: Create Consistency Protocol
Create `.agents/governance/consistency-protocol.md` documenting:
- Pre-critic validation checklist
- Cross-document consistency rules
- Orphan detection criteria
- Integration with existing critic agent

### F-004: Create Steering Directory
Create `.agents/steering/` with:
- `README.md` - Steering system overview
- Placeholder files for Phase 4 implementation

### F-005: Update AGENT-SYSTEM.md
Update `.agents/AGENT-SYSTEM.md` to document:
- New directory structure
- Spec layer workflow
- Steering file concept (placeholder for Phase 4)

### F-006: Initialize HANDOFF.md
Create or update `.agents/HANDOFF.md` with:
- Enhancement project context
- Phase 0 completion status
- Next phase preparation

## Acceptance Criteria

- [ ] All directories exist with README files
- [ ] Naming conventions documented with examples
- [ ] Consistency protocol aligns with existing critic workflow
- [ ] AGENT-SYSTEM.md reflects new architecture
- [ ] HANDOFF.md ready for Phase 1

## Constraints

- Do not modify existing agent prompts (that's Phase 1+)
- Do not create validation scripts yet (that's Phase 2)
- Focus on documentation and structure only

## Branch

Create branch: `feat/phase-0-foundation`

## Commit Convention

Use conventional commits:
- `docs(governance): add naming conventions`
- `docs(specs): create spec directory structure`
- `docs(system): update AGENT-SYSTEM.md with spec layer`

## Session Protocol

1. Create session log: `.agents/sessions/YYYY-MM-DD-session-NN.md`
2. Execute tasks F-001 through F-006 in order
3. Run retrospective agent before ending
4. Update HANDOFF.md with completion status
```

---

## Phase 1: Spec Layer

### Phase 1 - Full Prompt

```text
# AI Agents Enhancement - Phase 1: Spec Layer

@orchestrator Execute Phase 1 of the ai-agents enhancement project.

## Context

Read these files first:
1. `.agents/AGENT-SYSTEM.md` - Current agent system
2. `.agents/HANDOFF.md` - Previous session state (Phase 0 should be complete)
3. `.agents/planning/enhancement-PROJECT-PLAN.md` - Master plan
4. `.agents/governance/naming-conventions.md` - From Phase 0

## Phase Goal

Implement Kiro's 3-tier planning hierarchy with EARS requirements format.

## Background

### EARS Format (Easy Approach to Requirements Syntax)

EARS provides testable, unambiguous requirements:

```text
WHEN [precondition/trigger]
THE SYSTEM SHALL [action/behavior]
SO THAT [rationale/value]
```

**Types**:
- **Ubiquitous**: THE SYSTEM SHALL [action] (always true)
- **Event-Driven**: WHEN [event] THE SYSTEM SHALL [action]
- **State-Driven**: WHILE [state] THE SYSTEM SHALL [action]
- **Optional**: WHERE [feature enabled] THE SYSTEM SHALL [action]
- **Unwanted**: IF [condition] THEN THE SYSTEM SHALL NOT [action]

### 3-Tier Hierarchy

```text
requirements.md (EARS format)
    ↓ traced by
design.md (architecture decisions)
    ↓ traced by  
tasks.md (atomic work items)
```

## Tasks

### S-001: Create EARS Format Template
Create `.agents/governance/ears-format.md` documenting:
- EARS syntax rules with examples
- Requirement types (ubiquitous, event-driven, etc.)
- Testability criteria
- Anti-patterns to avoid

### S-002: Create spec-generator Agent
Create `src/claude/spec-generator.md` with:
- Agent identity: Spec Generation Specialist
- Workflow: vibe prompt → clarifying questions → requirements.md → design.md → tasks.md
- EARS validation checklist
- Output templates for each tier
- Memory protocol for spec context

**Agent Template Structure**:
```yaml
---
name: spec-generator
description: Transforms vibe-level feature descriptions into structured specifications using EARS requirements format and 3-tier hierarchy.
model: sonnet
argument-hint: Describe the feature or capability you want to specify
---
```

### S-003: Create Requirements YAML Schema
Define YAML front matter for requirements:
```yaml
---
type: requirement
id: REQ-NNN
status: draft | review | approved | implemented
priority: P0 | P1 | P2
category: functional | non-functional | constraint
related:
  - DESIGN-NNN
created: YYYY-MM-DD
updated: YYYY-MM-DD
---
```

### S-004: Create Design YAML Schema
Define YAML front matter for design documents:
```yaml
---
type: design
id: DESIGN-NNN
status: draft | review | approved | implemented
requirements:
  - REQ-NNN
  - REQ-NNN
decisions:
  - ADR-NNN
created: YYYY-MM-DD
updated: YYYY-MM-DD
---
```

### S-005: Create Tasks YAML Schema
Define YAML front matter for task documents:
```yaml
---
type: task
id: TASK-NNN
status: pending | in-progress | complete | blocked
complexity: XS | S | M | L | XL
designs:
  - DESIGN-NNN
assignee: implementer | qa | devops | architect
created: YYYY-MM-DD
updated: YYYY-MM-DD
---
```

### S-006: Update Orchestrator with Spec Routing
Update `src/claude/orchestrator.md` to include:
- Spec workflow detection (vibe → spec-generator)
- Routing heuristics for spec requests
- Integration with existing ideation workflow

### S-007: Create Sample Specs (Dogfood)
Create sample specs for an existing feature to validate the workflow:
- `.agents/specs/requirements/REQ-001-pr-comment-handling.md`
- `.agents/specs/design/DESIGN-001-pr-comment-handling.md`
- `.agents/specs/tasks/TASK-001-pr-comment-handling.md`

### S-008: Document Spec Workflow
Update `.agents/AGENT-SYSTEM.md` with:
- Spec layer workflow diagram
- spec-generator agent in catalog
- Routing from ideation to spec workflow

## Acceptance Criteria

- [ ] spec-generator agent produces valid EARS requirements
- [ ] All spec files have YAML front matter
- [ ] Orchestrator routes "create spec" requests correctly
- [ ] Sample specs demonstrate complete workflow
- [ ] AGENT-SYSTEM.md updated with spec workflow

## Constraints

- Maintain backward compatibility with existing agents
- Do not modify critic agent yet (that's Phase 2)
- Focus on spec creation, not validation

## Branch

Continue on: `feat/phase-1-spec-layer` (create from main)

## Commit Convention

- `feat(agents): add spec-generator agent`
- `docs(governance): add EARS format guide`
- `docs(specs): add sample PR comment specs`
```

---

## Phase 2: Traceability

### Phase 2 - Full Prompt

```text
# AI Agents Enhancement - Phase 2: Traceability

@orchestrator Execute Phase 2 of the ai-agents enhancement project.

## Context

Read these files first:
1. `.agents/AGENT-SYSTEM.md` - Current agent system
2. `.agents/HANDOFF.md` - Previous session state (Phase 1 should be complete)
3. `.agents/planning/enhancement-PROJECT-PLAN.md` - Master plan
4. `.agents/governance/consistency-protocol.md` - From Phase 0

## Phase Goal

Ensure all artifacts cross-reference correctly with automated validation.

## Background

### Traceability Rules

1. Every TASK must link to at least one DESIGN
2. Every DESIGN must link to at least one REQUIREMENT
3. No orphaned requirements (REQ without DESIGN)
4. No orphaned designs (DESIGN without TASK)
5. Status consistency (completed TASK implies completed chain)

### Validation Flow

```text
Pre-commit hook
    ↓
Validate-Traceability.ps1
    ↓
Parse YAML front matter
    ↓
Build reference graph
    ↓
Check rules 1-5
    ↓
Report violations or pass
```

## Tasks

### T-001: Design Traceability Graph Schema
Document the traceability graph structure:
- Node types: REQ, DESIGN, TASK
- Edge types: traces_to, implements, depends_on
- Status propagation rules
- Orphan detection algorithm

Save to: `.agents/governance/traceability-schema.md`

### T-002: Create Validation Script
Create `scripts/Validate-Traceability.ps1`:

```powershell
# Validate-Traceability.ps1
# Validates cross-references between specs

param(
    [string]$SpecsPath = ".agents/specs",
    [switch]$Strict  # Fail on warnings
)

# Parse YAML front matter from all spec files
# Build adjacency graph
# Check traceability rules
# Report violations

# Exit codes:
# 0 = Pass
# 1 = Errors found
# 2 = Warnings only (pass unless -Strict)
```

### T-003: Create Pre-Commit Hook
Create `.githooks/validate-traceability`:
- Run Validate-Traceability.ps1 on staged .md files in .agents/specs/
- Block commit if validation fails
- Provide actionable error messages

### T-004: Update Critic with Traceability
Update `src/claude/critic.md` to include:
- Traceability validation checklist
- Orphan detection in review
- Cross-reference verification before approval

Add to Review Checklist:
```markdown
### Traceability Validation
- [ ] All TASKs link to at least one DESIGN
- [ ] All DESIGNs link to at least one REQ
- [ ] No orphaned requirements
- [ ] No orphaned designs
- [ ] Status chain consistent
```

### T-005: Create Orphan Detection Report
Define report format for orphan detection:

```markdown
# Traceability Report

**Generated**: YYYY-MM-DD HH:MM:SS
**Spec Path**: .agents/specs/

## Summary
| Type | Total | Linked | Orphaned |
|------|-------|--------|----------|
| REQ | N | N | N |
| DESIGN | N | N | N |
| TASK | N | N | N |

## Orphaned Artifacts

### Orphaned Requirements
- REQ-NNN: [Title] - No DESIGN references this

### Orphaned Designs
- DESIGN-NNN: [Title] - No TASK references this

## Broken References
- TASK-NNN references DESIGN-999 which does not exist
```

### T-006: Add Traceability Metrics to Retrospective
Update `src/claude/retrospective.md` to track:
- Traceability coverage percentage
- Orphan count trend
- Reference completeness

### T-007: Document Traceability Protocol
Update `.agents/governance/consistency-protocol.md` with:
- Full traceability rules
- Validation script usage
- Pre-commit hook setup
- Remediation steps for violations

## Acceptance Criteria

- [ ] Validation script catches orphaned artifacts
- [ ] Pre-commit hook blocks commits with broken refs
- [ ] Critic validates traceability before approving
- [ ] Retrospective reports traceability coverage %
- [ ] Documentation complete and actionable

## Constraints

- PowerShell script must work cross-platform (PowerShell Core)
- Hook must be fast (<5 seconds for typical spec set)
- Validation must handle missing files gracefully

## Branch

Continue on: `feat/phase-2-traceability`

## Commit Convention

- `feat(scripts): add traceability validation script`
- `feat(hooks): add pre-commit traceability check`
- `feat(agents): update critic with traceability validation`
```

---

## Phase 3: Parallel Execution

### Phase 3 - Full Prompt

```text
# AI Agents Enhancement - Phase 3: Parallel Execution

@orchestrator Execute Phase 3 of the ai-agents enhancement project.

## Context

Read these files first:
1. `.agents/AGENT-SYSTEM.md` - Current agent system
2. `.agents/HANDOFF.md` - Previous session state
3. `.agents/planning/enhancement-PROJECT-PLAN.md` - Master plan

## Phase Goal

Enable orchestrator to document and reason about parallel work distribution.

## Background

### Anthropic Parallel Patterns

**Sectioning**: Split task into independent subtasks that can execute without coordination.

```text
Task: "Review all agent prompts"
    ↓ Section
[analyst.md] [architect.md] [critic.md] ... (independent)
    ↓ Aggregate
Combined review report
```

**Voting**: Run same task multiple times with different approaches, select best.

```text
Task: "Design API structure"
    ↓ Vote (3 attempts)
[Design A] [Design B] [Design C]
    ↓ Evaluate
Select highest-scoring design
```

### Current Limitation

Claude Code executes sequentially. This phase documents LOGICAL parallelism for:
- Future parallel runtimes
- Human parallel execution
- Clear dependency identification

## Tasks

### P-001: Design Parallel Dispatch Protocol
Create `.agents/governance/parallel-dispatch.md` documenting:
- Independence criteria (when tasks can run in parallel)
- Dependency detection heuristics
- Parallel task annotation format
- Sequential fallback behavior

### P-002: Update Orchestrator with Parallel Docs
Update `src/claude/orchestrator.md` to include:
- Parallel execution section in workflow documentation
- Independence assessment checklist
- Parallel annotation in task delegation

Add section:
```markdown
## Parallel Execution (Documentation)

When delegating tasks, assess parallel potential:

### Independence Criteria
Tasks are independent when:
- [ ] No shared file modifications
- [ ] No data dependencies
- [ ] No sequence requirements
- [ ] Results don't need coordination

### Parallel Annotation
When tasks could run in parallel, document:
\`\`\`markdown
## Parallel Block: [Name]
**Type**: Sectioning | Voting
**Tasks**:
- [ ] Task A (to: agent-a)
- [ ] Task B (to: agent-b)
**Aggregation**: merge | vote | escalate
\`\`\`
```

### P-003: Create Aggregation Patterns
Document result aggregation strategies in `.agents/governance/aggregation-patterns.md`:

| Strategy | Use Case | Behavior |
|----------|----------|----------|
| **merge** | Non-conflicting outputs | Combine all outputs |
| **vote** | Redundant execution | Select majority |
| **escalate** | Conflicts detected | Route to high-level-advisor |
| **first-wins** | Race condition | Use first complete result |

Include conflict detection heuristics.

### P-004: Document Voting Mechanism
Add voting protocol to aggregation patterns:
- Minimum vote count (default: 3)
- Tie-breaker rules (escalate to high-level-advisor)
- Confidence threshold for auto-selection
- Evidence requirements for votes

### P-005: Update Impact Analysis for Parallel
Update planner and specialist agents to note parallel potential:
- Add "Parallel Potential" field to impact analysis
- Document which consultations could run in parallel
- Note sequential dependencies explicitly

### P-006: Add Parallel Metrics to Session Logs
Update session log template to track:
- Parallel blocks identified
- Actual execution (sequential vs parallel annotation)
- Aggregation strategy used
- Time savings potential

### P-007: Document in AGENT-SYSTEM.md
Update `.agents/AGENT-SYSTEM.md` with:
- Parallel execution patterns section
- Aggregation strategy reference
- Future parallel runtime considerations

## Acceptance Criteria

- [ ] Orchestrator documents parallel dispatch capability
- [ ] Aggregation patterns defined and documented
- [ ] Impact analysis notes parallel potential
- [ ] Session logs track parallel metrics
- [ ] AGENT-SYSTEM.md updated

## Constraints

- This phase documents LOGICAL parallelism only
- Do not implement actual parallel execution (runtime limitation)
- Focus on identifying independence and aggregation strategies
- Maintain compatibility with sequential execution

## Branch

Continue on: `feat/phase-3-parallel`

## Commit Convention

- `docs(governance): add parallel dispatch protocol`
- `docs(agents): update orchestrator with parallel documentation`
- `docs(governance): add aggregation patterns`
```

---

## Phase 4: Steering Scoping

### Phase 4 - Full Prompt

```text
# AI Agents Enhancement - Phase 4: Steering Scoping

@orchestrator Execute Phase 4 of the ai-agents enhancement project.

## Context

Read these files first:
1. `.agents/AGENT-SYSTEM.md` - Current agent system
2. `.agents/HANDOFF.md` - Previous session state
3. `.agents/planning/enhancement-PROJECT-PLAN.md` - Master plan
4. `.agents/steering/README.md` - From Phase 0

## Phase Goal

Inject only relevant steering content based on file context to reduce token usage.

## Background

### Kiro Steering Pattern

Kiro uses glob-based inclusion to reduce context:

```yaml
# steering-manifest.yaml
steering:
  - file: csharp-patterns.md
    include:
      - "**/*.cs"
      - "**/*.csproj"
  - file: testing-approach.md
    include:
      - "**/*.test.*"
      - "**/*.spec.*"
```

### Token Efficiency Goal

Current: All guidance loaded regardless of task
Target: 30-40% reduction via context-relevant guidance only

## Tasks

### ST-001: Design Steering File Schema
Create `.agents/steering/steering-schema.md` documenting:
- Steering file format (markdown with YAML front matter)
- Glob pattern syntax
- Priority and override rules
- Fallback behavior

YAML Schema:
```yaml
---
steering: true
applies_to:
  - "**/*.cs"
  - "!**/*.Test.cs"  # Exclude pattern
priority: 10  # Higher = more specific
---
```

### ST-002: Create Domain Steering Files
Create steering files for key domains:

**`.agents/steering/csharp-patterns.md`**
- Applies to: `**/*.cs`
- Content: SOLID principles, performance patterns, naming conventions

**`.agents/steering/agent-prompts.md`**
- Applies to: `src/claude/**/*.md`
- Content: Prompt engineering best practices, agent structure

**`.agents/steering/testing-approach.md`**
- Applies to: `**/*.test.*`, `**/*.spec.*`
- Content: Testing strategy, coverage requirements

**`.agents/steering/security-practices.md`**
- Applies to: `**/Auth/**`, `*.env*`
- Content: Security checklist, sensitive data handling

**`.agents/steering/documentation.md`**
- Applies to: `**/*.md` (excluding agent prompts)
- Content: Documentation standards, markdown rules

### ST-003: Document Steering Injection Logic
Update orchestrator documentation to describe:
- When to check steering manifest
- How to match glob patterns to current task
- Injection point in agent prompts
- Token budget considerations

Add to `src/claude/orchestrator.md`:
```markdown
## Steering Context Injection

Before delegating to an agent, check steering applicability:

1. Identify files that will be touched by the task
2. Match files against steering glob patterns
3. Load applicable steering files by priority (highest first)
4. Inject steering context into agent prompt
5. Note steering files used in session log
```

### ST-004: Add Token Usage Tracking
Update session log template to track:
- Steering files loaded
- Estimated token count per steering file
- Total steering tokens vs baseline
- Percentage reduction achieved

### ST-005: Measure Baseline vs Scoped
Create measurement methodology:
- Baseline: All steering loaded (estimate tokens)
- Scoped: Only relevant steering (estimate tokens)
- Calculate reduction percentage
- Document in `.agents/steering/token-analysis.md`

### ST-006: Update Agent Prompts with Steering Refs
Update key agents to reference steering system:
- implementer.md: Reference csharp-patterns.md when working on .cs
- qa.md: Reference testing-approach.md
- security.md: Reference security-practices.md

Add section to agents:
```markdown
## Steering Context

This agent may receive additional context from steering files:
- See `.agents/steering/` for available steering
- Orchestrator injects relevant steering based on task scope
- Steering provides domain-specific guidance
```

### ST-007: Document in AGENT-SYSTEM.md
Update `.agents/AGENT-SYSTEM.md` with:
- Steering system overview
- Glob pattern reference
- Token efficiency goals and tracking

## Acceptance Criteria

- [ ] Steering files organized by domain
- [ ] Glob patterns documented and tested
- [ ] Token savings estimated (target: 30%+)
- [ ] Agents reference steering guidance
- [ ] AGENT-SYSTEM.md updated

## Constraints

- Steering is documentation/guidance only (not code injection)
- Must work without tooling changes (manual injection for now)
- Future: Could be automated in agent wrapper

## Branch

Continue on: `feat/phase-4-steering`

## Commit Convention

- `docs(steering): add steering file schema`
- `docs(steering): add csharp-patterns steering`
- `docs(agents): update agents with steering references`
```

---

## Phase 5: Evaluator-Optimizer

### Phase 5 - Full Prompt

```text
# AI Agents Enhancement - Phase 5: Evaluator-Optimizer

@orchestrator Execute Phase 5 of the ai-agents enhancement project.

## Context

Read these files first:
1. `.agents/AGENT-SYSTEM.md` - Current agent system
2. `.agents/HANDOFF.md` - Previous session state
3. `.agents/planning/enhancement-PROJECT-PLAN.md` - Master plan

## Phase Goal

Formalize the generator-evaluator-regenerate pattern for quality improvement.

## Background

### Anthropic Evaluator-Optimizer Pattern

```text
Generator → Evaluator → (Accept or Regenerate with feedback)
```

**Flow**:
1. Generator produces output
2. Evaluator scores against rubric
3. If score >= threshold: Accept
4. If score < threshold AND iterations < max: Regenerate with feedback
5. If iterations >= max: Escalate to user

### Current State

The independent-thinker agent provides critique but:
- No formal scoring rubric
- No regeneration loop
- No iteration tracking

## Tasks

### E-001: Design Evaluator-Optimizer Protocol
Create `.agents/governance/evaluator-optimizer.md` documenting:
- Evaluation trigger conditions
- Scoring rubric structure
- Regeneration feedback format
- Iteration limits and escalation

### E-002: Create Evaluation Rubric
Define rubric in `.agents/governance/evaluation-rubric.md`:

| Criterion | Weight | 1 (Poor) | 2 (Fair) | 3 (Good) | 4 (Excellent) |
|-----------|--------|----------|----------|----------|---------------|
| Completeness | 25% | Major gaps | Some gaps | Minor gaps | All covered |
| Correctness | 25% | Errors | Some errors | Minor issues | Error-free |
| Clarity | 25% | Confusing | Some ambiguity | Clear | Crystal clear |
| Actionability | 25% | Vague | Somewhat actionable | Actionable | Immediately executable |

**Scoring**:
- Score = Weighted sum / 4 * 100
- Threshold: 70% for acceptance

### E-003: Update Independent-Thinker with Rubric
Update `src/claude/independent-thinker.md` to include:
- Structured evaluation output format
- Rubric application protocol
- Score calculation
- Regeneration feedback format

Add evaluation output template:
```markdown
## Evaluation Report

### Scores
| Criterion | Score (1-4) | Evidence |
|-----------|-------------|----------|
| Completeness | N | [Why this score] |
| Correctness | N | [Why this score] |
| Clarity | N | [Why this score] |
| Actionability | N | [Why this score] |

### Overall Score: NN%

### Verdict: ACCEPT | REGENERATE

### Feedback for Regeneration (if applicable)
1. [Specific issue to address]
2. [Specific improvement needed]
```

### E-004: Add Regeneration to Orchestrator
Update `src/claude/orchestrator.md` to document:
- When to trigger evaluation
- Regeneration loop management
- Iteration tracking
- Escalation conditions

Add section:
```markdown
## Evaluator-Optimizer Loop

For quality-critical outputs, apply evaluation loop:

1. **Generate**: Route to generator agent
2. **Evaluate**: Route output to independent-thinker with rubric
3. **Decision**:
   - Score >= 70%: Accept and continue
   - Score < 70% AND iteration < 3: Regenerate with feedback
   - Iteration >= 3: Escalate to user

### Iteration Tracking
Maintain iteration count in session log:
\`\`\`markdown
## Evaluation Loop: [Output Name]
- Iteration 1: Score 45% - Regenerating
- Iteration 2: Score 62% - Regenerating  
- Iteration 3: Score 78% - Accepted
\`\`\`
```

### E-005: Add Evaluation Metrics to Session Logs
Update session log template to track:
- Evaluation loops triggered
- Iteration counts
- Score progression
- Acceptance rate

### E-006: Create Evaluation History
Define format for tracking evaluation history:
- Per-output evaluation chain
- Score trends over time
- Common regeneration feedback patterns
- Skill extraction from evaluations

Save format in `.agents/governance/evaluation-history.md`

### E-007: Document in AGENT-SYSTEM.md
Update `.agents/AGENT-SYSTEM.md` with:
- Evaluator-optimizer workflow
- independent-thinker evaluation role
- Quality threshold configuration

## Acceptance Criteria

- [ ] Evaluation rubric defined with weights
- [ ] independent-thinker outputs structured scores
- [ ] Orchestrator documents regeneration capability
- [ ] Session logs include evaluation metrics
- [ ] AGENT-SYSTEM.md updated

## Constraints

- Maximum 3 iterations before escalation (hard cap)
- Evaluation adds latency; use for quality-critical outputs only
- Rubric weights can be adjusted per task type

## Branch

Continue on: `feat/phase-5-evaluator`

## Commit Convention

- `docs(governance): add evaluator-optimizer protocol`
- `docs(governance): add evaluation rubric`
- `feat(agents): update independent-thinker with evaluation output`
```

---

## Phase 6: Integration Testing

### Phase 6 - Full Prompt

```text
# AI Agents Enhancement - Phase 6: Integration Testing

@orchestrator Execute Phase 6 of the ai-agents enhancement project.

## Context

Read these files first:
1. `.agents/AGENT-SYSTEM.md` - Current agent system
2. `.agents/HANDOFF.md` - Previous session state (all phases should be complete)
3. `.agents/planning/enhancement-PROJECT-PLAN.md` - Master plan

## Phase Goal

Validate all phases work together through an end-to-end test scenario.

## Background

All enhancement phases are complete:
- Phase 0: Foundation (directories, governance)
- Phase 1: Spec Layer (EARS, spec-generator)
- Phase 2: Traceability (validation, hooks)
- Phase 3: Parallel Execution (documentation)
- Phase 4: Steering Scoping (glob-based injection)
- Phase 5: Evaluator-Optimizer (rubric, loop)

This phase validates the integrated system works end-to-end.

## Test Scenario: New Agent Creation

Use "pr-review-digest" agent as the integration test case.

**Scenario**: Create a new agent that generates daily PR review digests.

**Expected Flow**:
1. User provides vibe prompt: "I want an agent that summarizes PR review activity"
2. spec-generator creates requirements (EARS format)
3. spec-generator creates design
4. task-generator creates atomic tasks
5. Traceability validation passes (all refs valid)
6. Orchestrator notes parallel potential in impact analysis
7. Steering files applied (agent-prompts.md)
8. Evaluator-optimizer refines the agent prompt
9. Implementation with full test coverage
10. Retrospective extracts learnings

## Tasks

### I-001: Define End-to-End Test Scenario
Document test scenario in `.agents/testing/integration-test-scenario.md`:
- Input: Vibe prompt for pr-review-digest
- Expected outputs at each stage
- Validation criteria per stage
- Success/failure definitions

### I-002: Execute Spec Workflow
Execute the spec workflow for pr-review-digest:
1. Invoke spec-generator with vibe prompt
2. Validate EARS requirements generated
3. Validate design document generated
4. Validate tasks generated
5. Save all to `.agents/specs/`

### I-003: Validate Traceability
Run traceability validation:
1. Execute `scripts/Validate-Traceability.ps1`
2. Verify all refs valid
3. Verify no orphans
4. Document any issues found

### I-004: Test Parallel Execution Documentation
Verify parallel potential noted:
1. Check impact analysis for parallel blocks
2. Verify aggregation strategy documented
3. Note which tasks could run in parallel

### I-005: Measure Steering Token Efficiency
Measure token savings:
1. Identify applicable steering files
2. Calculate baseline (all steering)
3. Calculate scoped (only applicable)
4. Document reduction percentage

### I-006: Test Evaluator-Optimizer
Run evaluation loop on generated agent prompt:
1. Generate initial agent prompt
2. Evaluate against rubric
3. Regenerate if score < 70%
4. Track iterations
5. Document final score

### I-007: Conduct Project Retrospective
Run comprehensive retrospective:
1. Invoke retrospective agent with full project context
2. Extract learnings from all phases
3. Identify skill updates
4. Document patterns for future projects

### I-008: Finalize Documentation
Complete all documentation:
1. Update AGENT-SYSTEM.md with all enhancements
2. Create enhancement summary document
3. Update HANDOFF.md with project completion
4. Archive project plan

## Acceptance Criteria

- [ ] End-to-end workflow completes successfully
- [ ] All traceability checks pass
- [ ] Parallel execution documented in test
- [ ] Token savings achieved (30%+ target)
- [ ] Evaluator loop improves quality (score increased)
- [ ] Retrospective captures actionable patterns
- [ ] All documentation finalized

## Success Metrics

| Metric | Target | Actual |
|--------|--------|--------|
| Traceability coverage | 100% | [TBD] |
| Token reduction | 30%+ | [TBD] |
| Evaluator improvement | +10% score | [TBD] |
| Test scenario complete | Yes | [TBD] |

## Branch

Continue on: `feat/phase-6-integration`

## Final Merge

After Phase 6 completion:
1. Create PR from `feat/phase-6-integration` to `main`
2. Include all phase changes
3. Run final validation
4. Merge with squash commit

## Commit Convention

- `test(integration): add end-to-end test scenario`
- `docs(project): finalize enhancement documentation`
- `feat(agents): complete ai-agents enhancement project`
```

---

## Quick Task Prompts

For resuming specific tasks within a phase:

### Resume from Specific Task

```text
@orchestrator Resume Phase [N] of ai-agents enhancement.

Read `.agents/HANDOFF.md` for previous session state.
Continue from task [Task-ID] in `.agents/planning/enhancement-PROJECT-PLAN.md`.

Task context:
- Task ID: [ID]
- Description: [Brief description]
- Dependencies: [List or None]
- Acceptance criteria: [List]

Execute this task following the standard session protocol.
```

### Handle Blocker

```text
@orchestrator A blocker has been identified in ai-agents enhancement.

## Blocker Details
- Phase: [N]
- Task: [Task-ID]
- Blocker: [Description of what's blocking]
- Impact: [What can't proceed]

## Request
1. Analyze the blocker
2. Identify resolution options
3. If resolvable: Proceed with resolution
4. If external dependency: Document in HANDOFF.md and identify alternative work
```

### Skip to Next Phase

```text
@orchestrator Mark Phase [N] complete and proceed to Phase [N+1].

## Confirmation
- All Phase [N] tasks complete: [Yes/No]
- All acceptance criteria met: [Yes/No]
- Documentation updated: [Yes/No]

If any answer is No, list what remains and complete it first.
If all Yes, update PROJECT-PLAN.md and proceed to Phase [N+1].
```

---

## Prompt Selection Guide

| Situation | Use This Prompt |
|-----------|-----------------|
| Starting a new session | SESSION-START-PROMPT.md |
| Starting a new phase | Phase N Full Prompt (above) |
| Continuing mid-phase | Resume from Specific Task |
| Ending any session | SESSION-END-PROMPT.md |
| Blocked on task | Handle Blocker |
| Phase complete | Skip to Next Phase |

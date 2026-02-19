# Multi-Agent Workflow Skills

Category: Agent Coordination and Workflow Patterns
Source: `.agents/skills/multi-agent-workflow.md`
Migrated: 2025-12-13

## High-Impact Skills (90%+ Atomicity)

### Skill-Workflow-001: Full Pipeline for Large Changes (90%)

- **Statement**: Use full agent pipeline for changes touching 10+ files
- **Pipeline**: analyst -> architect -> planner -> critic -> implementer -> qa -> retrospective
- **Evidence**: 2025-12-13 - 59-file change with zero rollbacks needed

### Skill-Workflow-003: Pre-Implementation Validation (92%)

- **Statement**: Always run critic validation on plans before implementation begins
- **Evidence**: Critic review caught 3 minor issues before implementation
- **Criteria**: Completeness, Feasibility, Scope, Timeline, Risks

### Skill-Workflow-004: Atomic Commit Strategy (90%)

- **Statement**: Create atomic commits per logical unit for complex changes
- **Sequence**: Config commit, then each directory batch separately
- **Impact**: Enables selective rollback without reverting unrelated changes

### Skill-Workflow-006: Batch Verification Pattern (90%)

- **Statement**: Verify each batch of changes before proceeding to the next
- **Pattern**: `npx markdownlint-cli2 "directory/**/*.md"` after each batch

### Skill-Workflow-008: Configuration-First Approach (90%)

- **Statement**: Create configuration and documentation before implementation
- **Order**: Tool config -> Requirements docs -> Verify -> Implement

### Skill-Workflow-009: Known Exception Documentation (92%)

- **Statement**: Document known exceptions/false-positives explicitly with file locations
- **Evidence**: 3 false positives documented in config comments and QA report

## Medium-Impact Skills (85-90% Atomicity)

### Skill-Workflow-002: Artifact Chain Documentation (88%)

- **Statement**: Each agent produces artifacts that become inputs for the next agent
- **Chain**: analysis/ -> architecture/ -> planning/ -> critique/ -> commits -> qa/ -> retrospective/ -> skills/

### Skill-Workflow-005: Retrospective Extraction Timing (88%)

- **Statement**: Run retrospective immediately after QA completes while context is fresh
- **Focus**: Success strategies, Problems, Near-failures, Reusable patterns

### Skill-Workflow-007: Agent-Appropriate Scope Selection (85%)

- **Statement**: Match agent to task scope
- **Selection**:
  - 1-2 files, clear fix: implementer -> qa
  - 3-10 files, defined change: planner -> implementer -> qa
  - 10+ files or new standards: full pipeline
  - Strategic decision: independent-thinker -> high-level-advisor

### Skill-Workflow-010: Parallel Platform Synchronization (88%)

- **Statement**: Apply identical changes to parallel platform implementations together
- **Pattern**: Fix Claude (reference) -> VS Code -> Copilot CLI -> Verify all -> Commit separately

## Anti-Patterns

### Anti-Workflow-001: Skipping Critic Validation (90%)

- Never skip critic review for changes affecting more than 5 files
- **Prevention**: Critic review is required gate for systemic changes

### Anti-Workflow-002: Monolithic Commits (85%)

- Avoid single commits containing all changes across multiple directories
- **Prevention**: Commit atomically by logical unit

### Anti-Workflow-003: Delayed Retrospective (85%)

- Avoid running retrospective days after completion when context is lost
- **Prevention**: Schedule retrospective immediately after QA verification

## Metrics

- Pipeline Stages Used: 7
- Artifacts Generated: 7
- Atomic Commits: 5
- Rollbacks Required: 0
- Known Exceptions: 3

## Related

- [skills-agent-workflow-index](skills-agent-workflow-index.md)
- [skills-agent-workflow-phase3](skills-agent-workflow-index.md)
- [skills-agent-workflows](skills-agent-workflows.md)
- [skills-analysis-index](skills-analysis-index.md)
- [skills-analysis](skills-analysis-index.md)

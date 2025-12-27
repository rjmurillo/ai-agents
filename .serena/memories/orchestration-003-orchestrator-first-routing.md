# Skill-Orchestration-003: Orchestrator-First Routing

**Statement**: For complex multi-step tasks, invoke orchestrator agent first to route to specialists

**Context**: When task requires multiple agent types or workflow unclear

**Trigger**: Task description includes multiple concerns (analysis, design, implementation)

**Evidence**: Session 04 - Orchestrator correctly routed RCA to analyst → architect workflow

**Atomicity**: 92%

**Tag**: helpful

**Impact**: 8/10

**Created**: 2025-12-24

**Validated**: 1

**Category**: Orchestration

## Decision Tree

### Invoke Orchestrator When

- Task scope unclear (need analysis first)
- Multiple disciplines required (analysis + design + implementation)
- Workflow not obvious (which agent sequence?)
- Strategic decision with execution (advisor + implementer)
- Cross-cutting concern (security + implementation)

### Invoke Specialist Directly When

- Clear single-discipline task (just implementation)
- Established pattern (bug fix → implementer → qa)
- Simple scope (1-2 files, known fix)
- Continuation of prior work (same agent context)

## Examples

### Orchestrator-First (Correct)

```python
# Complex: RCA needed before fix
Task(subagent_type="orchestrator", 
     prompt="Investigate and fix aggregation failures in #357")

# Orchestrator routes: analyst → architect → implementer
```

### Direct Agent (Correct)

```python
# Simple: Known fix pattern
Task(subagent_type="implementer", 
     prompt="Add retry logic per spec in issue #338")

# Then: qa agent for verification
```

## Pattern Recognition

| Task Description | Agent | Reason |
|------------------|-------|--------|
| "Investigate and fix..." | orchestrator | Analysis + implementation |
| "Design solution for..." | orchestrator | Design + validation |
| "Implement feature X per plan.md" | implementer | Plan exists, direct work |
| "Why does X fail?" | analyst | Pure analysis |
| "Review design decisions" | architect | Pure review |
| "Fix bug in file.ts" | implementer | Known scope |

## Session 04 Example

**User Request**: "Fix aggregation failures in #357"

**Anti-pattern (Skip Orchestrator)**:
```python
Task(subagent_type="implementer", prompt="Fix #357")
# Problem: Don't know root cause yet
# Result: Wrong fix, wasted work
```

**Correct Pattern (Orchestrator First)**:
```python
Task(subagent_type="orchestrator", prompt="Fix #357")
# Orchestrator assesses: Need RCA first
# Routes to: analyst → findings → architect → plan → implementer
```

## Benefits

- Orchestrator performs triage (which agents needed?)
- Prevents premature implementation (analysis first)
- Ensures proper workflow sequence
- Coordinates handoffs between specialists

## When NOT to Use Orchestrator

- Trivial tasks (no delegation needed)
- Single-agent context clear (just ask qa agent)
- Continuation work (agent already active)
- Simple questions (no workflow needed)

## Success Criteria

- Complex tasks routed through proper workflow
- Analysis before implementation (when needed)
- Design validation before coding (when needed)
- Specialist agents get appropriate tasks

## Related Skills

- agent-workflow-pipeline: Full pipeline for large changes (10+ files)
- orchestration-handoff-coordination: Handoff aggregation pattern
- orchestration-parallel-execution: Parallel task dispatch
- skill-analysis-002-rca-before-implementation: Analysis precedes work

## Anti-Pattern

**DON'T** skip directly to implementation for complex tasks:
```python
# WRONG - no analysis
Task(subagent_type="implementer", prompt="Fix complex system issue")
```

**DO** route through orchestrator:
```python
# CORRECT - orchestrator triages
Task(subagent_type="orchestrator", prompt="Fix complex system issue")
# Orchestrator decides: analyst → architect → implementer
```

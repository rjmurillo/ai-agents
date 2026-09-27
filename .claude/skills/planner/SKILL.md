---
name: planner
description: Script-guided plan-and-execute workflow run one numbered step at a time. planner.py drafts a plan through forced reflection pauses, then runs a technical-writer and quality-reviewer review of the plan file; executor.py delegates each milestone of an approved plan file to specialized agents and, on resume, reconciles the file against completed work. Use when you say "run the planner workflow", "review the plan file at plans/X.md", "execute the plan at plans/X.md", "pick up where the plan left off", or "resume execution". Do NOT use to decompose a spec into milestones and tasks in the lifecycle chain (use plan), or to log progress on a plan artifact (use execution-plans).
license: MIT
metadata:
  routing:
    role: front-door
    invoker: autoplan
    trigger: autoplan routes execution, review, or resume of a planner-written plan file to planner
    user-facing: true
version: 1.0.0
---

# Planner Skill

## Purpose

Two script-guided workflows. Each script prints the guidance for one numbered
step; the caller passes the step number and its thoughts on every call, and
nothing is saved between calls:

1. **Planning workflow** (planner.py): Draft a plan through forced reflection
   pauses, then run the technical-writer and quality-reviewer review of the
   plan file
2. **Execution workflow** (executor.py): Execute an approved plan file through
   delegation. On resume, step 1 reconciles the plan file against work already
   done

The `plan` skill owns lifecycle decomposition of a spec into milestones and
tasks. Use this skill when that work needs forced reflection pauses, a formal
review pass, or delegated execution.

## Invocation Routing

**Invoke planner.py** when user asks to:

- "run the planner workflow" for a plan that needs forced reflection pauses
- "review" a written plan file before execution (review phase)

A request to break a spec into milestones and tasks, with no plan file and no
executor run in view, belongs to the `plan` skill, not here.

**Invoke executor.py** when user asks to:

- "execute" or "implement" an approved plan file
- "pick up where the plan left off", "resume", or "continue" execution
- Provides a plan file path for implementation

---

## When to Use

Use the planner skill when the task has:

- An approved plan file whose milestones need delegated execution
- Architectural decisions requiring documentation
- Migration steps that need coordination
- Complexity that benefits from forced reflection pauses

## When to Skip

Skip the planner skill when the task is:

- Single-step with obvious implementation
- A quick fix or minor change
- Already well-specified by the user

---

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/planner.py` | Planning and review workflow, one numbered step per call |
| `scripts/executor.py` | Execution workflow for approved plans with milestone delegation |

## Triggers

| Trigger Phrase | Operation |
|----------------|-----------|
| `run the planner workflow` | planner.py (planning phase) |
| `review the plan file at plans/X.md` | planner.py (review phase) |
| `pick up where the plan left off` | executor.py (reconcile, then continue) |
| `execute the plan at plans/X.md` | executor.py (execution phase) |
| `resume execution` | executor.py (reconcile the plan file against completed work) |

---

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Skipping review phase after planning | Misses quality/temporal issues | Always run review steps 1-2 before execution |
| Starting execution without /clear | Context pollution from planning | User should /clear before execution workflow |
| Manually following workflow steps | Each step prints the guidance and the next command | Run the script and follow its output |
| Planning single-step tasks | Overhead exceeds benefit | Implement directly without planner |
| Editing plan during execution | Creates drift between plan and actions | Return to planning phase for changes |

---

## Verification

After planning:

- [ ] Plan file written to specified path
- [ ] Review phase completed (both TW and QR steps)
- [ ] Review verdict is PASS or PASS_WITH_CONCERNS

After execution:

- [ ] All milestones marked complete
- [ ] Post-implementation QR passed
- [ ] Documentation step completed
- [ ] Retrospective generated

---

## Process

### Planning Overview

```text
PLANNING PHASE (steps 1-N)
    |
    v
Write plan to file
    |
    v
REVIEW PHASE (steps 1-2)
    |-- Step 1: @agent-technical-writer (plan-annotation)
    |-- Step 2: @agent-quality-reviewer (plan-review)
    v
APPROVED --> Execution workflow
```

### Planning Preconditions

Before invoking step 1, you MUST have:

1. **Plan file path** - If user did not specify, ASK before proceeding
2. **Clear problem statement** - What needs to be accomplished

### Planning Invocation

```bash
python3 scripts/planner.py \
  --step-number 1 \
  --total-steps <estimated_steps> \
  --thoughts "<your thinking about the problem>"
```

### Planning Arguments

| Argument        | Description                                      |
| --------------- | ------------------------------------------------ |
| `--phase`       | Workflow phase: `planning` (default) or `review` |
| `--step-number` | Current step (starts at 1)                       |
| `--total-steps` | Estimated total steps for this phase             |
| `--thoughts`    | Your thinking, findings, and progress            |

### Planning Steps

1. Confirm preconditions (plan file path, problem statement)
2. Invoke step 1 immediately
3. Complete REQUIRED ACTIONS from output
4. Invoke next step with your thoughts
5. Repeat until `STATUS: phase_complete`
6. Write plan to file using format below

## Phase Transition: Planning to Review

When planning phase completes, the script outputs an explicit `ACTION REQUIRED`
marker:

```text
============================================
>>> ACTION REQUIRED: INVOKE REVIEW PHASE <<<
============================================
```

**You MUST invoke the review phase before proceeding to execution.**

The review phase ensures:

- Temporally contaminated comments are fixed (via @agent-technical-writer)
- Code snippets have WHY comments (via @agent-technical-writer)
- Plan is validated for production risks (via @agent-quality-reviewer)
- Documentation needs are identified

## Review Phase

After writing the plan file, transition to review phase:

```bash
python3 scripts/planner.py \
  --phase review \
  --step-number 1 \
  --total-steps 2 \
  --thoughts "Plan written to [path/to/plan.md]"
```

### Review Step 1: Technical Writer

Delegate to @agent-technical-writer with mode: `plan-annotation`

### Review Step 2: Quality Reviewer

Delegate to @agent-quality-reviewer with mode: `plan-review`

### After Review

- **PASS / PASS_WITH_CONCERNS**: Ready for execution workflow
- **NEEDS_CHANGES**: Return to planning phase to address issues

---

## Execution Workflow (executor.py)

### Execution Overview

```text
Step 1: Execution Planning
    |
    v
Step 2: Reconciliation (conditional, if prior work signaled)
    |
    v
Step 3: Milestone Execution (repeat until all complete)
    |
    v
Step 4: Post-Implementation QR
    |
    v
QR issues? --YES--> Step 5: Issue Resolution --> delegate fixes --> Step 4
    |
    NO
    v
Step 6: Documentation
    |
    v
Step 7: Retrospective
```

### Execution Preconditions

Before invoking step 1, you MUST have:

1. **Approved plan file** - Plan that passed review phase
2. **Clear context window** - User should /clear before execution

### Execution Invocation

```bash
python3 scripts/executor.py \
  --plan-file PATH \
  --step-number 1 \
  --total-steps 7 \
  --thoughts "<user's request and context>"
```

### Execution Arguments

| Argument        | Description                      |
| --------------- | -------------------------------- |
| `--plan-file`   | Path to the approved plan file   |
| `--step-number` | Current step (1-7)               |
| `--total-steps` | Always 7 for executor            |
| `--thoughts`    | Your current thinking and status |

## Execution Steps

| Step | Name                   | Purpose                                       |
| ---- | ---------------------- | --------------------------------------------- |
| 1    | Execution Planning     | Analyze plan, detect reconciliation, strategy |
| 2    | Reconciliation         | (conditional) Validate existing code vs plan  |
| 3    | Milestone Execution    | Delegate to agents, run tests (repeat)        |
| 4    | Post-Implementation QR | Quality review of implemented code            |
| 5    | Issue Resolution       | (conditional) Present issues, collect fixes   |
| 6    | Documentation          | TW pass for CLAUDE.md, README.md              |
| 7    | Retrospective          | Present execution summary                     |

Note: Step 3 may be re-invoked multiple times until all milestones complete.
Step 4 may loop back through step 5 until QR passes.

---

## Resources

| Resource                              | Purpose                                            |
| ------------------------------------- | -------------------------------------------------- |
| `resources/plan-format.md`            | Plan template (injected at planning completion)    |
| `resources/diff-format.md`            | Authoritative specification for code change format |
| `resources/temporal-contamination.md` | Detecting/fixing temporally contaminated comments  |
| `resources/default-conventions.md`    | Default conventions when project docs are silent   |

Note: Execution guidance is embedded directly in `scripts/executor.py` (not in
separate resource files) since it's only used by that script.

---

## References

| Reference | Purpose |
|-----------|---------|
| `references/strategy-ooda-loop.md` | Map planning and execution phases to OODA stages |
| `references/design-pit-of-success.md` | Design milestones so the obvious path produces correct results |
| `references/mental-models-galls-law.md` | Validate milestone decomposition against incremental complexity |
| `.claude/skills/analyze/references/engineering-complexity-tiers.md` | Classify tasks by tier (single source of truth in analyze skill) |
| `references/explainers-and-intents.md` | Write explainers before work, use intents as permission gates |
| `references/agent-architecture-patterns.md` | Skill budget rule, 3-file planning pattern, milestone decomposition for agent systems |
| `references/hybrid-memory-architecture.md` | Hybrid retrieval cascade, memory decay tiers, decision extraction for planning memory systems |

---

## Quick Reference

```bash
# === PLANNING WORKFLOW ===

# Start planning
python3 scripts/planner.py --step-number 1 --total-steps 4 --thoughts "..."

# Continue planning
python3 scripts/planner.py --step-number 2 --total-steps 4 --thoughts "..."

# Start review (after plan written)
python3 scripts/planner.py --phase review --step-number 1 --total-steps 2 \
  --thoughts "Plan at plans/feature.md"

# Continue review
python3 scripts/planner.py --phase review --step-number 2 --total-steps 2 \
  --thoughts "TW done, ready for QR"

# === EXECUTION WORKFLOW ===

# Start execution
python3 scripts/executor.py --plan-file plans/feature.md --step-number 1 \
  --total-steps 7 --thoughts "Execute the feature plan"

# Continue milestone execution
python3 scripts/executor.py --plan-file plans/feature.md --step-number 3 \
  --total-steps 7 --thoughts "Completed M1, M2. Executing M3..."

# After QR passes
python3 scripts/executor.py --plan-file plans/feature.md --step-number 6 \
  --total-steps 7 --thoughts "QR passed. Running documentation."

# Generate retrospective
python3 scripts/executor.py --plan-file plans/feature.md --step-number 7 \
  --total-steps 7 --thoughts "Execution complete. Generating retrospective."
```

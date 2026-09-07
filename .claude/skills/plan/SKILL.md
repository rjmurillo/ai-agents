---
name: plan
version: 1.0.0
description: Decompose a spec into milestones and atomic tasks with dependency ordering, risk register, and complexity sizing. Use when you say `plan how to build this`, `break this into milestones`, or `decompose this spec`, and run it after spec. Do NOT use to decide what to build (use spec), and do NOT use to write the code (use build).
license: MIT
allowed-tools: Task, Skill, Read, Write, Glob, Grep
argument-hint: spec-output-or-issue-number
user-invocable: true
---

# Plan

Turn a gated spec into milestones and atomic tasks: what ships in what order,
what blocks what, what fails first, and what is explicitly out of scope.

Migrated from `.claude/commands/plan.md` under ADR-064, which makes skills the
single user-invocable surface.

@CLAUDE.md

## Triggers

`plan how to build this`, `break this into milestones`, `decompose this spec`,
`plan this work`

## If you arrived here without a spec, run the front-gate first

Planning a spec that was never gated manufactures work. If there is no `/spec`
output for this work (no requirement, no design, no testable acceptance
criteria), do not decompose it into milestones yet. Run `spec` first: it applies
the front gate (the six forcing questions, the `front-gate-before-pipeline`
pattern) and confirms a named blocked user, a documented status quo, and a
concrete observation before any downstream step runs. Return here once the spec
exists.

Skip this only when the user explicitly asks to plan an ungated idea and accepts
that trade-off.

Plan: $ARGUMENTS

If `$ARGUMENTS` is empty, check for recent spec output in the conversation. If
none is found, ask what to plan rather than inferring it.

## Process

1. Read the spec or issue.
2. Map sub-problems to existing code. What already exists? Use Grep and Glob to
   verify rather than assuming.
3. `Task(subagent_type="milestone-planner")`: You are a project planner. Break
   the spec into milestones with clear exit criteria. Each milestone is
   independently shippable. Sequence by dependencies. Flag parallel
   opportunities.
4. `Task(subagent_type="task-decomposer")`: You are a work breakdown specialist.
   Decompose each milestone into atomic tasks. Each task is independently
   verifiable with a clear done definition. Size by complexity (S/M/L), not time.
5. `Skill(skill="execution-plans")` to persist the plan as a versioned artifact.
6. `Task(subagent_type="analyst")`: You are a risk analyst. Run a pre-mortem on
   this plan. What fails first? What dependencies are fragile? What assumptions
   are untested?
7. `Task(subagent_type="critic")`: You are a plan reviewer. Validate: is scope
   complete? Can tasks execute in the stated sequence? Are estimates credible?
   Is anything missing?

## Evaluation Axes

| Axis | Question |
|------|----------|
| Scope integrity | Nothing unnecessary, nothing missing |
| Dependency ordering | Can tasks execute in the stated sequence? |
| Risk coverage | Does every P0 risk have a mitigation? |
| Estimate confidence | Complexity-based sizing (S/M/L), never time-based |
| Reversibility | Which steps are hard to undo? |

## Principles

- **Programming by Intention.** Each task reads like an intent, not an
  implementation detail.
- **OODA loop.** Observe (read the spec), Orient (map to existing code), Decide
  (sequence tasks), Act (commit the plan). Faster loops win.
- **First principles.** Question the requirement, try to delete the step, then
  optimize, then speed up, then automate. Never automate something that should
  not exist.

## Output

| Section | Contents |
|---------|----------|
| Milestones | Numbered, each with exit criteria |
| Tasks per milestone | Atomic, with acceptance criteria and S/M/L sizing |
| Dependency graph | What blocks what, what can run in parallel |
| Risk register | Risk, likelihood, impact, mitigation |
| Deferred items | Explicitly out of scope for this plan |

## Verification

- [ ] A spec exists for this work, or the user accepted planning an ungated idea
- [ ] Sub-problems mapped against real code, verified with Grep or Glob
- [ ] Every milestone has exit criteria and is independently shippable
- [ ] Every task has a done definition and an S/M/L size, never a time estimate
- [ ] Plan persisted through `execution-plans`, not left in the conversation
- [ ] Pre-mortem run, and every P0 risk carries a mitigation
- [ ] Deferred items listed explicitly rather than left unstated

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Planning an ungated idea | Produces a credible milestone list for work no user asked for | Run `spec` first, or record that the user accepted the trade |
| Time estimates | Anchor on a number nobody can hold, and rot on contact | Size by complexity, S/M/L |
| Mapping sub-problems from memory | Plans a rewrite of code that already exists | Grep and Glob before claiming something is missing |
| Milestones that ship only together | Removes the option to stop early, which is the point of a milestone | Split until each one is independently shippable |
| Silent scope cuts | The reader cannot tell a decision from an oversight | List them under Deferred items |

## Extension Points

- **New evaluation axis.** Add a row to the axes table and a matching
  Verification checkbox, so the axis is both stated and checked.
- **Different persistence.** Step 5 delegates to `execution-plans`. A project
  that tracks plans elsewhere swaps that one call, not the process.
- **Parallel decomposition.** Steps 3 and 4 run per milestone. For a large spec
  they can fan out per milestone rather than running once over all of them.

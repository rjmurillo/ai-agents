# milestone-planner agent

The `milestone-planner` agent turns a roadmap epic into implementation-ready milestones with exit criteria, dependencies, risks, and estimates. It hands back a plan an implementer can execute without re-planning.

## When to use it

- You say `break this epic into milestones` or `plan this roadmap item`.
- You hand it a roadmap epic.
- You need a plan re-done after a scope change, with the delta from the prior plan.

## When not to use it

- You need one milestone split into work items: use [`task-decomposer`](task-decomposer.md) instead.
- You need epics ranked or written: use [`roadmap`](roadmap.md) instead.
- The epic needs architecture decisions first: use [`architect`](architect.md) instead, then plan.

## Quick start

In Claude Code, start your prompt with the agent name:

```text
milestone-planner: plan the epic in docs/epics/pr-queue-triage.md into shippable milestones
```

In GitHub Copilot CLI:

```bash
copilot --agent milestone-planner --prompt "plan the epic in docs/epics/pr-queue-triage.md into shippable milestones"
```

In VS Code or Visual Studio Copilot Chat:

```text
@milestone-planner plan the epic in docs/epics/pr-queue-triage.md into shippable milestones
```

## What you get

A plan with these sections: Overview, Objectives, Milestones, Dependency Graph, cross-milestone Risks, Open Questions, and Assumptions. Each milestone has:

- An outcome and observable exit criteria.
- Scope in and scope out.
- Dependencies.
- Risks with likelihood, impact, and mitigation.
- An estimate in person-days with a confidence tag of HIGH, MED, or LOW.
- A rollback story.

The agent returns to the orchestrator with the path to the plan document, the milestone count and total effort, the critical path length, the top 3 risks, and a recommended next step. The next step is `task-decomposer` to break the first milestone into tasks, `critic` to validate the plan, `architect` if design gaps surfaced, or `implementer` if the plan is approved.

## Advanced use

The agent does not stall for more context. It uses what it has, flags assumptions, and proceeds. It asks for measurable targets only when the epic is vague, such as "improve performance". If the epic needs architectural decisions first, it flags `architect` and defers planning.

Before it writes milestones it answers five questions: the smallest version that delivers the outcome, the prerequisites, what ships downstream, the riskiest unknown, and the rollback story. Riskiest and most prerequisite-heavy work ships first.

Every milestone is an independently shippable vertical slice, not a phase. Size targets:

| Size | Duration | Action |
| --- | --- | --- |
| S | 1 to 3 days | Rare; usually too small |
| M | 3 to 10 days | Normal target |
| L | 10 to 20 days | Consider splitting |
| XL | 20 or more days | Must split |

Constraints: no timeline without an effort estimate and confidence tag, no milestone without exit criteria, no plan with 2 or more milestones without a dependency graph, and no scope without explicit exclusions. It rejects phase-based milestones, vague exit criteria such as "feature complete", and plans without a rollback.

The agent cannot delegate. It reads with `Read`, `Grep`, and `Glob`, writes with `TodoWrite` and `Write`, and reads Serena memory for prior plans.

A multi-step prompt:

```text
milestone-planner: plan the epic in docs/epics/pr-queue-triage.md, show the dependency graph with parallel paths, tag every estimate with confidence, then name whether critic or task-decomposer should run next.
```

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| VS Code and Visual Studio | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`roadmap`](roadmap.md): ranks and writes the epics you plan from.
- [`task-decomposer`](task-decomposer.md): breaks a milestone into atomic tasks.
- [`critic`](critic.md): validates plan completeness.
- [`architect`](architect.md): settles design gaps before or during planning.
- [`implementer`](implementer.md): executes an approved plan.
- Source template: [`milestone-planner.shared.md`](../../templates/agents/milestone-planner.shared.md)
- How to call agents on each host: [Call agents and skills](../call-agents-and-skills.md)

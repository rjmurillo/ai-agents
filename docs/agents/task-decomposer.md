# task-decomposer agent

The `task-decomposer` agent breaks a PRD or epic into atomic, estimable tasks. Each task has acceptance criteria, a complexity size, and dependencies. It hands back a saved task document.

## When to use it

- You say `decompose this PRD` or `break into atomic tasks`.
- You hand it a PRD or an epic.
- You need each task small enough that someone can pick it up and know what to do.

## When not to use it

- You need roadmap epics sequenced into milestones: use [`milestone-planner`](milestone-planner.md) instead. Milestone planning comes first. This agent then breaks each milestone into tasks.
- You need the PRD written: use [`explainer`](explainer.md) instead.
- You need the tasks built: use [`implementer`](implementer.md) instead.

## Quick start

In Claude Code, start your prompt with the agent name:

```text
task-decomposer: break .project-toolkit/planning/PRD-merge-queue.md into atomic tasks
```

In GitHub Copilot CLI:

```bash
copilot --agent task-decomposer --prompt "break .project-toolkit/planning/PRD-merge-queue.md into atomic tasks"
```

In VS Code or Visual Studio Copilot Chat:

```text
@task-decomposer break .project-toolkit/planning/PRD-merge-queue.md into atomic tasks
```

## What you get

A file at `.project-toolkit/planning/TASKS-[feature-name].md` with:

- The source PRD.
- A summary table of task counts by complexity.
- Milestones, each with a goal and its tasks.
- A dependency graph of the tasks.
- A risk table.

Each task has an ID (`TASK-NNN`), a type (Feature, Bug, Chore, or Spike), a complexity, a description, acceptance criteria as checkboxes, dependencies, and affected files.

| Size | Guideline |
| --- | --- |
| XS | Single function change, obvious fix |
| S | Single file, straightforward logic |
| M | Multiple files, some complexity |
| L | Multiple components, heavy logic |
| XL | Cross-cutting, architectural impact |

The agent sizes by complexity, not hours.

## Advanced use

Estimate reconciliation: if the sum of your task estimates differs from the source PRD or epic estimate by more than 10 percent, the agent must reconcile. It picks one action:

| Action | When |
| --- | --- |
| Update source | The tasks reveal more accurate scope. It recommends an epic update. |
| Document rationale | The difference is justified. It explains why. |
| Flag for review | It is unsure. It flags it for `critic` or `milestone-planner`. |

The output then carries an Estimate Reconciliation section with the source document and estimate, the derived estimate, the difference, a status of Aligned, Reconciled, or Flagged for review, and a rationale.

Before it hands off, the agent checks a list: the document is saved, IDs are unique, every task has criteria and a complexity, dependencies and a graph exist, milestone groupings are logical, reconciliation is done when the source had estimates, and the summary counts match. If an item fails, it does not hand off. It fixes the item or documents the blocker. When you asked for GitHub issues and tasks were filed, each parent and dependency is a native link, not only `#N` text.

It uses the Memory Router before a breakdown and can store estimation notes under a `planning/estimation-[feature]` memory name. Serena writes happen only from the checkout Serena started in. It cannot delegate.

| Target | When | Purpose |
| --- | --- | --- |
| `critic` | Tasks ready | Validate the breakdown |
| `implementer` | Tasks approved | Begin coding |
| `milestone-planner` | Scope concerns | Adjust the plan |

A multi-step prompt:

```text
task-decomposer: decompose .project-toolkit/planning/PRD-merge-queue.md, reconcile against the PRD estimate, save TASKS-merge-queue.md, and recommend critic or milestone-planner as the next step.
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

- [`milestone-planner`](milestone-planner.md): creates the milestones first.
- [`explainer`](explainer.md): writes the PRD you decompose.
- [`critic`](critic.md): validates the breakdown.
- [`implementer`](implementer.md): builds the approved tasks.
- Source template: [`task-decomposer.shared.md`](../../templates/agents/task-decomposer.shared.md)
- How to call agents on each host: [Call agents and skills](../call-agents-and-skills.md)

# execution-plans

Keeps execution plans as versioned files in your repository. You create a plan, log progress and decisions as work moves, and then complete or abandon it. The file moves between folders to show its state.

## When to use it

- You want to persist a finished plan as a tracked artifact.
- You say `create execution plan`, `update plan progress`, `log decision`, `complete plan`, or `abandon plan`.
- You need a decision log and progress log that survive across sessions.

## When not to use it

- You need to break work into milestones: use [`plan`](plan.md) instead.
- You need to execute an approved plan file through delegation: use [`planner`](planner.md) instead.

## Quick start

This skill has no short slash command, so the agent usually loads it for you. In Claude Code you can still type `/project-toolkit:execution-plans`. The agent loads it when your request matches. To ask for it by name, say:

```text
Use the execution-plans skill to create an execution plan for migrating the build scripts to uv, linked to issue 123.
```

The agent copies the plan template into the `active/` folder, fills in the metadata, and defines objectives as checkboxes. You end with a plan file you can open and edit.

## What you get

A Markdown plan file under `.project-toolkit/plans/`. The folder shows the plan's state.

| Folder | Holds |
| --- | --- |
| `active/` | Plans in progress. |
| `completed/` | Plans that finished. |
| `abandoned/` | Plans that stopped, with the rationale. |

Each plan has these sections, taken from [`.project-toolkit/plans/TEMPLATE.md`](../../.project-toolkit/plans/TEMPLATE.md):

| Section | Purpose |
| --- | --- |
| Metadata | Status, dates, owner, complexity. |
| Objectives | Checkboxes for trackable goals. |
| Decision Log | Table of decisions with rationale. |
| Progress Log | Timestamped updates with agent attribution. |
| Blockers | Current impediments. |
| Related | Links to issues, PRs, and ADRs. |

The skill also reads and writes [`.project-toolkit/debt/tech-debt-registry.md`](../../.project-toolkit/debt/tech-debt-registry.md), which lists known technical debt items. It creates missing directories when the first plan is written.

## Advanced use

Each trigger phrase maps to one operation.

| Trigger phrase | Operation |
| --- | --- |
| `create execution plan` | Create a new plan in `active/`. |
| `update plan progress` | Add a progress entry to an existing plan. |
| `log decision` | Add a row to the plan's decision log. |
| `complete plan` | Move the plan to `completed/`. |
| `abandon plan` | Move the plan to `abandoned/` with a rationale. |

### Lifecycle steps

- **Create:** copy `TEMPLATE.md` to `.project-toolkit/plans/active/<slug>.md`. Set status to In Progress, set the created date, and set the owner to the agent name. Define objectives as checkboxes and link the related issue or PR.
- **Update progress:** check off completed objectives, add a Progress Log row with date, update, and agent name, and update blockers if any appear.
- **Log a decision:** add a row with the date, the decision, the rationale, and the alternatives considered.
- **Complete:** verify all objectives are checked, set status to Completed, move the file to `completed/`, and add a final progress entry.
- **Block:** set status to Blocked, document the impediment in Blockers, and add a progress entry.
- **Abandon:** set status to Abandoned, document the rationale in Blockers or the final progress entry, and move the file to `abandoned/`.

### Chaining

[`plan`](plan.md) persists its finished plan through this skill. [`planner`](planner.md) creates plans here when it executes complex work. Retrospectives link back to completed plans, and session logs reference active plans when relevant.

The skill has no scripts.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`plan`](plan.md): breaks work into milestones and calls this skill to persist the result.
- [`planner`](planner.md): executes an approved plan file through delegation.
- [`retrospective`](retrospective.md): links back to completed plans.
- Source: [`SKILL.md`](../../src/claude/skills/execution-plans/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)

# plan

Turns a spec into milestones and atomic tasks. You get dependency ordering, a risk register, S/M/L sizing, and a list of what is out of scope. The plan is saved as a versioned artifact.

## When to use it

- You have spec output or an issue and need to know what ships in what order.
- You say `plan how to build this`, `break this into milestones`, `decompose this spec`, or `plan this work`.
- You have already run [`spec`](spec.md).

## When not to use it

- You have not decided what to build: use [`spec`](spec.md).
- You are ready to write code: use [`build`](build.md).
- You have an approved plan file to run or resume through script-driven delegation: use [`planner`](planner.md).

## Quick start

In Claude Code, after a plugin install, run:

```text
/project-toolkit:plan 42
```

In GitHub Copilot CLI, or in a Claude Code session inside a checkout of this repository, drop the prefix: `/plan`. The argument can be spec output or an issue number, such as `42`.

With no argument, it looks for recent spec output in the conversation. If it finds none, it asks what to plan.

> [!NOTE]
> If no `/spec` output exists for the work, the skill stops and sends you to [`spec`](spec.md) first. Planning an ungated idea produces milestones for work nobody asked for. You can override this by asking explicitly to plan an ungated idea.

## What you get

| Section | Contents |
| --- | --- |
| Milestones | Numbered, each with exit criteria |
| Tasks per milestone | Atomic, with acceptance criteria and S/M/L sizing |
| Dependency graph | What blocks what, what can run in parallel |
| Risk register | Risk, likelihood, impact, mitigation |
| Deferred items | Explicitly out of scope for this plan |

Sizing is by complexity (S, M, L), never by time. The plan is persisted through [`execution-plans`](execution-plans.md) instead of staying in the conversation.

## Advanced use

**Process.** The skill runs seven steps:

1. Read the spec or issue.
2. Map sub-problems to existing code with Grep and Glob. If three tool calls surface nothing useful, it stops searching, reasons from first principles, and documents what it tried.
3. The `milestone-planner` agent breaks the spec into independently shippable milestones, sequenced by dependency, with parallel opportunities flagged.
4. The `task-decomposer` agent splits each milestone into atomic, verifiable tasks with done definitions.
5. [`execution-plans`](execution-plans.md) persists the plan.
6. The `analyst` agent runs a pre-mortem: what fails first, which dependencies are fragile, which assumptions are untested.
7. The `critic` agent validates the plan.

**Evaluation axes.** The critic checks scope integrity, dependency ordering, risk coverage (every P0 risk has a mitigation), estimate confidence, and reversibility.

**Principles.** Tasks read as intent, not implementation detail. The skill follows an observe, orient, decide, act loop. It questions each requirement before sequencing it, and does not reopen a frozen spec.

**Chaining.** Run [`spec`](spec.md) before it and [`build`](build.md) after it. [`autoplan`](autoplan.md) routes Feature-tier requests through all three.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`spec`](spec.md): produces the input.
- [`build`](build.md): implements the tasks.
- [`milestone-planner`](../agents/milestone-planner.md) and [`task-decomposer`](../agents/task-decomposer.md): the agents that do the decomposition.
- Source: [`SKILL.md`](../../src/claude/skills/plan/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)

# planner

Runs a plan-and-execute workflow one numbered step at a time. It drafts a plan with forced reflection pauses and reviews the plan file. Then it delegates each milestone of an approved plan to specialized agents.

## When to use it

- You have an approved plan file whose milestones need delegated execution.
- The task has architectural decisions that need documentation, migration steps that need coordination, or complexity that benefits from forced reflection pauses.
- You say `run the planner workflow`, `review the plan file at plans/X.md`, `execute the plan at plans/X.md`, `pick up where the plan left off`, or `resume execution`.

## When not to use it

- You want to decompose a spec into milestones and tasks in the lifecycle chain: use [`plan`](plan.md) instead.
- You want to log progress on a plan artifact: use [`execution-plans`](execution-plans.md) instead.
- The task is a single step with an obvious implementation, a quick fix, or already well specified: implement it directly.

## Quick start

This skill has no short slash command, so the agent usually loads it for you. In Claude Code you can still type `/project-toolkit:planner`. The agent loads it when your request matches. To ask for it by name, say:

```text
Use the planner skill to execute the plan at plans/auth-migration.md.
```

Each script prints guidance for one step. The agent follows that output, passes its thoughts back on the next call, and repeats until the workflow finishes. Nothing is saved between calls. For execution, you end with all milestones complete, a quality review result, a documentation pass, and a retrospective.

> [!NOTE]
> Run `/clear` before the execution workflow. Planning context pollutes execution.

## What you get

| Workflow | Script | Ends with |
| --- | --- | --- |
| Planning | `planner.py` | A plan file at the path you give, then a review phase with a verdict of `PASS`, `PASS_WITH_CONCERNS`, or `NEEDS_CHANGES`. |
| Execution | `executor.py` | All milestones complete, a post-implementation quality review pass, a documentation step, and a retrospective. |

On `PASS` or `PASS_WITH_CONCERNS`, the plan is ready for execution. On `NEEDS_CHANGES`, return to the planning phase.

## Advanced use

### Planning workflow

You need a plan file path and a clear problem statement before step 1. If you gave no path, the agent asks.

1. Confirm the preconditions.
2. Run step 1 right away and complete the required actions in the output.
3. Run the next step with your thoughts. Repeat until the output says `STATUS: phase_complete`.
4. Write the plan to the file.
5. Run the review phase. Step 1 delegates to the comment-analyzer agent, which returns findings. You apply them to the plan file. Step 2 delegates to the quality-reviewer agent in `plan-review` mode.

The review finds temporally contaminated comments, flags code snippets that lack WHY comments, validates the plan for production risks, and identifies documentation needs.

```bash
uv run python .claude/skills/planner/scripts/planner.py --help
```

| Flag | Meaning |
| --- | --- |
| `--phase` | `planning` (default) or `review`. |
| `--step-number` | Current step, starting at 1. |
| `--total-steps` | Estimated total steps for this phase. |
| `--thoughts` | Your thinking, findings, and progress. |

Exit code `0` means step guidance printed. Exit code `1` means the step number or total steps are below 1.

```bash
uv run python .claude/skills/planner/scripts/planner.py --step-number 1 --total-steps 4 --thoughts 'Design auth system'
uv run python .claude/skills/planner/scripts/planner.py --phase review --step-number 1 --total-steps 2 --thoughts 'Plan at plans/auth.md'
```

> [!WARNING]
> The shell expands `$(...)` and backticks inside a double-quoted `--thoughts` value before the script runs. Use single quotes, as shown, and never paste request text you did not write into this argument.

### Execution workflow

You need an approved plan file that passed review, and a cleared context window.

| Step | Name | Purpose |
| --- | --- | --- |
| 1 | Execution Planning | Analyze the plan, detect reconciliation, choose a strategy. |
| 2 | Reconciliation | Conditional. Validate existing code against the plan. |
| 3 | Milestone Execution | Delegate to agents and run tests. Repeats until all milestones finish. |
| 4 | Post-Implementation QR | Quality review of the implemented code. |
| 5 | Issue Resolution | Conditional. Present issues and collect fixes, then loop back to step 4. |
| 6 | Documentation | The coordinator edits `CLAUDE.md` index entries directly. A new `README.md` or ARCHITECTURE scaffold uses the `codebase-documenter` skill. A new README with project content gets a `codebase-documenter` scaffold, then the `technical-writing` skill fills it. An edit to an existing `README.md` or docs page uses the `technical-writing` skill. Docstrings go to the implementer agent, and the comment-analyzer agent checks transcribed comments. |
| 7 | Retrospective | Present the execution summary. |

On resume, step 1 reconciles the plan file against work already done.

A milestone whose files are all `*.md` or `*.rst` and that holds docs pages goes to a docs skill, not an agent. The coordinator, or a general-purpose subagent it starts, loads the skill and follows it. A new README or ARCHITECTURE scaffold uses `codebase-documenter`, which stops at placeholders. A new README with project content gets a `codebase-documenter` scaffold, then the `technical-writing` skill fills it. An edit to an existing docs page, including an existing README, uses `technical-writing`. A milestone for agent prompts or `SKILL.md` files goes to the implementer agent instead.

```bash
uv run python .claude/skills/planner/scripts/executor.py --help
```

| Flag | Meaning |
| --- | --- |
| `--plan-file` | Path to the approved plan file. |
| `--step-number` | Current step, 1 to 7. |
| `--total-steps` | Always 7. |
| `--thoughts` | Your current thinking and status. |

Exit code `0` means step guidance printed. Exit code `1` means the step number is outside 1 to 7.

```bash
uv run python .claude/skills/planner/scripts/executor.py --plan-file plans/feature.md --step-number 1 --total-steps 7 --thoughts 'Execute the feature plan'
```

### Habits that avoid wasted work

- Always run the review phase before execution.
- Run the script and follow its output. Do not follow the steps by hand.
- Do not edit the plan during execution. Return to the planning phase for changes.

### Chaining

[`autoplan`](autoplan.md) routes execution, review, or resume of a planner-written plan file here. The [`plan`](plan.md) skill owns lifecycle decomposition of a spec into milestones and tasks. Use this skill when that work needs forced reflection pauses, a formal review pass, or delegated execution. Use [`execution-plans`](execution-plans.md) to log progress on a plan artifact.

Supporting files ship with the skill: [`resources/plan-format.md`](../../src/claude/skills/planner/resources/plan-format.md) (plan template), [`resources/diff-format.md`](../../src/claude/skills/planner/resources/diff-format.md), [`resources/temporal-contamination.md`](../../src/claude/skills/planner/resources/temporal-contamination.md), and [`resources/default-conventions.md`](../../src/claude/skills/planner/resources/default-conventions.md).

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`plan`](plan.md): decomposes a spec into milestones and tasks.
- [`execution-plans`](execution-plans.md): logs progress on a plan artifact.
- [`autoplan`](autoplan.md): routes plan-file requests to this skill.
- Source: [`SKILL.md`](../../src/claude/skills/planner/SKILL.md)
- Reference: [OODA loop mapping](../../src/claude/skills/planner/references/strategy-ooda-loop.md)
- Reference: [Pit of success](../../src/claude/skills/planner/references/design-pit-of-success.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)

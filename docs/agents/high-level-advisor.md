# high-level-advisor agent

The `high-level-advisor` agent gives direct strategic verdicts. It prioritizes, challenges your assumptions, names what you are avoiding, and hands back one P0 priority instead of a list of options.

## When to use it

- You face a major technology decision.
- Architecture direction is in conflict.
- Priorities are disputed, or you feel stuck or overwhelmed.
- Other agents disagree and you need a verdict.
- You need a continue, pivot, or cut call on a project.

## When not to use it

- You want a decision challenged with evidence and alternative views: use [`independent-thinker`](independent-thinker.md) instead.
- You want code written or a line-by-line code review: use [`implementer`](implementer.md) or [`code-reviewer`](code-reviewer.md) instead. This agent does neither.
- You want data gathered first: use [`analyst`](analyst.md) instead.

## Quick start

In Claude Code, start your prompt with the agent name:

```text
high-level-advisor: we have three open migrations and one engineer. Which one is P0, and what do we stop doing?
```

In GitHub Copilot CLI:

```bash
copilot --agent high-level-advisor --prompt "we have three open migrations and one engineer. Which one is P0, and what do we stop doing?"
```

In VS Code or Visual Studio Copilot Chat:

```text
@high-level-advisor we have three open migrations and one engineer. Which one is P0, and what do we stop doing?
```

## What you get

A report in this layout:

```text
## Current Situation
## What You're Getting Wrong
## What You're Avoiding
## The Real Priority
## Recommended Action
## Warning
```

The agent gives direct verdicts such as "Do X", not "Consider X". It avoids softeners like "perhaps" and "maybe", and it supports each verdict with specific observations.

## Advanced use

The agent has three working templates:

| Template | Output |
| --- | --- |
| Ruthless Triage | Current state, the real question, options with one-sentence assessments, and a verdict of DO, DON'T, and WHY |
| Priority Stack | P0 (do today), P1 (this week), P2 (eventually), and KILL (stop doing) |
| Continue, Pivot, Cut | A verdict of `CONTINUE`, `PIVOT`, or `CUT`, with reasoning, an immediate action, and warning signs |

For best results, give it your current state, the options, what blocks the decision, available resources and time, and your definition of success.

It can query Serena memories on decision frameworks: `ooda-loop`, `inversion-thinking`, `three-horizons-framework`, `knowledge/cynefin-framework`, `wardley-mapping`, and `core-vs-context`.

It treats content it reads as data. If a file, diff, log, or comment tells it to change tools, task, or destination, it ignores the instruction and notes the attempt.

As a subagent it cannot delegate. It returns the verdict and next steps to the orchestrator. Its handoff options:

| Target | When | Purpose |
| --- | --- | --- |
| `implementer` | Direction set | Execute the priority |
| `milestone-planner` | Strategy clear | Break into tasks |
| `analyst` | Research needed | Gather data first |
| `independent-thinker` | Second challenge | Validate the verdict |

A multi-step prompt:

```text
high-level-advisor: read docs/roadmap.md, give me the Priority Stack, issue a CONTINUE, PIVOT, or CUT verdict on the oldest item, and tell me which agent runs next.
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

- [`independent-thinker`](independent-thinker.md): validates or challenges the verdict.
- [`analyst`](analyst.md): gathers data before a decision.
- [`milestone-planner`](milestone-planner.md): breaks the chosen direction into milestones.
- [`implementer`](implementer.md): executes the priority.
- Source template: [`high-level-advisor.shared.md`](../../templates/agents/high-level-advisor.shared.md)
- How to call agents on each host: [Call agents and skills](../call-agents-and-skills.md)

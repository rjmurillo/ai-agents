# retrospective agent

The `retrospective` agent turns what happened in a task or session into learnings. It runs structured retrospective activities, scores each learning for atomicity, and hands back a saved retrospective document plus a "Findings for the owner" table.

## When to use it

- A `reflect` pass produced a high-confidence finding.
- `main` went red.
- A merge was reverted or force-fixed.
- You corrected the agent's work explicitly.
- You want root-cause analysis with Five Whys, or learnings scored and ready for the skillbook.

There is no calendar entry and no every-session run.

## When not to use it

- You want the learnings written to the skill store: use [`skillbook`](skillbook.md) instead. This agent returns batches for it.
- You want the retrospective as a skill workflow: use the [`retrospective`](../skills/retrospective.md) skill instead.
- You want a quick reflection on a session: use the [`reflect`](../skills/reflect.md) skill instead.

## Quick start

In Claude Code, start your prompt with the agent name:

```text
retrospective: analyze the PR 7361 retry bug, find the root cause with Five Whys, and extract learnings
```

In GitHub Copilot CLI:

```bash
copilot --agent retrospective --prompt "analyze the PR 7361 retry bug, find the root cause with Five Whys, and extract learnings"
```

In VS Code or Visual Studio Copilot Chat:

```text
@retrospective analyze the PR 7361 retry bug, find the root cause with Five Whys, and extract learnings
```

## What you get

A retrospective document saved in `.project-toolkit/retrospective/` as `YYYY-MM-DD-[scope].md`. The agent returns to the orchestrator with:

1. The learnings and recommended skill updates.
2. The `Findings for the owner` table, with Blocker rows first.
3. A recommendation to route to `skillbook` for persistence, when it applies.

Each learning is scored 0 to 100 percent for atomicity and tied to execution evidence such as tool calls, timestamps, and outcomes. Every insight links to a specific artifact.

| Atomicity | Action |
| --- | --- |
| 95 to 100 percent | Add to the skillbook |
| 70 to 94 percent | Add with refinement |
| 40 to 69 percent | Refine before adding |
| Under 40 percent | Reject |

## Advanced use

The agent runs seven phases in order and observes before it interprets:

| Phase | Work |
| --- | --- |
| 0 Data gathering | 4-Step Debrief, execution trace, and Mad, Sad, or Glad outcome classification |
| 1 Generate insights | Five Whys (mandatory for every failure), fishbone, force field, patterns and shifts, learning matrix |
| 2 Diagnosis | Critical error patterns, success analysis, near misses, efficiency, skill gaps, and traceability health |
| 3 Decide | Keep, Drop, Add, or Modify, plus SMART validation and dependency ordering |
| 4 Learning extraction | Atomicity scoring, skillbook updates, and a duplicate check |
| 5 Recursive extraction | Batches of 3 to 5 learnings, at most 5 iterations and 20 learnings per session |
| 6 Close | +/Delta, Delta Triage, ROTI (0 to 4), and Helped, Hindered, Hypothesis |

A Bias Guard runs before the agent assigns a root cause. It asks whether the conclusion protects a tool, method, or author instead of following the evidence.

Delta Triage assigns each item a class from the frozen completion contract: Blocker, Requested improvement, Optional enhancement, or Side quest. A Blocker stays blocking. Retrospectives recommend. The owner decides what becomes tracked work, so the agent files no GitHub issue and writes no backlog memory file.

Long rubrics live in the `retrospective` skill's `references/` folder: `frameworks.md`, `diagnosis-and-actions.md`, `learning-template.md`, `recursive-extraction.md`, and `handoff-example.md`. The agent reads one only when its phase needs it. If the references do not resolve, such as in a VS Code agent list, it applies the rules in its own file and states which reference it could not load.

Root cause patterns are stored under categories: Cross-Cutting Concerns, Fail-Safe Design, Test-Implementation Drift, Premature Validation, Context Loss, and Skill Gap. If a similar pattern exists with more than 70 percent similarity, the agent updates it instead of creating a new one.

The agent runs the `prose-self-check` skill on prose artifacts. It cannot delegate. Its handoff options:

| Target | When | Purpose |
| --- | --- | --- |
| `skillbook` | Learnings ready | Store skills |
| `implementer` | Coding skill found | Apply next time |
| `milestone-planner` | Process improvement | Update approach |
| `architect` | Design insight | Update guidance |

A multi-step prompt:

```text
retrospective: analyze why main went red after PR 7360, build the execution trace, run Five Whys, score each learning for atomicity, and return the Findings for the owner table with Blockers first.
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

- [`retrospective`](../skills/retrospective.md): the skill that holds the references.
- [`reflect`](../skills/reflect.md): a lighter reflection pass.
- [`skillbook`](skillbook.md): persists the learnings.
- [`prose-self-check`](../skills/prose-self-check.md): audits the prose.
- Source template: [`retrospective.shared.md`](../../templates/agents/retrospective.shared.md)
- How to call agents on each host: [Call agents and skills](../call-agents-and-skills.md)

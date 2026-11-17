# decision-question

Decides whether the agent should ask you to choose, and if so builds the smallest complete decision brief. It stops the agent from asking questions you already answered or delegated.

## When to use it

- The agent hits a material decision only you can make.
- You want a decision brief with options, consequences, and a recommendation.
- Trigger phrases: `ask the user to choose between these paths`, `do I need a user decision here`, `present a decision brief`, `which option should the user pick`.

## When not to use it

- You want to review a decision already made: use [`decision-critic`](decision-critic.md).
- You want to surface project risks: use [`pre-mortem`](pre-mortem.md).

## Quick start

This skill has no short slash command, so the agent usually loads it for you. In Claude Code you can still type `/project-toolkit:decision-question`. The [`autoplan`](autoplan.md) skill loads it when it finds a decision only you can make. To ask for it by name, say:

```text
Use the decision-question skill to decide whether I need to choose between a schema migration and a compatibility view, and brief me if so.
```

The skill first applies a routing gate. If no decision is yours to make, it acts within the authorization you already gave and does not ask. Otherwise it presents one decision at a time through your host's ask tool.

## What you get

The routing gate returns no question when any of these holds:

- You delegated the choice.
- Repository or safety policy mandates one option.
- Existing acceptance criteria decide it.
- The choice is a reversible implementation detail within authorized scope.
- Reading evidence or tools resolves the uncertainty.
- The task is terminal and the question would only invite optional follow-up.

Each decision in a brief carries:

- A stable ID (`D1`, `D2`).
- One sentence on what must be decided now, and why it matters now.
- At least two materially distinct options with their consequences, shown 2 to 4 per page.
- A recommendation with its load-bearing reason, or a statement that the evidence supports none.
- `Hold`, only when deferring is legitimate and a reopen condition exists.

## Advanced use

The checker script reads a brief and returns one JSON object. Run it from the root of a checkout of this repository:

```bash
uv run python .claude/skills/decision-question/scripts/decision_question.py --brief brief.json --max-options 4
```

| Flag | Meaning |
| --- | --- |
| `--brief` | Path to a decision brief JSON file. Required. |
| `--max-options` | Options per prompt your host accepts. Minimum 3. Claude Code allows 4. |

| Exit code | Meaning |
| --- | --- |
| 0 | Routing resolved: no question needed (`skip`), a complete brief (`ask`), decisions held (`held`), or nothing left (`resolved`). |
| 1 | Invalid arguments, or unreadable or malformed brief JSON. Also a non-option answer, a duplicate decision ID, an out-of-range `paging` count, or a cap below 3. |
| 2 | The brief is incomplete (`incomplete`, with the missing fields), or an earlier answer ruled out the recommended option (`revise_recommendation`). |

An exit 2 with a `ptk_run:` line on stderr and no JSON is a launcher failure. Read the line and fix that cause, not the brief.

The skill presents the decision with the host's ask tool: `AskUserQuestion` in Claude Code, `request_user_input` in Muse Code and in Codex Plan mode (at most 3 questions), and a plain chat question when no tool exists. Record your answer under `answers` and rerun. If you pick `_more`, add one to that decision's `paging` count and rerun to get the next page. Dependent decisions are pruned or filtered from earlier answers, and unresolved IDs are never renumbered.

With five or more options, the skill never drops one. It batches coherent alternatives into groups of at most 4, or splits into one call per option, each answered Include, Defer, Cut, or Hold. Split is the default when unsure. Past 6 options, it first asks whether to proceed, narrow, or batch.

For weak evidence on an irreversible choice, the output's `pre_ask_review` names [`decision-critic`](decision-critic.md) and [`pre-mortem`](pre-mortem.md). Run one before you ask. The field rules are in [`references/decision-brief-protocol.md`](../../src/claude/skills/decision-question/references/decision-brief-protocol.md).

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`autoplan`](autoplan.md): invokes this skill when its confusion protocol finds a decision only you can make.
- [`decision-critic`](decision-critic.md): optional review step for a high-impact decision.
- [`pre-mortem`](pre-mortem.md): optional risk step for a high-impact decision.
- Source: [`SKILL.md`](../../src/claude/skills/decision-question/SKILL.md)
- Reference: [`decision-brief-protocol.md`](../../src/claude/skills/decision-question/references/decision-brief-protocol.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)

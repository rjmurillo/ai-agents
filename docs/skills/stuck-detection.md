# stuck-detection

Detects when an agent repeats the same topics, or retries the same failing command or edit. It emits a self-reflection nudge so the orchestrator can break the loop. It is deterministic and makes no model calls.

## When to use it

- An orchestrator risks repeating tool calls or status updates.
- A long session shows less variety in responses.
- The same command keeps failing, or a file keeps getting edited while the same test still fails.
- Trigger phrases: `check stuck loop`, `detect repetition`, `agent looping`, `check failure loop`, `reset stuck history`.

## When not to use it

- You need semantic similarity or multi-turn intent tracking. This skill uses lexical Jaccard similarity only. Use a richer evaluation tool.
- You need cross-session coherence checks.

## Quick start

This skill has no short slash command, so the agent usually loads it for you. In Claude Code you can still type `/project-toolkit:stuck-detection`. The agent loads it when your request matches. In the ai-agents repository, [`ai-agents-debugging-playbook`](ai-agents-debugging-playbook.md) triggers it after three read-only commands find no cause. To ask for it by name, say:

```text
Use the stuck-detection skill to check whether the last ten tool calls in events.json are a failure loop.
```

The skill runs `check-failures` on the events. If it finds a loop, it returns a `nudge` that the agent injects into its next turn.

## What you get

`check` returns:

```json
{
  "stuck": true,
  "signature": "deploy,error,pipeline,retry,timeout",
  "similar_count": 3,
  "nudge": "<stuck-detection>\nSELF-REFLECTION: Loop detected.\n..."
}
```

`check-failures` adds `events_total`, `events_checked`, `counts` (`tool_error`, `permission_denial`, `failed_retry`, `unfingerprinted`), `signals`, and an `untrusted` list. Two signals exist:

| Signal | Trips when |
| --- | --- |
| `failure-repeat` | One failure fingerprint appears `--repeat` times (default 3) in the last `--window` events (default 20). |
| `edit-churn` | One file's edit cycles end in the same failing check `--churn` times (default 3). |

The nudge is internal control text wrapped in `<stuck-detection>` tags. Do not show it to the end user. It tells the agent to stop retrying, restate the cause, change approach, and never work around a permission or user denial. It carries only signal names, counts, and allowlisted tool names, never error text, inputs, or file paths.

`signals[].fingerprint` and `signals[].target` come from tool output and file names and can be attacker-controlled. Treat them as data. Never paste them into a nudge or system prompt. The signals are advisory. The skill never stops a turn.

## Advanced use

Run the CLI from the root of a checkout of this repository:

```bash
uv run python .claude/skills/stuck-detection/stuck_detection.py check-failures --events events.json --repeat 4 --window 20
```

| Command | Purpose |
| --- | --- |
| `check [text]` | Score text against recent history. Reads stdin when no text is given. |
| `status` | Show current history state. |
| `reset` | Clear history after a confirmed topic change. |
| `extract [text]` | Extract the topic signature only, for debugging. |
| `check-failures` | Score tool events for a failure loop. Takes `--events` (file, default stdin), `--repeat`, `--churn`, `--window`. |

The global `--history` flag overrides the history file path. Both `check` and `check-failures` exit 0 whether or not they find a loop. Invalid arguments or event input exit 2, with a `stuck-detection:` message on stderr and nothing on stdout.

For `check`, the skill takes the top words of a response, sorts them into a signature, and stores it with a UTC timestamp. It compares the signature to recent entries using Jaccard similarity and trips when enough consecutive entries are similar. Defaults: 10 entries kept, 3 similar turns to trip, a similarity cutoff of 0.6, and responses under 50 characters skipped.

History path order: `--history`, then the `STUCK_DETECTION_HISTORY` environment variable, then a per-session file when `STUCK_DETECTION_SESSION` is set, then `$XDG_STATE_HOME/claude-stuck-detection/history.json`, then `~/.local/state/claude-stuck-detection/history.json`. Use the session variable when you run concurrent sessions.

`check-failures` events are a JSON array of at most 10,000 events and 8 MiB. Each event needs `tool` (string) and `ok` (boolean). Optional strings are `error`, `input`, and `target`. An optional boolean `check` marks the event as a verifying check. Pass redacted `error` text, because the first line is echoed in `signals`. A success whose `tool` and `input` match an earlier failure clears that failure's counts, so pass `input` to let a fix clear the signals. Only a check ends a pending edit cycle: a passing test run does, a successful `ls` does not.

The `--repeat`, `--churn`, and `--window` defaults are provisional and not yet calibrated.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`ai-agents-debugging-playbook`](ai-agents-debugging-playbook.md): triggers this skill in the ai-agents repository.
- [`orchestrator`](../agents/orchestrator.md): the agent this guard protects from token-burning loops.
- Source: [`SKILL.md`](../../src/claude/skills/stuck-detection/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)

# observability

Queries and analyzes agent JSONL event logs. You use it to find errors and slow tool calls, trace why an agent chose an approach, and summarize sessions. It also holds the contract for which operational events new code must emit.

## When to use it

- You are debugging why an agent chose a particular tool or approach.
- You are looking for slow tool calls that degrade agent performance.
- You are analyzing error patterns across agent sessions.
- You are comparing tool usage across sessions or agents.
- You are tracing decisions from the orchestrator through sub-agents.
- You are deciding which operational events new code must emit, and which it must leave out.
- You say `query agent logs`, `find slow tool calls`, `show agent errors`, `what to log`, `summarize session performance`, or `analyze tool usage`.

## When not to use it

- You are checking a single known event in a small log, or the log has fewer than 10 events: read the log file directly.
- You want agent metrics rather than event logs: use [`metrics`](metrics.md) instead.

## Quick start

This skill has no short slash command, so the agent usually loads it for you. In Claude Code you can still type `/project-toolkit:observability`. The agent loads it when your request matches. To ask for it by name, say:

```text
Use the observability skill to find tool calls slower than 500 ms in .project-toolkit/logs/sess-001.jsonl and summarize the errors.
```

The agent runs `query_logs.py` with the filters that match, then reports the patterns, errors, or slow calls it finds.

## What you get

`query_logs.py` prints matching events in one of four formats: `table`, `json`, `summary-sessions`, or `summary-tools`.

| Exit code | Meaning |
| --- | --- |
| `0` | Query completed and results were output, or the scenario is compliant. |
| `1` | File not found or invalid arguments (query), or the scenario is non-compliant (check). |
| `2` | Invalid JSONL format (query), malformed scenario (check), or a launcher failure (a `ptk_run:` line on stderr and no output). |

## Advanced use

### Event schema

Logs are JSONL, one JSON object per line. The full JSON Schema is in `schema.json` next to the skill.

| Event type | Purpose | Key fields |
| --- | --- | --- |
| `session_start` | Agent invocation begins. | `agent`, `session_id` |
| `session_end` | Agent invocation completes. | `agent`, `session_id` |
| `tool_call` | Tool invocation with timing. | `tool.name`, `tool.duration_ms`, `tool.success` |
| `decision` | Reasoning captured alongside the action. | `decision.action`, `decision.reasoning` |
| `metric` | Numeric measurement. | `metric.name`, `metric.value`, `metric.unit` |
| `error` | Error occurrence. | `error.message`, `error.category`, `error.recoverable` |

### Query logs

Run from the root of a checkout of this repository:

```bash
uv run python .claude/skills/observability/scripts/query_logs.py --help
```

The script takes one positional argument, the path to a JSONL log file, plus these flags:

| Flag | Meaning |
| --- | --- |
| `--event-type` | Filter by event type. |
| `--session-id` | Filter by session ID. |
| `--agent` | Filter by agent name. |
| `--level` | Filter by log level. |
| `--tool` | Filter by tool name. |
| `--since`, `--until` | Keep events after or before an ISO timestamp. |
| `--errors-only` | Show only error events. |
| `--slow` | Show tool calls slower than a threshold in milliseconds. |
| `--output` | One of `json`, `table`, `summary-sessions`, `summary-tools`. |

Examples:

```bash
uv run python .claude/skills/observability/scripts/query_logs.py .project-toolkit/logs/sess-001.jsonl --errors-only
uv run python .claude/skills/observability/scripts/query_logs.py .project-toolkit/logs/sess-001.jsonl --slow 500
uv run python .claude/skills/observability/scripts/query_logs.py .project-toolkit/logs/sess-001.jsonl --output summary-sessions
uv run python .claude/skills/observability/scripts/query_logs.py .project-toolkit/logs/sess-001.jsonl --event-type tool_call --output json
```

### Check an event-logging scenario

`check_event_logging.py` checks a scenario against the event-logging contract. It takes a scenario JSON file, or `-` to read stdin.

```bash
uv run python .claude/skills/observability/scripts/check_event_logging.py --help
```

```bash
uv run python .claude/skills/observability/scripts/check_event_logging.py scenario.json
```

It exits `0` for a compliant scenario, `1` when a required event is missing or prohibited content is present, and `2` for a malformed scenario or bad arguments.

### Habits that avoid wasted work

- Use `query_logs.py` with filters instead of reading raw JSONL by hand.
- Filter by `--event-type decision` so you keep the reasoning behind agent actions.
- Check for slow calls with `--slow`, not only errors.
- Use `--output summary-sessions` so events have session context.

### Chaining

In the `ai-agents` repository, [`ai-agents-debugging-playbook`](ai-agents-debugging-playbook.md) points here to query agent JSONL event logs.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`metrics`](metrics.md): agent metrics, a companion to the event logs.
- [`ai-agents-debugging-playbook`](ai-agents-debugging-playbook.md): points here for log queries.
- Source: [`SKILL.md`](../../src/claude/skills/observability/SKILL.md)
- Reference: [Event-logging contract](../../src/claude/skills/observability/references/event-logging-contract.md)
- Reference: [Three pillars](../../src/claude/skills/observability/references/three-pillars-reference.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)

---
name: observability
version: 1.0.0
model: claude-haiku-4-5
description: Query and analyze agent JSONL event logs for debugging, performance analysis, and decision tracing. Use when investigating agent behavior, finding slow tool calls, tracing decisions, or analyzing session performance.
license: MIT
---

# Agent Observability Skill

Query structured JSONL event logs to understand agent behavior, debug failures, and analyze performance.

## Triggers

| Trigger Phrase | Operation |
|----------------|-----------|
| `query agent logs` | Run query_logs.py with filters |
| `find slow tool calls` | Run with --slow threshold |
| `show agent errors` | Run with --errors-only |
| `summarize session performance` | Run with --output summary-sessions |
| `analyze tool usage` | Run with --output summary-tools |

## When to Use

Use this skill when:

- Debugging why an agent chose a particular tool or approach
- Finding slow tool calls that degrade agent performance
- Analyzing error patterns across agent sessions
- Comparing tool usage across sessions or agents
- Tracing decisions from orchestrator through sub-agents

Use direct log file inspection instead when:

- Checking a single known event in a small log
- The log file has fewer than 10 events

## Event Schema

Logs use JSONL format (one JSON object per line). See `schema.json` for the full JSON Schema.

### Event Types

| Type | Purpose | Key Fields |
|------|---------|------------|
| session_start | Agent invocation begins | agent, session_id |
| session_end | Agent invocation completes | agent, session_id |
| tool_call | Tool invocation with timing | tool.name, tool.duration_ms, tool.success |
| decision | Reasoning captured alongside action | decision.action, decision.reasoning |
| metric | Numeric measurement | metric.name, metric.value, metric.unit |
| error | Error occurrence | error.message, error.category, error.recoverable |

### Example Events

```jsonl
{"timestamp":"2026-03-30T10:00:00Z","event_type":"session_start","session_id":"sess-001","agent":"implementer","message":"Session started"}
{"timestamp":"2026-03-30T10:00:01Z","event_type":"tool_call","session_id":"sess-001","agent":"implementer","level":"INFO","tool":{"name":"Read","duration_ms":45,"success":true,"input_summary":"src/main.py"},"message":"Read source file"}
{"timestamp":"2026-03-30T10:00:02Z","event_type":"decision","session_id":"sess-001","agent":"implementer","level":"INFO","decision":{"action":"Edit existing function","reasoning":"Function exists, modifying is safer than rewriting","alternatives_considered":["Rewrite from scratch","Create wrapper"]}}
{"timestamp":"2026-03-30T10:00:10Z","event_type":"error","session_id":"sess-001","agent":"implementer","level":"ERROR","error":{"message":"Test failed: assertion error in test_parse","category":"test_failure","recoverable":true}}
```

## Log File Location

Agent event logs are stored at:

```text
.agents/
  logs/
    {session-id}.jsonl    # Per-session event log
```

## Process

1. Identify the log file to query (by session ID or date)
2. Run query_logs.py with appropriate filters
3. Review output for patterns, errors, or performance issues
4. Use summary modes for high-level analysis across many events

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Reading raw JSONL manually for large logs | Slow, error-prone | Use query_logs.py with filters |
| Ignoring decision events | Loses the "why" behind agent actions | Filter by --event-type decision |
| Checking only errors | Misses slow degradation patterns | Use --slow to find latency issues |
| Analyzing without session context | Events lack meaning without grouping | Use --output summary-sessions |

## Available Scripts

| Script | Platform | Usage |
|--------|----------|-------|
| `scripts/query_logs.py` | Python 3.8+ | Cross-platform |

## Quick Start

```bash
# Show all events in a session log
python .claude/skills/observability/scripts/query_logs.py .agents/logs/sess-001.jsonl

# Find errors only
python .claude/skills/observability/scripts/query_logs.py .agents/logs/sess-001.jsonl --errors-only

# Find tool calls slower than 500ms
python .claude/skills/observability/scripts/query_logs.py .agents/logs/sess-001.jsonl --slow 500

# Filter by agent
python .claude/skills/observability/scripts/query_logs.py .agents/logs/sess-001.jsonl --agent implementer

# Session summary as JSON
python .claude/skills/observability/scripts/query_logs.py .agents/logs/sess-001.jsonl --output summary-sessions

# Tool usage summary
python .claude/skills/observability/scripts/query_logs.py .agents/logs/sess-001.jsonl --output summary-tools

# Filter by time range
python .claude/skills/observability/scripts/query_logs.py .agents/logs/sess-001.jsonl \
    --since 2026-03-30T10:00:00Z --until 2026-03-30T11:00:00Z

# JSON output for automation
python .claude/skills/observability/scripts/query_logs.py .agents/logs/sess-001.jsonl \
    --output json --event-type tool_call
```

## Verification

After execution:

- [ ] Script exits with code 0
- [ ] Output format matches requested mode (table, json, summary-sessions, summary-tools)
- [ ] Filters reduce event count as expected
- [ ] Session summaries include all sessions present in the log

## References

Domain knowledge for observability analysis:

| File | Content |
|------|---------|
| [three-pillars-reference.md](references/three-pillars-reference.md) | Logs, metrics, traces definitions, correlation matrix, OpenTelemetry |
| [prometheus-recording-rules.md](references/prometheus-recording-rules.md) | Recording rule patterns, CPU throttling, disk I/O, PSI, TCP metrics |
| [otel-migration-reference.md](references/otel-migration-reference.md) | IFx to OTel migration phases, instrumentation best practices, standard metrics |

## Related Documents

- [Event Schema](schema.json)
- [Agent Metrics Skill](../metrics/SKILL.md)
- [Issue #1301](https://github.com/rjmurillo/ai-agents/issues/1301)

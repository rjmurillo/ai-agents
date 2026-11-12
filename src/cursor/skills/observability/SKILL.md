---
name: observability
description: Use when you say `query agent logs`, `find slow tool calls`, `show agent errors`, or `what to log`. Query and analyze agent JSONL event logs for debugging, performance analysis, and decision tracing.
metadata:
  capability:
    kind: reusable-primitive
    owns: [operational-event-selection]
    status: active
  routing:
    role: conditional-adjunct
    invoker: ai-agents-debugging-playbook
    trigger: in the ai-agents repository, ai-agents-debugging-playbook points here to query agent JSONL event logs
    user-facing: false
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
- Deciding which operational events new code must emit, and which it must leave out (read the event-logging contract below)

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

## Scripts

| Script | Platform | Usage |
|--------|----------|-------|
| `scripts/query_logs.py` | Python 3.8+ | Cross-platform |
| `check_event_logging.py` | Python 3.8+ | Check a scenario against the event-logging contract |

| Exit Code | Meaning |
|-----------|---------|
| 0 | Query completed and results output (query) or scenario compliant (check) |
| 1 | File not found or invalid arguments (query) or scenario non-compliant (check) |
| 2 | Invalid JSONL format (query) or malformed scenario (check) |

## Quick Start

```bash
# Show all events in a session log
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/observability/scripts/query_logs.py .project-toolkit/logs/sess-001.jsonl; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )

# Check an emission scenario against the event-logging contract
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/observability/scripts/check_event_logging.py scenario.json; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )

# Find errors only
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/observability/scripts/query_logs.py .project-toolkit/logs/sess-001.jsonl --errors-only; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )

# Find tool calls slower than 500ms
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/observability/scripts/query_logs.py .project-toolkit/logs/sess-001.jsonl --slow 500; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )

# Filter by agent
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/observability/scripts/query_logs.py .project-toolkit/logs/sess-001.jsonl --agent implementer; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )

# Session summary as JSON
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/observability/scripts/query_logs.py .project-toolkit/logs/sess-001.jsonl --output summary-sessions; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )

# Tool usage summary
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/observability/scripts/query_logs.py .project-toolkit/logs/sess-001.jsonl --output summary-tools; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )

# Filter by time range
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/observability/scripts/query_logs.py .project-toolkit/logs/sess-001.jsonl --since 2026-03-30T10:00:00Z --until 2026-03-30T11:00:00Z; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )

# JSON output for automation
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/observability/scripts/query_logs.py .project-toolkit/logs/sess-001.jsonl --output json --event-type tool_call; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )
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
| [event-logging-contract.md](references/event-logging-contract.md) | Canonical contract for which operational events code emits and omits: decision test, MUST and MUST NOT tables, log vs metric vs trace, worked example |
| [three-pillars-reference.md](references/three-pillars-reference.md) | Logs, metrics, traces definitions, correlation matrix, OpenTelemetry |
| [prometheus-recording-rules.md](references/prometheus-recording-rules.md) | Recording rule patterns, CPU throttling, disk I/O, PSI, TCP metrics |
| [otel-migration-reference.md](references/otel-migration-reference.md) | IFx to OTel migration phases, instrumentation best practices, standard metrics |

## Related Documents

- [Event Schema](schema.json)
- [Agent Metrics Skill](../metrics/SKILL.md)

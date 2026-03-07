---
name: observability
version: 1.0.0
model: claude-haiku-4-5
description: Query structured JSON logs and metrics files for agent-legible observability.
  Use when agents need to search logs by level, service, time range, or pattern,
  or read metrics snapshots. MVP implementation using local files, no external stack.
license: MIT
---

# Agent Observability Skill

## Purpose

Query structured JSON log files and metrics snapshots so agents can answer questions about service behavior, errors, and performance without external observability infrastructure.

## Triggers

| Trigger Phrase | Operation |
|----------------|-----------|
| `find all ERROR logs` | query_logs.py --level ERROR |
| `search logs for timeout` | query_logs.py --pattern "timeout" |
| `check service metrics` | query_logs.py --metrics |
| `summarize recent logs` | query_logs.py --summary |
| `filter logs by service` | query_logs.py --service <name> |

---

## When to Use

Use this skill when:

- Searching or filtering structured JSON log files
- Reading metrics snapshots (JSON format)
- Answering questions about service errors, latency, or throughput
- Producing log summaries by level

Use direct file reads instead when:

- Log files are not in JSON-lines format
- You need to inspect a single known log entry
- The file is small enough to read entirely

---

## Log Format

Log files must use JSON-lines format (one JSON object per line):

```json
{"timestamp": "2026-03-07T01:15:00Z", "level": "ERROR", "service": "api", "message": "Connection timeout after 5s"}
{"timestamp": "2026-03-07T01:15:01Z", "level": "INFO", "service": "api", "message": "Retry succeeded"}
```

Supported timestamp fields: `timestamp`, `ts`, `time`.
Supported message fields: `message`, `msg`.

## Metrics Format

Metrics files are plain JSON objects:

```json
{
  "startup_time_ms": 450,
  "error_rate": 0.02,
  "active_connections": 12,
  "memory_mb": 256
}
```

---

## Process

1. Identify the log or metrics file path
2. Run `query_logs.py` with appropriate filters
3. Parse the JSON output for your analysis

### Examples

```bash
# Find ERROR logs from a specific service
python3 .claude/skills/observability/query_logs.py logs/app.jsonl --level ERROR --service api

# Search for timeout messages in the last hour
python3 .claude/skills/observability/query_logs.py logs/app.jsonl --pattern "timeout" --since "2026-03-07T00:00:00Z"

# Get a level-count summary
python3 .claude/skills/observability/query_logs.py logs/app.jsonl --summary

# Read a metrics snapshot
python3 .claude/skills/observability/query_logs.py metrics/snapshot.json --metrics
```

---

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Reading entire log files with Read tool | Wastes context window on irrelevant entries | Use query_logs.py with filters |
| Grepping unstructured logs | Fragile parsing, no timestamp filtering | Ensure logs are JSON-lines format |
| Hardcoding file paths | Breaks across environments | Accept path as argument |

---

## CLI Reference

```text
query_logs.py <path> [options]

Arguments:
  path                    Path to JSON-lines log file or JSON metrics file

Options:
  --level LEVEL           Filter: DEBUG, INFO, WARN, WARNING, ERROR, CRITICAL
  --service SERVICE       Filter by service name
  --pattern REGEX         Regex match against message field
  --since TIMESTAMP       ISO 8601 lower bound (inclusive)
  --until TIMESTAMP       ISO 8601 upper bound (inclusive)
  --limit N               Max entries to return (default: 100)
  --metrics               Treat file as JSON metrics snapshot
  --summary               Print level-count summary instead of entries
```

Exit codes: 0 = success, 1 = invalid args/file not found, 2 = invalid format.

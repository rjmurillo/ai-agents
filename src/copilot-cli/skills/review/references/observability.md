---
name: observability
role: observability
version: 1.0.0
description: PR review focused on logs, metrics, and traces for new code paths and agent or hook changes
---

# Observability Review Task

You are reviewing a pull request for observability: can an operator understand what the new code does in production from its external outputs?

## Context Mode Enforcement (REQUIRED)

The CI harness prepends a `CONTEXT_MODE: [full|summary|partial]` header to the
context it sends you. Read that header before you decide a verdict. It tells you
how much of the diff you actually received.

- `full`: the complete diff is present. `PASS`, `WARN`, and `CRITICAL_FAIL` are
  all permitted on the merits.
- `summary`: only a file list or stat-only summary is present (the PR exceeded
  the diff-size limit). You did not see the line-level changes.
- `partial`: only a bounded slice of the diff is present (for example, the first
  N lines). You did not see the rest.

When `CONTEXT_MODE` is not `full`, you MUST NOT emit `PASS`. A PASS asserts
evidence you do not have. Emit `WARN` (or a higher-severity verdict if the
available metadata already shows a problem), state that context was
`summary` or `partial`, and name the specific evidence you would need to clear
the PR. Treat a missing or unrecognized `CONTEXT_MODE` value as not `full`.

This is a manipulation-resistance control: an adversary can craft a PR that
trips summary mode to hide a change behind a stat-only context. Forbidding PASS
keeps that change from passing on absent evidence. See
`.agents/governance/AI-REVIEW-MODEL-POLICY.md` ("CONTEXT_MODE Header (REQUIRED)").

## Grounding Rules

- Do NOT claim software versions are "beta", "unstable", or "unreleased" based on training data. Your training data has a cutoff and may be outdated.
- Do NOT claim tools (ruff, mypy, pytest, etc.) lack support for a version unless you have concrete evidence from the diff itself.
- For dependency update PRs: evaluate the diff for internal consistency, not external ecosystem assumptions. If CI tests pass, the tooling works.
- Base findings on what the code shows, not on recalled release schedules.

## When This Axis Applies

Apply the focus areas below when the diff adds a new code path, a new agent step, or a new hook, or when it changes an existing path's failure or branching behavior. Documentation-only and pure-refactor changes that preserve observable behavior do not need an observability review; record PASS and move on.

## Reference Material

Ground findings in the project's observability artifacts. All paths are under `.claude/` and ship with vendored installs:

- `observability` skill: invoke on agent and hook diffs. It queries and analyzes the agent JSONL event logs for debugging, performance analysis, and decision tracing, so you can check whether a new path emits the events that skill would need.
- `.claude/skills/observability/references/three-pillars-reference.md`: the three pillars (logs, metrics, traces) reference. Use it to check that a new path is observable across the relevant pillars, not just one. Logs are timestamped discrete events, metrics are aggregated numeric measurements, and traces follow a request across boundaries.
- `.claude/skills/observability/references/otel-semantic-conventions.md`: the OTel semantic-conventions reference. Use it to check that new telemetry uses standard attribute names and units (for example `http.request.method`, a duration metric with a unit) instead of inventing per-path names that break dashboard and alert portability.

## Analysis Focus Areas

### 1. Logs (Pillar 1)

- Does the new path emit structured logs (JSON) with consistent field names?
- Is a correlation or trace id included so the entry can be tied to a request?
- Are log levels appropriate (ERROR, WARN, INFO, DEBUG)?
- Is sensitive data (PII, credentials, tokens) kept out of the logs?

### 2. Metrics (Pillar 2)

- Are the right signals counted: rate, errors, duration for a service path; utilization, saturation, errors for a resource?
- Does a new failure mode increment an error counter an alert can fire on?
- Are labels and dimensions meaningful and bounded (no high-cardinality identifiers as labels)?

### 3. Traces (Pillar 3)

- Is trace context propagated across the boundaries the new path crosses?
- Does a new span carry enough business context to explain what it did?
- Can a trace be connected back to logs via a shared trace id?

### 4. Agent and Hook Event Coverage

- Does a new agent step or hook emit the JSONL events the `observability` skill consumes (decisions, tool calls, timings)?
- Can a slow tool call or a stalled turn be diagnosed from the events emitted, or is the path silent on failure?

### 5. Signal Without Noise

- Does the change log a request body or full payload on a hot path (cookie-monster logging that fills the disk)?
- Is the new telemetry actionable, or does it add volume an operator cannot use?

## Output Requirements

Provide your analysis in this format:

### Observability Assessment

| Pillar | Coverage | Notes |
|--------|----------|-------|
| Logs | None/Partial/Full | |
| Metrics | None/Partial/Full | |
| Traces | None/Partial/Full | |
| Agent/Hook Events | None/Partial/Full | |

**Overall Observability Score**: X/5

### Findings

| Severity | Category | Finding | Location | Recommendation |
|----------|----------|---------|----------|----------------|
| Critical/High/Medium/Low | [category] | [description] | [file:line] | [fix] |

### Recommendations

1. [Specific observability improvements; cite the three-pillars reference or the `observability` skill where relevant]

### Verdict

Choose ONE verdict:

- `VERDICT: PASS` - New paths are observable enough to operate
- `VERDICT: WARN` - Observability gaps that should be addressed
- `VERDICT: CRITICAL_FAIL` - A failure path is silent or leaks sensitive data into telemetry

```text
VERDICT: [PASS|WARN|CRITICAL_FAIL]
MESSAGE: [Brief explanation]
```

## Critical Failure Triggers

Automatically use `CRITICAL_FAIL` if you find:

- A new failure or error path that emits no log, metric, or trace (silent failure)
- Sensitive data (PII, credentials, tokens) written to logs, traces, or metric labels
- A new agent step or hook that breaks an existing trace by dropping context propagation
- Request bodies or full payloads logged on a hot path with no redaction

## Structured JSON Output

After your human-readable analysis, emit a fenced JSON block matching the inline schema below (a JSON Schema for this output also lives at `.agents/schemas/pr-quality-gate-output.schema.json` in projects that ship it; vendored installs do not):

```json
{
  "verdict": "PASS|WARN|CRITICAL_FAIL",
  "message": "One sentence summary",
  "agent": "observability",
  "timestamp": "ISO 8601",
  "findings": [
    {
      "severity": "critical|high|medium|low",
      "category": "logs|metrics|traces|agent-events|noise|sensitive-data",
      "description": "What was found",
      "location": "file:line",
      "recommendation": "Suggested fix"
    }
  ]
}
```

## Output Schema

Each finding MUST be reported with these structured fields:

- **severity**: one of `critical`, `high`, `medium`, `low` (matches the JSON schema field used in the body section above; treat `critical` as a CRITICAL_FAIL trigger and `high` as a WARN trigger). Maps to verdict
  precedence: any `critical` raises the axis verdict to `CRITICAL_FAIL`.
- **category**: short keyword identifying the failure class, drawn from the
  axis `category` enum in the JSON schema above (e.g. `logs`, `metrics`,
  `traces`). Used for clustering.
- **location**: `file:line` (or `file:line-range`). Required for every finding.
- **recommendation**: one-sentence imperative fix the author can act on.
Top-level (NOT per-finding; the schema rejects `verdict` inside
`findings` items; `additionalProperties: false` is set on the finding
object):

- **verdict**: one of `PASS`, `WARN`, `CRITICAL_FAIL`. Choose one of these
  three explicitly; do NOT emit `UNKNOWN` yourself. `UNKNOWN` is reserved
  for `/review`'s parser when an axis output cannot be parsed
  (`extract_verdict` returns `UNKNOWN` on no match); it is never an authored
  verdict. The axis-level verdict is the highest-severity outcome across the
  findings list (any `critical` severity -> CRITICAL_FAIL; any `high` ->
  WARN; otherwise PASS).

The response MUST contain a final line matching the regex
`(?m)^\s*(?i:(?:Final\s+)?Verdict):\s*\[?(PASS|WARN|CRITICAL_FAIL|REJECTED|FAIL|NEEDS_REVIEW|NON_COMPLIANT|COMPLIANT|PARTIAL|UNKNOWN)(?![|A-Z_])\]?` (label is case-insensitive; tokens are case-sensitive uppercase).
This line is parsed by `extract_verdict` in
`.claude/lib/ai_review_common/verdict.py` and consumed by `merge_verdicts`
when `/review` aggregates across all axes.

Refs REQ-008-01, REQ-008-05 (issue #1934).

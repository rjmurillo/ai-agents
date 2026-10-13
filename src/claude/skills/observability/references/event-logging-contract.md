---
source: issue #5413
created: 2026-10-12
review-by: 2027-01-12
---

# Operational Event-Logging Contract

The producer-side contract for this repository. The rest of the observability
skill is consumer-side (query and review emitted telemetry). This file is the
one canonical statement of which operational events production-style code
emits and which it leaves out. Consumers reference this file. They do not copy
the policy.

## Governing Principle

> Emit the minimum telemetry needed to reconstruct externally meaningful state
> transitions and failure decisions without reproducing the incident.

Diagnostic sufficiency is the goal, not log volume. If an event does not help
an operator localize a failure or confirm a state change from outside the
process, it is noise.

> Log decisions and transitions an operator must reconstruct. Do not log
> implementation noise.

## Decision Test

```text
Would an operator need this fact to explain what happened,
why it happened, or how much was affected?
        |
     no | yes
     |  v
     | Is the fact already captured reliably by a lower layer,
     | metric, trace, or canonical event?
     |        |         |
     |       yes        no
     |        |         |
     |        v         v
     |   reference/   emit one
     |    consume     structured event
     v
  no new log
```

Prefer structured events (key-value or JSON fields) where the repository
convention supports them. This contract names no logging SDK and no telemetry
backend.

## MUST Emit

A code path MUST emit an operational event for each row that applies to it.

| # | Trigger | Required event(s) | Load-bearing fields |
|---|---------|-------------------|---------------------|
| 1 | Job or process where duration or outcome matters | start + completion | id, count, duration, result |
| 2 | Externally meaningful state transition | one transition event | id, from, to |
| 3 | External dependency call | one outcome event | operation identity, status or outcome |
| 4 | Retry path | one event per failed attempt + one on exhaustion; the condition that triggers backoff | attempt, cause, next delay |
| 5 | Quota or rate-limit hit | one rate-limit event | limit, scope |
| 6 | Skip that changes observable behavior | one skip event | reason |
| 7 | Error that is not swallowed | one error event | operation context that localizes the failure |
| 8 | Diagnosis needs it | ids, counts, durations, branch or decision outcomes | the value being diagnosed |
| 9 | Cancellation or timeout that differs from ordinary failure | one cancellation or timeout event | outcome kind |

## MUST NOT Emit

| # | Prohibited | Why |
|---|------------|-----|
| 1 | Every function entry and exit | Volume with no operational signal |
| 2 | The same transition at every layer | One transition, one event. Pick the owning layer |
| 3 | Secrets, tokens, credentials, unnecessary PII | Leak. Redact or omit |
| 4 | Entire request or response bodies by default | Cost and leak. Log identity and status, not payload |
| 5 | High-cardinality fields with no operational justification | Cardinality blowup, unusable dashboards |
| 6 | Logs where a metric or trace is the better signal | Wrong pillar. See below |

## Pure and Internal Helpers Emit Nothing

A pure or internal helper (deterministic, no external side effect, no state
transition an operator cares about) legitimately requires no operational
event. Absence of logging is the correct state, not a gap. Do not flag it.

The same holds when a lower layer already captures the signal. A wrapper around
an HTTP client that already logs every call emits no second outcome event.

## Which Pillar Is the Evidence

| Need | Pillar | Example |
|------|--------|---------|
| What did this one operation decide, and why | Log | `skipped sync: manifest missing` |
| A rate, count, or duration trend to alert or graph on | Metric | retry rate, p99 latency, rate-limit count |
| Where time went across a boundary in one request | Trace | slow downstream call inside a request span |

"How often" or "how slow across all requests" is a metric, not a log line per
request. "What did this operation decide" is a log. One retry loop can need all
three: a log line when retries are exhausted, a counter for retry rate, a span
for the slow call. Pick the pillar per question and do not substitute one for
another. The three-pillars-reference.md file in this directory defines each
pillar.

## Worked Example

Before, a sync job that is hard to diagnose and noisy:

```text
INFO enter sync()
INFO calling GET /manifest
INFO GET /manifest returned
INFO enter parse()
INFO exit parse()
INFO exit sync()
```

After, three events reconstruct the run (rows 1, 3, 6 of the MUST Emit table):

```text
INFO sync.start job_id=j42
INFO sync.skip job_id=j42 reason=manifest_unchanged etag=abc123
INFO sync.done job_id=j42 count=0 duration_ms=214 result=skipped
```

The HTTP client layer already records the `GET /manifest` outcome, so the job
adds no second call event. `parse()` is a pure helper and emits nothing. The
request body and the auth header never appear.

## Reference, Do Not Copy

Other skills and rules point to this file. They do not restate the policy. The
review skill's observability axis (`references/observability.md`) and the
code-quality rule point here for producer-side emission. Capability metadata
records the edge: this skill owns `operational-event-selection`, and a consumer
declares `depends-on: [operational-event-selection]`.

## Executable Guard

The skill's script `check_event_logging.py` encodes the two tables above as a
deterministic decision procedure. It reads a structured scenario (what the code
does, what it emits) and reports missing required events and prohibited
content. The test module `test_event_logging_contract.py` runs the nine
reference scenarios, including the pure-helper case where no logging is
correct and the controls that prove a missing load-bearing event is detected.
It also fails when a table row here has no counterpart in the checker.

Stricter/looser/different than canonical: the checker is different, not
stricter. Row 8 of MUST Emit and row 6 of MUST NOT Emit are judgment calls it does
not adjudicate. It reads a described scenario, not source code, so it cannot
infer intent.

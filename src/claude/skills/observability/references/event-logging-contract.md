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

A code path MUST emit an operational event for each row that applies to it, unless a lower layer, metric, trace, or canonical event already captures it reliably (see Decision Test).

| # | Trigger | Required event(s) | Load-bearing fields |
|---|---------|-------------------|---------------------|
| 1 | Job or process where duration or outcome matters | start + completion | id, count, duration, result |
| 2 | Externally meaningful state transition | one transition event | id, from, to |
| 3 | External dependency call | one outcome event | `operation`, `status` |
| 4 | Retry path | one event per failed attempt + one on exhaustion | attempt, cause (the condition that triggered backoff), next delay |
| 5 | Quota or rate-limit hit | one rate-limit event | limit, scope |
| 6 | Skip that changes observable behavior | one skip event | reason |
| 7 | Error that is not swallowed | one error event | operation name, input identifiers, request or correlation id |
| 8 | Diagnosis needs a fact rows 1 to 7 and 9 do not carry | no separate event: add the fields to the events from rows 1 to 7 and 9 | ids, counts, durations, branch or decision outcomes |
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

After, three events reconstruct the run (rows 1 and 6 of the MUST Emit table; row 3 is covered by the HTTP client layer):

```text
INFO sync.start job_id=j42
INFO sync.skip job_id=j42 reason=manifest_unchanged etag=abc123
INFO sync.done job_id=j42 count=0 duration=214ms result=skipped
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

The skill's script `check_event_logging.py` is a deterministic decision
procedure for the mechanical part of the two tables above. It reads a
structured scenario (what the code does, what it emits) and reports missing
required events, missing load-bearing fields, and prohibited content.

Field checks cover only these literal keys: row 1 `count`, `duration`,
`result` on `job_completion`; row 3 `operation`, `status`; row 4 `attempt`
on `retry_attempt`; row 5 `limit`, `scope`; row 6 `reason`; row 7
`operation`. The table field names are categories. The checker does not check
row 1 `id`, row 2 `id`/`from`/`to`, row 4 `cause`/`next delay`, or row 9
`outcome kind`, and row 9 is satisfied only by an event named `cancellation`.
Row 8 of MUST Emit and row 6 of MUST NOT Emit are judgment calls it does not
adjudicate. It reads a described scenario, not source code, so it cannot
infer intent.

```bash
python3 .claude/skills/observability/scripts/check_event_logging.py scenario.json
```

```json
{
  "behavior": {"job_lifecycle": true, "skip_changes_behavior": true},
  "emits": [
    {"event": "job_start", "fields": {}},
    {"event": "skip", "fields": {"reason": "manifest_unchanged"}},
    {"event": "job_completion", "fields": {"count": 0, "duration": 214, "result": "skipped"}}
  ]
}
```

Exit 0 is compliant, 1 is non-compliant, 2 is a malformed scenario. Behavior
flags: `job_lifecycle`, `state_transition`, `external_call`, `retry`,
`rate_limited`, `skip_changes_behavior`, `error_not_swallowed`,
`cancellation_differs`.

The test module `test_event_logging_contract.py` runs the nine #5413 fixtures
(job, external call, retry, skip, error, auth, pure helper, lower layer,
cardinality). Rate limit and cancellation have no fixture. It also fails when
a MUST Emit or MUST NOT Emit row is added or removed without a checker
counterpart. Rewording a row passes.

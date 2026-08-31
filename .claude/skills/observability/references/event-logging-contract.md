---
source: issue #5413
created: 2026-08-31
review-by: 2026-11-30
---

# Operational Event-Logging Contract

The producer-side contract for this repository. The rest of the observability
skill is consumer-side (query and review emitted telemetry); this file is the
one canonical statement of what production-style code MUST emit and MUST NOT
emit. Consumers reference this file, they do not copy the policy.

## Governing Principle

> Emit the minimum telemetry needed to reconstruct externally meaningful state
> transitions and failure decisions without reproducing the incident.

Minimum, not maximum. If an event does not help an operator localize a failure
or confirm a state change from outside the process, it is noise.

## MUST Emit

A code path MUST emit an operational event for each row that applies to it.

| # | Trigger | Required event(s) | Load-bearing fields |
|---|---------|-------------------|---------------------|
| 1 | Job/process where duration or outcome matters | start + completion | id, count, duration, result |
| 2 | Externally meaningful state transition | one transition event | id, from, to |
| 3 | External dependency call | one outcome event | operation identity, status/outcome |
| 4 | Retry path | retry-attempt + retry-exhaustion; backoff trigger | attempt, cause, next-delay |
| 5 | Quota or rate-limit hit | rate-limit event | limit, scope |
| 6 | Skip that changes observable behavior | skip event | reason |
| 7 | Error not swallowed | error event | operation context to localize |
| 8 | Diagnosis needs it | ids, counts, durations, branch/decision outcomes | the value diagnosed |
| 9 | Cancellation/timeout differing from ordinary failure | cancellation/timeout event | outcome kind |

## MUST NOT Emit

| # | Prohibited | Why |
|---|------------|-----|
| 1 | Every function entry/exit | Volume with no operational signal |
| 2 | Duplicate events at every layer for one transition | One transition, one event; pick the owning layer |
| 3 | Secrets, tokens, credentials, unnecessary PII | Leak; redact or omit |
| 4 | Entire request/response bodies by default | Cost and leak; log identity + status, not payload |
| 5 | High-cardinality telemetry with no operational justification | Cardinality blowup, unusable dashboards |
| 6 | Logs used where metrics or traces are the better signal | Wrong pillar; see below |

## Pure and Internal Helpers Emit Nothing

A pure or internal helper (deterministic, no external side effect, no state
transition an operator cares about) legitimately requires NO operational event.
Absence of logging is the correct state, not a gap. Do not flag it.

## Which Pillar Is the Evidence

| Need | Pillar | Example |
|------|--------|---------|
| A specific failure decision or skip reason, one occurrence, with causal context | Log | "skipped sync: manifest missing" |
| A rate, count, or duration trend to alert or graph on | Metric | retry rate, p99 latency, rate-limit count |
| Where time went across a boundary in one request | Trace | slow downstream call in a request span |

If the question is "how often / how slow across all requests", that is a metric,
not a log line per event. If the question is "what did THIS operation decide and
why", that is a log. Do not substitute one for the other.

## Reference, Do Not Copy

Other skills and rules point to this file; they must not restate the policy.
The review axis `.claude/skills/review/references/observability.md` references
this contract to check producer-side emission. Copying the tables forks the
policy and drifts.

## Executable Guard

`.claude/skills/observability/scripts/check_event_logging.py` encodes the two
tables above as a deterministic decision procedure. Given a described scenario
(what the code does, what it emits), it returns whether the emission is
compliant. `tests/skills/observability/test_event_logging_contract.py` exercises
the nine reference scenarios, including the pure-helper case where NO logging is
correct and the negative controls where a missing required event or prohibited
content is detected.

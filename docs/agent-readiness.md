# Agent Readiness Signals

This page records how this repository answers each Agent Readiness signal.
It covers two signals that pass and nine that are out of scope.

## Why some signals are out of scope

This repository is a plugin toolkit. It ships agents, skills, and rules for
Claude Code and GitHub Copilot CLI. It runs no hosted service. The
[`README.md`](../README.md#fastest-start) "Data sent" bullet states this, in
the "Fastest Start" section.

Several readiness signals measure a running service. They need a server,
users, or deploys to observe. This repository has none of those, so those
signals do not apply.

## Signals that pass

| Signal | Status | Evidence |
|---|---|---|
| `circuit_breakers` | Pass (retry with backoff) | [`scripts/github_core/api.py`](../scripts/github_core/api.py) |
| `alerting_configured` | Pass (GitHub issue alerts) | [`.github/workflows/check-ruleset-drift.yml`](../.github/workflows/check-ruleset-drift.yml), [`.github/workflows/drift-detection.yml`](../.github/workflows/drift-detection.yml) |

### circuit_breakers

The signal passes on a circuit breaker or on retry with exponential backoff.
This repository has retry with backoff. It has no circuit breaker.

The GitHub API helpers live in
[`scripts/github_core/api.py`](../scripts/github_core/api.py). The build
copies them into [`src/claude/lib/github_core/`](../src/claude/lib/github_core/).
The `.claude/lib/github_core` path is a symlink to that copy.

GraphQL calls:

- [`api.py:1055`](../scripts/github_core/api.py#L1055) sets
  `_GRAPHQL_MAX_ATTEMPTS = 3`.
- [`api.py:1056`](../scripts/github_core/api.py#L1056) sets
  `_GRAPHQL_BACKOFF_BASE_SECONDS = 2.0`.
- [`api.py:1113`](../scripts/github_core/api.py#L1113) computes the ceiling
  as `_GRAPHQL_BACKOFF_BASE_SECONDS ** (attempt - 1)`. With the base at 2.0,
  that is 1 second, then 2 seconds. This is exponential backoff for HTTP 429
  and 5xx failures.
- [`api.py:1066`](../scripts/github_core/api.py#L1066) sets a longer ladder
  of 15 and 30 seconds for rate-limit refusals.
- [`api.py:1114`](../scripts/github_core/api.py#L1114) stops retrying when
  the rate-limit bucket is drained, since no short retry can outlast the reset.
- [`api.py:1131` to `1134`](../scripts/github_core/api.py#L1131-L1134) honors
  a `Retry-After` header. Otherwise it waits a random time up to the ceiling
  (full jitter).
- [`api.py:1217` to `1253`](../scripts/github_core/api.py#L1217-L1253) is the
  loop. It retries only transient errors and raises on permanent ones.

REST page calls:

- [`api.py:950`](../scripts/github_core/api.py#L950) sets
  `REST_REFUSAL_BACKOFF_SECONDS = (300.0, 600.0)`. Each wait doubles the one
  before.
- [`api.py:951`](../scripts/github_core/api.py#L951) limits retries to HTTP
  429, 500, 502, 503, and 504, plus rate-limit refusals.
- [`api.py:964` to `991`](../scripts/github_core/api.py#L964-L991) is the
  loop. It makes at most three attempts.

What would add a circuit breaker: a long-running process that calls GitHub
many times per minute. Today each script run is short, so bounded retries are
enough.

### alerting_configured

The signal passes on custom alert rules that notify when things go wrong.
This repository files GitHub issues from scheduled checks. GitHub then
notifies repository watchers and anyone subscribed to the labels.

Ruleset drift check:

- [`.github/workflows/check-ruleset-drift.yml`](../.github/workflows/check-ruleset-drift.yml)
  runs daily at 06:00 UTC.
- It runs
  [`scripts/validation/check_ruleset_params_drift.py`](../scripts/validation/check_ruleset_params_drift.py)
  with `--alert`.
- [`check_ruleset_params_drift.py:311` to `316`](../scripts/validation/check_ruleset_params_drift.py#L311-L316)
  call `publish_drift_alert` when drift is found and `--alert` is set.
- [`scripts/ci/ruleset_context_drift.py:43`](../scripts/ci/ruleset_context_drift.py#L43)
  sets the labels to `bug`, `area-workflows`, `drift-detected`, and
  `automated`.
- [`ruleset_context_drift.py:247` to `292`](../scripts/ci/ruleset_context_drift.py#L247-L292)
  opens one issue. If an open issue with that title exists, it updates a
  marked comment instead. This avoids duplicate alerts.
- The job still exits non-zero on drift, so the failed run also shows in the
  Actions tab.

Agent drift check:

- [`.github/workflows/drift-detection.yml`](../.github/workflows/drift-detection.yml)
  runs weekly, Mondays at 09:00 UTC.
- [Lines 111 to 119](../.github/workflows/drift-detection.yml#L111-L119)
  count open issues with the `drift-detected` label. The query does not
  filter by title.
- [Lines 121 to 128](../.github/workflows/drift-detection.yml#L121-L128)
  open a new issue through
  [`scripts/ci/drift_create_alert_issue.py`](../scripts/ci/drift_create_alert_issue.py)
  when that count is zero.
- [`drift_create_alert_issue.py:84` to `85`](../scripts/ci/drift_create_alert_issue.py#L84-L85)
  label it `drift-detected` and `automated`.
- [Lines 130 to 152](../.github/workflows/drift-detection.yml#L130-L152)
  comment on the first open `drift-detected` issue the list returns.

Known gap: the ruleset alert also carries the `drift-detected` label. While a
ruleset drift issue is open, the weekly agent drift check comments on that
issue. It does not open a separate agent drift issue. The alert still lands,
but on an issue with another title.

There is no pager, chat, or email hook. GitHub issue notifications are the
alert channel.

## Signals out of scope

| Signal | Status | Reason | What would change the decision |
|---|---|---|---|
| `error_tracking_contextualized` | Out of scope | No hosted service throws runtime errors to track. Errors surface in the user's CLI session. | The project ships a hosted service. |
| `error_to_insight_pipeline` | Out of scope | No error tracker exists to feed a pipeline. | Error tracking is added for a hosted service. |
| `product_analytics_instrumentation` | Out of scope | Analytics would send usage data from user machines. That breaks the [`README.md`](../README.md#fastest-start) "Data sent" statement. | Users opt in, and the privacy statement is changed first. |
| `feature_flag_infrastructure` | Out of scope | Users install a plugin version. No server exists to flip a flag at run time. | The project ships a hosted service with staged rollouts. |
| `distributed_tracing` | Out of scope | No multi-service request path exists to trace. | The project runs two or more services that call each other. |
| `metrics_collection` | Out of scope | No runtime process exists to emit telemetry. | The project runs a long-lived service. |
| `deployment_observability` | Out of scope | Releases publish plugin files. Nothing is deployed to a server. | The project deploys to an environment it operates. |
| `deployment_frequency` | Out of scope | There are no deploys to count. Releases follow [`RELEASING.md`](../RELEASING.md). | The project deploys a service on a schedule. |
| `build_performance_tracking` | Out of scope | The repository has no compiled build to time. Generation runs in seconds through [`build/scripts/build_all.py`](../build/scripts/build_all.py). | Build time grows enough to slow pull requests. |

Revisit this page when the project adds a hosted service or changes the
[`README.md`](../README.md#fastest-start) "Data sent" statement.

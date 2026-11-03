# Agent Readiness Signals

This page records how this repository answers each Agent Readiness signal.
It covers two signals that pass and nine that are out of scope.

## Why some signals are out of scope

This repository is a plugin toolkit. It ships agents, skills, and rules for
Claude Code and GitHub Copilot CLI. It runs no hosted service. The README
"Data sent" bullet states this, in the "Fastest Start" section.

Several readiness signals measure a running service. They need a server,
users, or deploys to observe. This repository has none of those, so those
signals do not apply.

## Signals that pass

| Signal | Status | Evidence |
|---|---|---|
| `circuit_breakers` | Pass (retry with backoff) | `scripts/github_core/api.py` |
| `alerting_configured` | Pass (GitHub issue alerts) | `.github/workflows/check-ruleset-drift.yml`, `.github/workflows/drift-detection.yml` |

### circuit_breakers

The signal passes on a circuit breaker or on retry with exponential backoff.
This repository has retry with backoff. It has no circuit breaker.

The GitHub API helpers live in `scripts/github_core/api.py`. The build copies
them into `src/claude/lib/github_core/`. The `.claude/lib/github_core` path
is a symlink to that copy.

GraphQL calls:

- `api.py:1055` sets `_GRAPHQL_MAX_ATTEMPTS = 3`.
- `api.py:1056` sets the backoff base to 2 seconds.
- `api.py:1113` computes the ceiling as `2 ** (attempt - 1)`. That is
  exponential backoff for HTTP 429 and 5xx failures.
- `api.py:1066` sets a longer ladder of 15 and 30 seconds for rate-limit
  refusals.
- `api.py:1114` stops retrying when the rate-limit bucket is drained, since
  no short retry can outlast the reset.
- `api.py:1131` to `api.py:1134` honors a `Retry-After` header. Otherwise it
  waits a random time up to the ceiling (full jitter).
- `api.py:1217` to `api.py:1253` is the loop. It retries only transient
  errors and raises on permanent ones.

REST page calls:

- `api.py:950` sets `REST_REFUSAL_BACKOFF_SECONDS = (300.0, 600.0)`. Each
  wait doubles the one before.
- `api.py:951` limits retries to HTTP 429, 500, 502, 503, and 504, plus
  rate-limit refusals.
- `api.py:964` to `api.py:991` is the loop. It makes at most three attempts.

What would add a circuit breaker: a long-running process that calls GitHub
many times per minute. Today each script run is short, so bounded retries are
enough.

### alerting_configured

The signal passes on custom alert rules that notify when things go wrong.
This repository files GitHub issues from scheduled checks. GitHub then
notifies repository watchers and anyone subscribed to the labels.

Ruleset drift check:

- `.github/workflows/check-ruleset-drift.yml` runs daily at 06:00 UTC.
- It runs `scripts/validation/check_ruleset_params_drift.py --alert`.
- `check_ruleset_params_drift.py:311` to `:316` call `publish_drift_alert`
  when drift is found and `--alert` is set.
- `scripts/ci/ruleset_context_drift.py:43` sets the labels to `bug`,
  `area-workflows`, `drift-detected`, and `automated`.
- `ruleset_context_drift.py:247` to `:292` opens one issue. If an open issue
  with that title exists, it updates a marked comment instead. This avoids
  duplicate alerts.
- The job still exits non-zero on drift, so the failed run also shows in the
  Actions tab.

Agent drift check:

- `.github/workflows/drift-detection.yml` runs weekly, Mondays at 09:00 UTC.
- Lines 121 to 128 open a new issue through
  `scripts/ci/drift_create_alert_issue.py` when no open drift issue exists.
- `drift_create_alert_issue.py:84` to `:85` label it `drift-detected` and
  `automated`.
- Lines 130 to 152 comment on the open issue when one already exists.

There is no pager, chat, or email hook. GitHub issue notifications are the
alert channel.

## Signals out of scope

| Signal | Status | Reason | What would change the decision |
|---|---|---|---|
| `error_tracking_contextualized` | Out of scope | No hosted service throws runtime errors to track. Errors surface in the user's CLI session. | The project ships a hosted service. |
| `error_to_insight_pipeline` | Out of scope | No error tracker exists to feed a pipeline. | Error tracking is added for a hosted service. |
| `product_analytics_instrumentation` | Out of scope | Analytics would send usage data from user machines. That breaks the README "Data sent" statement. | Users opt in, and the privacy statement is changed first. |
| `feature_flag_infrastructure` | Out of scope | Users install a plugin version. No server exists to flip a flag at run time. | The project ships a hosted service with staged rollouts. |
| `distributed_tracing` | Out of scope | No multi-service request path exists to trace. | The project runs two or more services that call each other. |
| `metrics_collection` | Out of scope | No runtime process exists to emit telemetry. | The project runs a long-lived service. |
| `deployment_observability` | Out of scope | Releases publish plugin files. Nothing is deployed to a server. | The project deploys to an environment it operates. |
| `deployment_frequency` | Out of scope | There are no deploys to count. Releases follow `RELEASING.md`. | The project deploys a service on a schedule. |
| `build_performance_tracking` | Out of scope | The repository has no compiled build to time. Generation runs in seconds through `build/scripts/build_all.py`. | Build time grows enough to slow pull requests. |

Revisit this page when the project adds a hosted service or changes the
README "Data sent" statement.

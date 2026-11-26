---
source: wiki/concepts/Observability/OTel Semantic Conventions.md
created: 2026-06-01
review-by: 2026-09-01
---

# OTel Semantic Conventions

## Principle

Standardized attribute names, types, values, and descriptions give telemetry
data consistent meaning across traces, metrics, and logs. The convention layer
turns OpenTelemetry from "another telemetry SDK" into a portability story: the
same `http.request.method` attribute means the same thing whether it is emitted
by a Go service, a Python library, or a Kubernetes sidecar. This reference
complements `three-pillars-reference.md`: that file covers what the three pillars
are, this one covers how to name what they emit so the signal is portable.

## What They Solve

Before semantic conventions, every team named the same field differently:
`http_method`, `httpMethod`, `request.method`, `verb`. Dashboards broke on every
service migration. Alerts could not be reused. Cross-service correlation
required a custom mapping per integration.

After semantic conventions, a shared schema. Dashboards, SLOs, alerts, and
queries become portable across services and vendors. This is the foundation of
vendor-neutral observability.

## Categories

| Signal | Examples |
|--------|----------|
| Resource | `service.name`, `service.version`, `host.name`, `cloud.provider`, `k8s.pod.name` |
| Traces | Span names and kinds, `http.request.method`, `db.system`, `messaging.destination.name` |
| Metrics | Instrument types, names, units (`http.server.request.duration`) |
| Logs | Standardized severity, body, attributes |

## Attribute Namespaces

Dot-separated hierarchies signal the domain:

- `http.*`: HTTP client and server (`http.response.status_code`, `http.route`)
- `db.*`: database operations (`db.system`, `db.statement`, `db.operation`)
- `k8s.*`: Kubernetes (`k8s.namespace.name`, `k8s.deployment.name`)
- `messaging.*`, `rpc.*`, `exception.*`, `cloud.*`, `host.*`

## Stable Versus Experimental

Each convention carries a stability marker. Stable means production-ready, a
frozen surface. Experimental means subject to breaking changes. Migrating
instrumentation through a stable promotion is itself an event that can trigger a
rename storm.

## Why It Matters

Semantic conventions are the interop contract of modern observability. Without
them, OpenTelemetry would be just another SDK. With them, it becomes the
substrate for service-mesh telemetry, SLO and SLI definitions, and cross-vendor
backend swaps without rewriting queries.

## Why This Lens Applies In PR Review

When a diff adds telemetry (a new log field, a metric instrument, a span
attribute), check the names against the semantic conventions rather than letting
each path invent its own. A change that emits `httpMethod` next to an existing
`http.request.method`, or that names a duration metric without a unit, breaks the
portability of every dashboard, alert, and query that reads it. The cost is
silent until a backend swap or a dashboard reuse exposes the drift. Flag
non-conventional attribute names and missing units on new telemetry, and prefer
the stable convention name over a hand-rolled one.

## Related

- Three pillars reference: logs, metrics, traces and what each one is for.
- OTel migration reference: how to handle a rename storm when a convention is
  promoted from experimental to stable.

## Source

OTel Semantic Conventions Spec (opentelemetry.io/docs/specs/semconv/) and the
open-telemetry/semantic-conventions repository.

---
source: wiki/concepts/Reliability/Observability Three Pillars.md
created: 2026-04-11
review-by: 2026-07-11
---

# Observability Three Pillars

Understand a system's internal state by examining its external outputs. Three complementary signal types provide complete visibility.

## Observability vs Monitoring

| Aspect | Monitoring | Observability |
|--------|------------|---------------|
| Approach | Predefined metrics and alerts | Explore unknown unknowns |
| Questions | "Is it broken?" | "Why is it broken?" |
| Data | Aggregated metrics | High-cardinality, contextual |
| Use case | Known failure modes | Novel failures, debugging |

## Pillar 1: Logs

Timestamped records of discrete events. Structured (JSON) preferred over unstructured.

**Best Practices**:

- Use structured logging (JSON) with consistent field names
- Include correlation IDs (trace ID) in every log entry
- Log at appropriate levels (ERROR, WARN, INFO, DEBUG)
- Never log sensitive data (PII, credentials, tokens)

## Pillar 2: Metrics

Numeric measurements aggregated over time.

| Type | Description | Example |
|------|-------------|---------|
| Counter | Monotonically increasing | Requests total, errors total |
| Gauge | Point-in-time value | Active connections, queue depth |
| Histogram | Distribution of values | Request latency percentiles |

**Best Practices**:

- USE method for resources: Utilization, Saturation, Errors
- RED method for services: Rate, Errors, Duration
- Define meaningful labels and dimensions
- Alert on SLO-relevant metrics, not raw values

## Pillar 3: Traces

Distributed request flow across services.

| Concept | Description |
|---------|-------------|
| Trace | End-to-end journey of a request |
| Span | Single operation within a trace |
| Context | Propagated trace ID + span ID across boundaries |

**Best Practices**:

- Propagate context (W3C Trace Context) across service boundaries
- Sample appropriately for high-volume services
- Include business context in span attributes
- Connect traces to logs via trace ID

## Correlation Matrix

| Scenario | Start With | Then Use |
|----------|------------|----------|
| Alert fires | Metrics (what is wrong) | Traces (where), Logs (why) |
| User complaint | Traces (request path) | Logs (specific errors) |
| Performance issue | Metrics (latency trend) | Traces (slow spans) |
| Debug production bug | Logs (error details) | Traces (context) |

## OpenTelemetry Unification

Single SDK covering all three pillars. Vendor-neutral, CNCF standard.

```csharp
using var tracerProvider = Sdk.CreateTracerProviderBuilder()
    .AddSource("MyService")
    .AddOtlpExporter()
    .Build();
```

## Relationship to SRE

| SRE Practice | Observability Role |
|--------------|-------------------|
| SLO/SLI/SLA | Metrics define and track SLIs |
| Error Budgets | Metrics track budget consumption |
| Chaos Engineering | All three pillars validate resilience |
| Incident Response | Traces + logs for root cause analysis |

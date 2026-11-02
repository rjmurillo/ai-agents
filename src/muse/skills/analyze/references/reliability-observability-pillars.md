---
source: wiki/concepts/Reliability/Observability Three Pillars.md
created: 2026-04-11
review-by: 2026-07-11
---

# Observability: Three Pillars

Observability is the ability to understand a system's internal state by examining its external outputs. Use during investigation and debugging phases of analysis.

## Observability vs Monitoring

| Aspect | Monitoring | Observability |
|--------|------------|---------------|
| Approach | Predefined metrics and alerts | Explore unknown unknowns |
| Questions | "Is it broken?" | "Why is it broken?" |
| Data | Aggregated metrics | High-cardinality, contextual |
| Use case | Known failure modes | Novel failures, debugging |

## The Three Pillars

### Logs

Timestamped records of discrete events. Use for debugging, auditing, compliance.

Best practices:

- Use structured logging (JSON)
- Include correlation IDs (trace ID)
- Log at appropriate levels
- Do not log sensitive data

### Metrics

Numeric measurements aggregated over time.

| Type | Description | Example |
|------|-------------|---------|
| Counter | Monotonically increasing | Requests total, errors total |
| Gauge | Point-in-time value | Current connections, queue depth |
| Histogram | Distribution of values | Request latency percentiles |

Best practices:

- USE method: Utilization, Saturation, Errors (for resources)
- RED method: Rate, Errors, Duration (for services)
- Define meaningful labels/dimensions
- Set alerts on SLO-relevant metrics

### Traces

Distributed request flow across services.

| Concept | Description |
|---------|-------------|
| Trace | End-to-end journey of a request |
| Span | Single operation within a trace |
| Context | Propagated trace ID + span ID |

Best practices:

- Propagate context across service boundaries
- Sample appropriately for high-volume services
- Include business context in span attributes
- Connect traces to logs via trace ID

## Investigation Workflow

| Scenario | Start With | Then Use |
|----------|------------|----------|
| Alert fires | Metrics (what's wrong) | Traces (where), Logs (why) |
| User complaint | Traces (request path) | Logs (specific errors) |
| Performance issue | Metrics (latency) | Traces (slow spans) |
| Debug production bug | Logs (error details) | Traces (context) |

## Assessing Observability During Analysis

When analyzing a codebase, check for these gaps:

| Gap | Signal | Severity |
|-----|--------|----------|
| No structured logging | String concatenation in log calls | High |
| Missing correlation IDs | No trace ID propagation | High |
| No metrics instrumentation | No counters, gauges, or histograms | Medium |
| Incomplete trace coverage | Spans missing for external calls | Medium |
| Sensitive data in logs | PII, tokens, passwords logged | Critical |
| No alerting on SLOs | Metrics exist but no alert rules | Medium |

## Modern Standard: OpenTelemetry

Vendor-neutral SDK unifying all three pillars. Look for OTel adoption as a positive signal during analysis.

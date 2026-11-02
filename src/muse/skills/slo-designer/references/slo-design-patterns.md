# SLO Design Patterns

Reference patterns for common service types based on Google SRE best practices.

## Pattern Selection Guide

| Service Type | Primary SLIs | Typical Target | Error Budget |
|--------------|--------------|----------------|--------------|
| Consumer API | Availability, Latency | 99.9% | 43 min/month |
| Internal API | Availability, Error Rate | 99.5% | 3.6 hr/month |
| Data Pipeline | Freshness, Correctness | 99% | 7.3 hr/month |
| Real-time System | Latency, Availability | 99.99% | 4 min/month |
| Batch Processing | Completion, Correctness | 99% | 7.3 hr/month |

## Consumer-Facing API Pattern

Services directly used by end-users.

### Consumer-Facing Characteristics

- User experience is paramount
- Latency directly impacts satisfaction
- Errors visible to users
- High availability expectations

### Consumer-Facing Recommended SLIs

1. **Availability**: 99.9% (43 min/month downtime)
2. **Latency p99**: < 200ms
3. **Latency p50**: < 50ms
4. **Error Rate**: < 0.1%

### Consumer-Facing Example Configuration

```yaml
slis:
  - name: Availability
    description: Successful HTTP responses
    measurement: |
      sum(rate(http_requests_total{status!~"5.."}[5m]))
      / sum(rate(http_requests_total[5m]))

  - name: Latency P99
    description: 99th percentile response time
    measurement: |
      histogram_quantile(0.99, rate(http_duration_bucket[5m]))

slos:
  - sli: Availability
    target: 99.9
    rationale: Industry standard for consumer APIs

  - sli: Latency P99
    target: 200  # milliseconds
    rationale: Research shows user frustration above 200ms
```

## Internal API Pattern

Services used by other internal services.

### Internal API Characteristics

- Downstream systems can retry
- Batch operations common
- Less latency-sensitive
- Cost of reliability is higher

### Internal API Recommended SLIs

1. **Availability**: 99.5% (3.6 hr/month downtime)
2. **Latency p99**: < 500ms
3. **Error Rate**: < 1%

### Internal API Example Configuration

```yaml
slis:
  - name: Availability
    description: Successful gRPC responses
    measurement: |
      sum(rate(grpc_requests_total{code!~"UNAVAILABLE|INTERNAL"}[5m]))
      / sum(rate(grpc_requests_total[5m]))

slos:
  - sli: Availability
    target: 99.5
    rationale: Internal services can retry; 3.6hr/month budget allows maintenance
```

## Data Pipeline Pattern

ETL, data processing, analytics pipelines.

### Pipeline Characteristics

- Correctness over availability
- Freshness matters for downstream consumers
- Batch windows provide natural recovery time
- Data quality is critical

### Pipeline Recommended SLIs

1. **Freshness**: Data processed within SLA
2. **Correctness**: No data corruption or loss
3. **Completeness**: All expected records processed

### Pipeline Example Configuration

```yaml
slis:
  - name: Freshness
    description: Time since last successful pipeline run
    measurement: |
      time() - pipeline_last_success_timestamp

  - name: Correctness
    description: Percentage of records passing validation
    measurement: |
      sum(pipeline_records_valid) / sum(pipeline_records_total)

  - name: Completeness
    description: Percentage of expected records processed
    measurement: |
      sum(pipeline_records_processed) / sum(pipeline_records_expected)

slos:
  - sli: Freshness
    target: 3600  # Within 1 hour of schedule
    rationale: Downstream dashboards refresh hourly

  - sli: Correctness
    target: 99.99
    rationale: Data integrity is critical for business decisions
```

## Real-Time System Pattern

Low-latency, high-availability systems.

### Real-Time System Characteristics

- Extremely low latency requirements
- Very high availability (four 9s or more)
- Often financial or safety-critical
- Expensive to maintain

### Real-Time System Recommended SLIs

1. **Availability**: 99.99% (4 min/month downtime)
2. **Latency p99**: < 50ms
3. **Latency p999**: < 100ms

### Real-Time System Example Configuration

```yaml
slis:
  - name: Availability
    description: Service responding to health checks
    measurement: |
      sum(up{job="realtime-service"}) / count(up{job="realtime-service"})

  - name: Latency P99
    description: 99th percentile processing time
    measurement: |
      histogram_quantile(0.99, rate(processing_duration_bucket[1m]))

slos:
  - sli: Availability
    target: 99.99
    rationale: Financial transactions require high availability

  - sli: Latency P99
    target: 50  # milliseconds
    rationale: Trading requires sub-100ms responses
```

## Dependency Chain Patterns

### Chain Reliability Calculation

When services depend on each other:

```text
Overall Availability = Service A * Service B * Service C
```

Example:

- Service A: 99.9%
- Service B: 99.9%
- Service C: 99.9%
- Combined: 99.9% x 99.9% x 99.9% = 99.7%

### Mitigation Strategies

1. **Circuit Breakers**: Fail fast when dependency is down
2. **Fallbacks**: Graceful degradation with cached/default data
3. **Retries with Backoff**: Handle transient failures
4. **Bulkheads**: Isolate dependency failures

## Anti-Patterns to Avoid

### 1. Setting Unrealistic Targets

**Bad**: 99.999% availability for a non-critical internal tool
**Why**: Enormous engineering cost, no user benefit
**Fix**: Start with 99.5%, increase based on evidence

### 2. Too Many SLOs

**Bad**: 15 different SLOs per service
**Why**: Cognitive overload, conflicting priorities
**Fix**: 3-5 SLOs covering critical user journeys

### 3. SLO Higher Than Dependencies

**Bad**: 99.99% SLO when critical dependency is 99.9%
**Why**: Mathematically impossible without redundancy
**Fix**: Account for dependency chain in targets

### 4. No Error Budget Policy

**Bad**: Define SLOs but never use error budget
**Why**: SLOs become meaningless metrics
**Fix**: Define clear policies for budget consumption

### 5. SLO = SLA

**Bad**: Same target for internal SLO and customer SLA
**Why**: No buffer for issues before contract breach
**Fix**: SLO should be 10-50% tighter than SLA

## Burn Rate Reference

Standard burn rates for monthly error budgets:

| Burn Rate | Time to Exhaust | Use Case |
|-----------|-----------------|----------|
| 1x | 30 days | Normal operation |
| 2x | 15 days | Slightly elevated errors |
| 6x | 5 days | Significant issue |
| 14.4x | 50 hours | Major incident |
| 36x | 20 hours | Critical outage |
| 72x | 10 hours | Complete failure |

### Multi-Window Alert Strategy

```yaml
# Page-worthy (immediate action)
- condition: burn_rate_1h > 14.4 AND burn_rate_6h > 6
  action: page

# Ticket-worthy (business hours)
- condition: burn_rate_6h > 6 AND burn_rate_24h > 2
  action: ticket

# Low-priority (next sprint)
- condition: burn_rate_24h > 2
  action: backlog
```

## References

- [Google SRE Book - Service Level Objectives](https://sre.google/sre-book/service-level-objectives/)
- [Google SRE Workbook - Implementing SLOs](https://sre.google/workbook/implementing-slos/)
- [The Art of SLOs](https://sre.google/workbook/slo-engineering/)
- [Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/)

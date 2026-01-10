# SLO/SLI/SLA Framework

**Category**: Operability
**Source**: `.agents/analysis/senior-engineering-knowledge.md`
**Origin**: Google SRE Book

## Definitions

- **SLI** (Service Level Indicator): Metric measuring service quality (e.g., p99 latency)
- **SLO** (Service Level Objective): Target for SLI (e.g., p99 < 200ms)
- **SLA** (Service Level Agreement): Contract with consequences (e.g., credits if breached)

## Error Budget Concept

If SLO is 99.9% availability, error budget is 0.1% (~43 minutes/month).

**Use it for**: Experimentation, deployments, learning from failures

## Common SLIs

| Category | Example SLI |
|----------|-------------|
| Availability | % of successful requests |
| Latency | p50, p95, p99 response times |
| Throughput | Requests per second |
| Error Rate | % of requests returning 5xx |
| Correctness | % of requests with correct data |

## Implementation

1. Identify critical user journeys
2. Define SLIs for each journey
3. Set SLOs based on user expectations
4. Measure and alert on SLO breach risk
5. Use error budget for velocity decisions

## Related

- `mttr-optimization` - Mean time to recovery
- `monitoring-traffic-lights` - Red/yellow/green alerting

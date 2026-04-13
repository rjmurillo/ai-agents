---
source: wiki/concepts/Reliability/SLO SLI SLA.md
created: 2026-04-11
review-by: 2026-07-11
---

# SLO / SLI / SLA Reference

Service level objectives provide the measurable targets that chaos experiments validate.

## Definitions

| Term | Meaning | Example |
|------|---------|---------|
| SLI (Service Level Indicator) | Metric that measures service behavior | p99 latency, error rate, availability |
| SLO (Service Level Objective) | Target value for an SLI | p99 latency < 200ms, 99.9% availability |
| SLA (Service Level Agreement) | Contract with consequences if SLO missed | Refunds, credits, penalties |

## Hierarchy

```
SLA (contract) --> SLO (target) --> SLI (measurement)
```

SLOs should be slightly stricter than SLAs. Internal SLOs enable error budgets.

## Common SLIs

| SLI | Measurement | Chaos Relevance |
|-----|-------------|-----------------|
| Availability | % of successful requests | Primary impact metric during experiments |
| Latency | p50, p95, p99 response times | Detects degradation before failure |
| Throughput | Requests per second | Validates capacity under failure |
| Error rate | % of failed requests | Direct measure of customer impact |

## Error Budget Formula

```
Error Budget = 100% - SLO

99.9% availability SLO = 0.1% error budget = ~43 minutes/month
99.95% availability SLO = 0.05% error budget = ~22 minutes/month
99.99% availability SLO = 0.01% error budget = ~4.3 minutes/month
```

## Error Budget Mechanics

1. Define SLO (e.g., 99.9% availability)
2. Calculate error budget (0.1% = 43 min/month)
3. Track consumption via incidents and chaos experiments
4. Budget depleted: freeze features, focus on reliability
5. Budget healthy: ship faster, run more experiments

## Chaos Experiment Integration

- **Baseline thresholds**: Derive Green/Yellow/Red zones from SLO targets
- **Hypothesis formation**: Reference specific SLIs in predictions
- **Impact measurement**: Compare actual SLI values during experiment against SLO
- **Budget tracking**: Account for chaos-induced SLI violations in monthly budget
- **Go/no-go gate**: Error budget status determines whether experiments proceed

## Benefits of Error Budgets

- Align reliability with business needs
- Provide objective go/no-go for releases and experiments
- Empower teams to make risk decisions with data
- Reduce reliability vs velocity tension

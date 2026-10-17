---
source: wiki/concepts/Reliability/Chaos Engineering.md
created: 2026-04-11
review-by: 2026-07-11
---

# Chaos Engineering Principles

Build confidence in system resilience by introducing controlled failures in production.

## Process

1. **Define steady state**: Normal operating metrics (throughput, error rates, latency percentiles)
2. **Hypothesize**: System will maintain steady state during experiment
3. **Introduce variables**: Inject failures (network, service, infrastructure)
4. **Observe**: Compare actual vs expected behavior
5. **Learn**: Fix weaknesses, document findings

## Common Experiments

| Category | Examples |
|----------|----------|
| Instance failure | Kill process, terminate VM, evict pod |
| Network | Partition, latency injection, packet loss, DNS failure |
| Resource exhaustion | CPU spike, memory pressure, disk fill |
| Dependency | External service unavailable, slow response |
| Region | Simulate region or availability zone failure |

## Prerequisites

- Strong observability (cannot learn from what you cannot see)
- Runbooks for recovery
- SLOs to measure impact
- Organizational buy-in and stakeholder approval

## Anti-Patterns

| Anti-Pattern | Risk | Mitigation |
|--------------|------|------------|
| Chaos without observability | Blind experimentation, no learning | Establish three pillars first |
| Chaos without hypothesis | Random breaking, no measurable outcome | Use falsifiable hypothesis template |
| Chaos without communication | Surprise failures, trust erosion | Notify stakeholders, on-call, support |
| Chaos without recovery plan | Uncontrolled damage, extended outage | Define and test rollback before starting |
| Testing only in staging | Production has different traffic patterns | Start small in production |
| No baseline metrics | Cannot compare results | Collect 7+ days of steady state data |

## Blast Radius Containment

1. Start with smallest possible scope (single instance)
2. Use canary deployment pattern for experiments
3. Define automatic abort criteria
4. Have rollback ready and tested before starting
5. Notify on-call before and after execution

## Relationship to SRE Practices

- **SLOs**: Tolerance thresholds derive from SLO targets
- **Error budgets**: Chaos experiments consume error budget; track consumption
- **Observability**: All three pillars validate resilience during experiments
- **Incident response**: Chaos validates runbooks and recovery procedures

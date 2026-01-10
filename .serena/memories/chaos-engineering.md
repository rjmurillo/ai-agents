# Chaos Engineering

**Created**: 2026-01-10
**Category**: Resilience Engineering

## Overview

"The discipline of experimenting on a system to build confidence in its capability to withstand turbulent conditions in production."

## Core Principles

1. **Steady State Focus**: Measure observable outputs (throughput, error rates, latency percentiles)
2. **Real-World Variables**: Introduce realistic disruptions
3. **Production Testing**: Experiment on live systems
4. **Continuous Automation**: Build experiments into systems
5. **Blast Radius Containment**: Minimize customer impact

## Methodology

1. Establish baseline steady state metrics
2. Form hypothesis that state persists across test and control groups
3. Introduce variables simulating real-world events
4. Compare outcomes to identify weaknesses

## Best Practices

- Focus on measurable outcomes
- Automate continuous testing
- Prioritize high-impact events
- Contain negative effects during experiments

## Benefits

- Identify systemic weaknesses before customer impact
- Prevent cascading outages, retry storms, service degradation
- Build confidence in system resilience

## Related

- `slo-sli-sla`: Reliability targets and error budgets
- `resilience-patterns`: Circuit breaker, bulkhead, retry
- `foundational-knowledge-index`: Master index

# Service Reliability Hierarchy

Bottom-up progression for building reliable services. Each level depends on foundations below.

## Level 1: Basic Ownership and Observability
- Clear ownership model (team, on-call rotation)
- Logging, metrics, tracing instrumentation
- Dashboards showing service health
- Alerting for critical failures

**Exit Criteria**: Team can detect and respond to outages within SLA.

## Level 2: Service Level Objectives (SLOs)
- Define SLIs (Service Level Indicators): latency, error rate, throughput
- Set SLOs with error budgets
- Monitor burn rate
- Escalation paths when error budget depletes

**Exit Criteria**: Quantifiable reliability targets with tracking.

## Level 3: Incident Response
- Blameless postmortems
- Runbooks for common issues
- Incident command structure
- Post-incident action items tracked to completion

**Exit Criteria**: Systematic learning from failures.

## Level 4: Safe Release Practices
- Automated baseline comparison
- Fast rollback mechanisms (< 5 minutes)
- Continuous deployment with feature flags
- Gradual rollout (canary, ring deployment)

**Exit Criteria**: Deploy multiple times per day with <0.1% rollback rate.

## Level 5: Testing, Capacity, Performance
- Load testing in staging
- Integration testing with dependencies
- Capacity planning based on traffic projections
- Performance regression testing

**Exit Criteria**: Proactive capacity management, no surprise outages from traffic.

## Level 6: High Availability and Disaster Recovery
- Multi-region deployment
- Automated failover mechanisms
- Load shedding and graceful degradation
- Regular DR drills

**Exit Criteria**: Survive single region failure with <1 minute failover.

## Level 7: Chaos Testing
- Unannounced DR exercises
- Fault injection in production
- Automated chaos testing (e.g., Chaos Monkey)
- Resilience validation under adversarial conditions

**Exit Criteria**: Service self-heals from arbitrary failures without human intervention.

## Application Strategy

1. **Do NOT skip levels**. Each builds on previous foundations.
2. **Level 1-3 are table stakes** for production services.
3. **Level 4-5 required** for high-scale or business-critical services.
4. **Level 6-7 reserved** for tier-0/tier-1 services with extreme uptime requirements.

## Source
User preference: Richard Murillo's global CLAUDE.md (removed during token optimization 2026-01-04)

## Context
Richard was Principal SWE Manager (M6) at Microsoft, built 40-person org for MDE modernization.

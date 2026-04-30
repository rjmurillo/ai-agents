# Chaos Experiment: {{EXPERIMENT_NAME}}

## Metadata

| Field | Value |
|-------|-------|
| **Experiment ID** | {{EXPERIMENT_ID}} |
| **Date Created** | {{DATE_CREATED}} |
| **Target Date** | {{TARGET_DATE}} |
| **Owner** | {{OWNER}} |
| **Status** | DRAFT / APPROVED / IN_PROGRESS / COMPLETED |

## System Under Test

### Target System

- **Service/Component**: {{SYSTEM_NAME}}
- **Environment**: staging / canary / production
- **Region/Zone**: {{REGION}}
- **Instance Count**: {{INSTANCE_COUNT}}

### Architecture Context

<!-- Brief description of system architecture relevant to this experiment -->

```text
[Architecture diagram or ASCII representation]
```

### Dependencies

| Dependency | Type | Criticality |
|------------|------|-------------|
| {{DEP_NAME}} | internal / external | high / medium / low |

## Business Justification

### Objective

<!-- Why are we running this experiment? What confidence are we trying to build? -->

### Historical Context

<!-- Any relevant incidents or near-misses that motivated this experiment -->

### Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| {{RISK}} | low / medium / high | low / medium / high | {{MITIGATION}} |

## Steady State Baseline

### Metrics Collected

| Metric | Source | Baseline Value | Green Threshold | Yellow Threshold | Red Threshold |
|--------|--------|----------------|-----------------|------------------|---------------|
| P99 Latency | {{SOURCE}} | {{VALUE}}ms | < {{GREEN}}ms | < {{YELLOW}}ms | >= {{RED}}ms |
| Error Rate | {{SOURCE}} | {{VALUE}}% | < {{GREEN}}% | < {{YELLOW}}% | >= {{RED}}% |
| Throughput | {{SOURCE}} | {{VALUE}} req/s | > {{GREEN}} req/s | > {{YELLOW}} req/s | <= {{RED}} req/s |
| {{CUSTOM_METRIC}} | {{SOURCE}} | {{VALUE}} | {{GREEN}} | {{YELLOW}} | {{RED}} |

### Collection Period

- **Start Date**: {{BASELINE_START}}
- **End Date**: {{BASELINE_END}}
- **Duration**: {{BASELINE_DAYS}} days

### Dashboard Links

- Primary: {{DASHBOARD_URL}}
- Backup: {{BACKUP_DASHBOARD_URL}}

## Hypothesis

```text
Given {{SYSTEM_NAME}} in steady state with baseline metrics as documented above,
When {{FAILURE_DESCRIPTION}},
Then {{EXPECTED_BEHAVIOR}} within {{RECOVERY_TIME}},
Because {{RESILIENCE_MECHANISM}}.
```

### Predictions

| Metric | Current Baseline | Expected During Injection | Expected Recovery Time |
|--------|------------------|---------------------------|------------------------|
| P99 Latency | {{BASELINE}}ms | < {{EXPECTED}}ms | < {{RECOVERY}}s |
| Error Rate | {{BASELINE}}% | < {{EXPECTED}}% | < {{RECOVERY}}s |
| {{CUSTOM}} | {{BASELINE}} | {{EXPECTED}} | {{RECOVERY}} |

### Falsification Criteria

This hypothesis is **falsified** if:

- [ ] {{FALSIFICATION_CRITERION_1}}
- [ ] {{FALSIFICATION_CRITERION_2}}
- [ ] {{FALSIFICATION_CRITERION_3}}

## Injection Plan

### Failure Type

- **Category**: Instance / Network / Resource / Dependency / Time / State
- **Specific Failure**: {{FAILURE_DESCRIPTION}}
- **Severity**: Complete outage / Degraded / Intermittent

### Injection Method

**Tool**: {{TOOL_NAME}}

**Commands**:

```bash
# Injection command
{{INJECTION_COMMAND}}

# Verification command (confirm injection active)
{{VERIFICATION_COMMAND}}
```

### Scope and Blast Radius

| Parameter | Value |
|-----------|-------|
| Affected Instances | {{AFFECTED_COUNT}} of {{TOTAL_COUNT}} |
| Affected Regions | {{REGIONS}} |
| Estimated User Impact | {{IMPACT_PERCENTAGE}}% |
| Maximum Duration | {{MAX_DURATION}} |

### Ramp-Up Strategy

- [ ] **Immediate**: Full injection at once
- [ ] **Gradual**: Ramp over {{RAMP_DURATION}}
- [ ] **Staged**: {{STAGE_1}}% -> {{STAGE_2}}% -> {{STAGE_3}}%

### Abort Criteria

Immediately abort if:

- [ ] Error rate exceeds {{ABORT_ERROR_RATE}}%
- [ ] P99 latency exceeds {{ABORT_LATENCY}}ms
- [ ] Customer complaints received
- [ ] On-call escalation triggered
- [ ] {{CUSTOM_ABORT_CRITERION}}

## Rollback Procedure

### Automatic Rollback

**Trigger**: {{AUTO_ROLLBACK_TRIGGER}}

**Mechanism**: {{AUTO_ROLLBACK_MECHANISM}}

### Manual Rollback

**Commands**:

```bash
# Stop injection
{{ROLLBACK_COMMAND}}

# Verify rollback complete
{{VERIFY_ROLLBACK_COMMAND}}

# Force recovery if needed
{{FORCE_RECOVERY_COMMAND}}
```

**Expected Recovery Time**: {{EXPECTED_ROLLBACK_TIME}}

### Rollback Verification

- [ ] Injection stopped
- [ ] Metrics returning to baseline
- [ ] No customer-facing errors
- [ ] Alerts cleared

## Approvals

### Required Approvers

| Role | Name | Status | Date |
|------|------|--------|------|
| System Owner | {{OWNER}} | PENDING / APPROVED | |
| On-Call Lead | {{ONCALL}} | PENDING / APPROVED | |
| SRE Manager | {{SRE}} | PENDING / APPROVED | |
| {{CUSTOM_ROLE}} | {{NAME}} | PENDING / APPROVED | |

### Communication Plan

| Audience | Channel | Timing |
|----------|---------|--------|
| On-Call Team | Slack #oncall | 30 min before |
| Customer Support | Email | 1 hour before |
| Engineering | Slack #eng | 15 min before |
| {{AUDIENCE}} | {{CHANNEL}} | {{TIMING}} |

## Execution Log

### Pre-Execution Checklist

- [ ] Approvals received
- [ ] On-call notified
- [ ] Dashboards open
- [ ] Rollback tested
- [ ] Recording started

### Observation Log

```text
[HH:MM:SS] - [Metric/Event]: [Value/Description]
```

### Post-Execution Checklist

- [ ] Injection stopped
- [ ] Metrics at baseline
- [ ] On-call notified of completion
- [ ] Initial findings documented

## Results

### Verdict

- [ ] **VALIDATED**: Hypothesis confirmed
- [ ] **INVALIDATED**: Hypothesis falsified
- [ ] **INCONCLUSIVE**: Unable to determine

### Summary

<!-- 2-3 sentence summary of what happened -->

### Metrics During Experiment

| Metric | Baseline | Peak During Injection | Recovery Time | Within Tolerance? |
|--------|----------|----------------------|---------------|-------------------|
| P99 Latency | {{BASELINE}}ms | {{PEAK}}ms | {{RECOVERY}}s | YES / NO |
| Error Rate | {{BASELINE}}% | {{PEAK}}% | {{RECOVERY}}s | YES / NO |
| {{CUSTOM}} | {{BASELINE}} | {{PEAK}} | {{RECOVERY}} | YES / NO |

### Findings

#### Resilience Strengths

1. {{STRENGTH_1}}
2. {{STRENGTH_2}}

#### Weaknesses Discovered

| ID | Finding | Severity | Ticket |
|----|---------|----------|--------|
| W1 | {{WEAKNESS_1}} | critical / high / medium / low | {{TICKET_URL}} |
| W2 | {{WEAKNESS_2}} | critical / high / medium / low | {{TICKET_URL}} |

#### Monitoring Gaps

1. {{GAP_1}}
2. {{GAP_2}}

#### Unexpected Behaviors

1. {{UNEXPECTED_1}}
2. {{UNEXPECTED_2}}

### Action Items

| Priority | Action | Owner | Due Date | Status |
|----------|--------|-------|----------|--------|
| P0 | {{ACTION_1}} | {{OWNER}} | {{DATE}} | TODO / IN_PROGRESS / DONE |
| P1 | {{ACTION_2}} | {{OWNER}} | {{DATE}} | TODO / IN_PROGRESS / DONE |

## Follow-Up Experiments

Based on these findings, consider:

1. {{FOLLOW_UP_1}}
2. {{FOLLOW_UP_2}}

## Appendix

### Raw Data

<!-- Link to or include raw metrics data -->

### Screenshots

<!-- Dashboard screenshots during the experiment -->

### Related Documents

- Incident Report: {{INCIDENT_URL}}
- Architecture Doc: {{ARCH_DOC_URL}}
- Runbook: {{RUNBOOK_URL}}

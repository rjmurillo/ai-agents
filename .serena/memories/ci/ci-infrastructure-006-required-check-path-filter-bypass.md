# Ci Infrastructure: Required Check Path Filter Bypass

## Skill-CI-Infrastructure-006: Required Check Path Filter Bypass

**Statement**: Use workflow_dispatch to manually trigger required checks blocked by path filters

**Atomicity**: 89%

**Context**: PR blocked by required status check that won't trigger due to path filters

**Evidence**: PR #298 - YAML-only changes don't trigger Pester Tests (PowerShell path filter), manually triggered via workflow_dispatch, tests passed and PR unblocked

**Trigger**: PR shows "Waiting for status to be reported" for required check that won't run due to path filters

**Command**: `gh workflow run pester-tests.yml --ref <branch-name>`

**Related Skills**:
- Skill-CI-Infrastructure-004 (label/check validation before deployment)
- skills-dorny-paths-filter-checkout-requirement

**SMART Validation**:
- Specific: Y - One concept: manual workflow trigger workaround
- Measurable: Y - PR #298 unblocked, tests passed
- Attainable: Y - workflow_dispatch available via gh CLI
- Relevant: Y - Applies when required checks have path filters
- Timely: Y - Trigger: PR blocked by required check that won't run

## Related

- [ci-infrastructure-001-fail-fast-infrastructure-failures](ci-infrastructure-001-fail-fast-infrastructure-failures.md)
- [ci-infrastructure-002-explicit-retry-timing](ci-infrastructure-002-explicit-retry-timing.md)
- [ci-infrastructure-003-job-status-verdict-distinction](ci-infrastructure-003-job-status-verdict-distinction.md)
- [ci-infrastructure-004-error-message-investigation](ci-infrastructure-004-error-message-investigation.md)
- [ci-infrastructure-aggregate-job-always-pattern](ci-infrastructure-aggregate-job-always-pattern.md)

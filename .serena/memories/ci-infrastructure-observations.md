# Skill Observations: ci-infrastructure

**Last Updated**: 2026-01-16
**Sessions Analyzed**: 1

## Purpose

This memory captures learnings from CI/CD workflows, GitHub Actions, and infrastructure patterns across sessions.

## Constraints (HIGH confidence)

These are corrections that MUST be followed:

- always() controls WHEN condition is evaluated, not WHETHER job runs - always() && false still skips the job (Session 2026-01-16-session-07, 2026-01-16)

## Preferences (MED confidence)

These are preferences that SHOULD be followed:

- Comments should reference bug tracking numbers for workarounds (bpo-XXXXX / GH issue #YYYY) (Session 2026-01-16-session-07, 2026-01-16)

## Edge Cases (MED confidence)

These are scenarios to handle:

- Aggregation metrics must distinguish unique items vs total operations (Session 2026-01-16-session-07, 2026-01-16)

## Notes for Review (LOW confidence)

These are observations that may become patterns:

## History

| Date | Session | Type | Learning |
|------|---------|------|----------|
| 2026-01-16 | 2026-01-16-session-07 | HIGH | always() controls evaluation timing, not whether job runs |
| 2026-01-16 | 2026-01-16-session-07 | MED | Comments should reference bug tracking numbers |
| 2026-01-16 | 2026-01-16-session-07 | MED | Aggregation metrics: unique items vs total operations |

## Related

- [ci-infrastructure-001-fail-fast-infrastructure-failures](ci-infrastructure-001-fail-fast-infrastructure-failures.md)
- [ci-infrastructure-002-explicit-retry-timing](ci-infrastructure-002-explicit-retry-timing.md)
- [ci-infrastructure-003-job-status-verdict-distinction](ci-infrastructure-003-job-status-verdict-distinction.md)
- [ci-infrastructure-004-error-message-investigation](ci-infrastructure-004-error-message-investigation.md)
- [ci-infrastructure-ai-integration](ci-infrastructure-ai-integration.md)
- [ci-infrastructure-claude-code-action-installer-race-condition](ci-infrastructure-claude-code-action-installer-race-condition.md)
- [ci-infrastructure-deployment-validation](ci-infrastructure-deployment-validation.md)
- [ci-infrastructure-dorny-paths-filter-checkout](ci-infrastructure-dorny-paths-filter-checkout.md)
- [ci-infrastructure-environment-simulation](ci-infrastructure-environment-simulation.md)
- [ci-infrastructure-matrix-artifacts](ci-infrastructure-matrix-artifacts.md)
- [ci-infrastructure-milestone-tracking](ci-infrastructure-milestone-tracking.md)
- [ci-infrastructure-output-handling](ci-infrastructure-output-handling.md)
- [ci-infrastructure-quality-gates](ci-infrastructure-quality-gates.md)
- [ci-infrastructure-runner-selection](ci-infrastructure-runner-selection.md)
- [ci-infrastructure-test-runner-artifacts](ci-infrastructure-test-runner-artifacts.md)
- [ci-infrastructure-workflow-required-checks](ci-infrastructure-workflow-required-checks.md)
- [ci-infrastructure-yaml-shell-patterns](ci-infrastructure-yaml-shell-patterns.md)
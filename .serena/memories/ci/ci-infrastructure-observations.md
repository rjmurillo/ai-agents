# Skill Observations: ci-infrastructure

**Last Updated**: 2026-01-18
**Sessions Analyzed**: 5

## Purpose

This memory captures learnings from CI/CD workflows, GitHub Actions, and infrastructure patterns across sessions.

## Constraints (HIGH confidence)

These are corrections that MUST be followed:

- always() controls WHEN condition is evaluated, not WHETHER job runs - always() && false still skips the job (Session 2026-01-16-session-07, 2026-01-16)
- Aggregate jobs must use `always() &&` condition to run even when dependencies fail - prevents enforcement bypass when validation fails (Session 01, 2026-01-11)
  - Evidence: Session protocol validation aggregate job missing always() at line 250, allowing bypass when validate job failed
  - Reference pattern: ai-pr-quality-gate.yml line 308 shows correct usage

## Preferences (MED confidence)

These are preferences that SHOULD be followed:

- Comments should reference bug tracking numbers for workarounds (bpo-XXXXX / GH issue #YYYY) (Session 2026-01-16-session-07, 2026-01-16)
- VS Code MCP config uses .vscode/mcp.json with 'servers' root key (not mcp.json in project root) - scripts should auto-create .vscode/ directory if missing (Session 01, 2025-12-17)
  - Evidence: Sync-McpConfig.ps1 updated default destination from mcp.json to .vscode/mcp.json for VS Code compatibility
- Self-referential copy prevention in installation scripts - check source != destination before file operations (Session 03, 2026-01-16)
  - Evidence: Batch 36 - Installation script failed copying file to itself, added source/destination comparison check
- Cross-platform testing matrix needed for Windows/Linux/macOS to catch platform-specific issues early (Session 2, 2026-01-15)
  - Evidence: Batch 37 - Platform-specific bugs found in CI that local testing missed, matrix coverage recommended

## Edge Cases (MED confidence)

These are scenarios to handle:

- Aggregation metrics must distinguish unique items vs total operations (Session 2026-01-16-session-07, 2026-01-16)

## Notes for Review (LOW confidence)

These are observations that may become patterns:

## History

| Date | Session | Type | Learning |
|------|---------|------|----------|
| 2026-01-16 | 2026-01-16-session-07 | HIGH | always() controls evaluation timing, not whether job runs |
| 2026-01-11 | Session 01 | HIGH | Aggregate jobs must use always() && to prevent bypass |
| 2026-01-16 | 2026-01-16-session-07 | MED | Comments should reference bug tracking numbers |
| 2025-12-17 | Session 01 | MED | VS Code MCP config .vscode/mcp.json with servers root key |
| 2026-01-16 | Session 03 | MED | Self-referential copy prevention in installation scripts |
| 2026-01-15 | Session 2 | MED | Cross-platform testing matrix for early issue detection |
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

# GitHub Actions Local Testing Integration

**Date**: 2026-01-09
**Source**: Research session on workflow validation shift-left
**Analysis**: `.agents/analysis/github-actions-local-testing-research.md`

## Integration Summary

Research evaluated tools for local GitHub Actions validation to reduce the expensive push-check-tweak OODA loop.

## Tool Recommendations

| Tool | Priority | Use Case | Adoption |
|------|----------|----------|----------|
| **actionlint** | P0 | Workflow YAML validation | Add to pre-commit hook |
| **act (nektos)** | P1 | PowerShell workflow testing | Use selectively |
| **yamllint** | P2 | YAML style consistency | Secondary linter |
| **act-test-runner** | P3 | E2E workflow testing | Do not adopt (TypeScript violates ADR-005) |

## Key Findings

1. **40% Session Protocol failure rate** - Preventable with local validation
2. **actionlint catches 80%+ workflow YAML errors** - Zero runtime cost
3. **act supports PowerShell** via `pwsh -command` with `$ErrorActionPreference = 'stop'`
4. **Windows runners require workaround** - Use `-P windows-latest=-self-hosted`
5. **AI workflows cannot shift left** - Require Copilot CLI infrastructure

## Implementation Actions

1. Add actionlint to `.pre-commit-config.yaml`
2. Create `scripts/Validate-All.ps1` unified runner
3. Document shift-left workflow in `.agents/SHIFT-LEFT.md`
4. Pilot act with pester-tests.yml and validate-paths.yml

## Projected Impact

- 80%+ workflow YAML errors caught locally
- 50-66% reduction in PR iteration count
- 60% reduction in AI review token consumption

## Related Memories

- `pattern-thin-workflows`: Keep workflows thin, move logic to testable modules
- `quality-shift-left-gate`: 6-agent consultation pattern pre-push
- `validation-pre-pr-checklist`: Local validation steps before PR
- `ci-infrastructure-quality-gates`: Pre-commit syntax validation

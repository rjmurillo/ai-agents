# GitHub Actions Local Testing Integration

**Date**: 2026-01-09
**Source**: Research session on workflow validation shift-left
**Analysis**: `.agents/analysis/github-actions-local-testing-research.md`

> **IMPORTANT (2026-08-25, issue #5201)**: the `act-test-runner` row below
> rejects TypeScript as an "ADR-005 violation". ADR-005 (PowerShell-only
> scripting) was superseded by ADR-042 (Python migration) on 2026-01-17, so
> citing ADR-005 for that rejection is wrong on its own. ADR-042's own text
> (`.agents/architecture/ADR-042-python-migration-strategy.md:165-168,228`)
> proposes, but has not accepted, a further amendment permitting TypeScript
> for user-facing distribution surfaces: that amendment's `### Status` reads
> `Proposed` and its Amendment Log entry reads `Pending adr-review`. Until
> that amendment is accepted, ADR-042's original Python-first mandate is
> still current policy for this row, not a blanket TypeScript exception.
> Re-evaluate this row's adoption recommendation against ADR-042's accepted
> text (and re-check the amendment's status, in case it has since been
> accepted) rather than the superseded ADR-005 rule quoted here (Copilot
> review on PR #5283).

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

1. Add actionlint to .pre-commit-config.yaml (removed)
2. Create `scripts/Validate-PrePR.ps1` unified runner (since migrated to `scripts/validation/pre_pr.py`)
3. Document shift-left workflow in `.agents/SHIFT-LEFT.md`
4. Pilot act with pester-tests.yml and validate-paths.yml

## Projected Impact

- 80%+ workflow YAML errors caught locally
- 50-66% reduction in PR iteration count
- 60% reduction in AI review token consumption

## Related Memories

- [pattern-thin-workflows](pattern-thin-workflows.md): Keep workflows thin, move logic to testable modules
- [quality-shift-left-gate](quality-shift-left-gate.md): 6-agent consultation pattern pre-push
- [validation-pre-pr-checklist](validation-pre-pr-checklist.md): Local validation steps before PR
- [ci-infrastructure-quality-gates](ci-infrastructure-quality-gates.md): Pre-commit syntax validation

## Related

- [github-cli-001-bidirectional-issue-linking](github-cli-001-bidirectional-issue-linking.md)
- [github-cli-anti-patterns](github-cli-anti-patterns.md)
- [github-cli-api-patterns](github-cli-api-patterns.md)
- [github-cli-extensions](github-cli-extensions.md)
- [github-cli-issue-operations](github-cli-issue-operations.md)

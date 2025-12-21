---
number: 197
title: "chore: Audit workflows for ARM runner migration (ubuntu-24.04-arm)"
state: OPEN
created_at: 12/20/2025 13:36:01
author: rjmurillo-bot
labels: ["enhancement"]
assignees: []
milestone: null
url: https://github.com/rjmurillo/ai-agents/issues/197
---

# chore: Audit workflows for ARM runner migration (ubuntu-24.04-arm)

## Summary

Per ADR-007 (GitHub Actions Runner Selection), all workflows MUST use `ubuntu-24.04-arm` unless documented ARM compatibility issues exist. This issue tracks the audit and migration of existing workflows.

## Cost Impact

| Runner | Cost/Min | Savings vs x64 |
|--------|----------|----------------|
| `ubuntu-latest` (x64) | $0.008 | baseline |
| `ubuntu-24.04-arm` | $0.005 | **37.5%** |

## Audit Scope

Analyze all `.github/workflows/*.yml` files for:
1. Current runner configuration
2. Tools/dependencies that may have ARM compatibility issues
3. Docker images that may not have ARM variants

## Workflows to Audit

```bash
find .github/workflows -name "*.yml" -exec grep -l "runs-on:" {} \;
```

## Migration Checklist Template

For each workflow:
- [ ] Identify current runner
- [ ] Test on `ubuntu-24.04-arm`
- [ ] Document any compatibility issues
- [ ] Add ADR-007 comment if non-ARM is required
- [ ] Update runner configuration

## Acceptance Criteria

- [ ] All workflows audited
- [ ] ARM-compatible workflows migrated
- [ ] Non-ARM workflows documented with justification comments
- [ ] PR created with all changes

## References

- [ADR-007: GitHub Actions Runner Selection](/.agents/architecture/ADR-007-github-actions-runner-selection.md)
- [COST-GOVERNANCE.md](/.agents/governance/COST-GOVERNANCE.md)
- [GitHub ARM Runner Docs](https://docs.github.com/en/actions/using-github-hosted-runners/about-github-hosted-runners/about-github-hosted-runners#standard-github-hosted-runners-for-public-repositories)


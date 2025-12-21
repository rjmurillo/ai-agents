---
number: 195
title: "chore: P0 - GitHub Actions cost audit and optimization"
state: OPEN
created_at: 12/20/2025 12:48:34
author: rjmurillo-bot
labels: ["enhancement", "priority:P0"]
assignees: []
milestone: null
url: https://github.com/rjmurillo/ai-agents/issues/195
---

# chore: P0 - GitHub Actions cost audit and optimization

## Context

**Current metered usage**: $243.55 (December 2025)
**Projected monthly cost**: $500+ USD
**Target**: <$100/month

This is an urgent cost issue requiring immediate attention.

## Immediate Actions Required (P0)

### 1. Migrate All Workflows to ARM Runners
- Change `ubuntu-latest` → `ubuntu-24.04-arm` (37.5% savings)
- Document any ARM incompatibilities

### 2. Add Path Filters to All Workflows
Prevent workflows from running on irrelevant file changes:
```yaml
on:
  push:
    paths:
      - 'relevant-path/**'
```

### 3. Add Concurrency Groups
Cancel duplicate runs:
```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

### 4. Audit Artifact Storage
- Reduce retention periods to minimum
- Remove unjustified artifact uploads
- Add compression to text artifacts

## Acceptance Criteria

- [ ] All workflows audited for runner type
- [ ] ARM migration complete (or documented exceptions)
- [ ] Path filters added to all workflows
- [ ] Concurrency groups added
- [ ] Artifact retention reduced
- [ ] Cost reduction verified (target: 50%+ reduction)

## References

- ADR-007: GitHub Actions Runner Selection
- ADR-008: Artifact Storage Minimization
- COST-GOVERNANCE.md

## Priority

**P0 (URGENT)** - Monthly cost will exceed $500 without intervention

## Effort Estimate

2-3 hours for complete audit and migration


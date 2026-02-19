# Skill-Cost-004: Concurrency Cancels Duplicates

**Statement**: Use concurrency to cancel duplicate workflow runs on same branch

**Context**: When writing GitHub Actions workflows that may receive rapid pushes

**Action Pattern**:
- SHOULD add `concurrency:` block with workflow+ref grouping
- SHOULD set `cancel-in-progress: true`
- MUST use pattern: `${{ github.workflow }}-${{ github.ref }}`

**Trigger Condition**:
- Workflow runs on branches with frequent force-pushes
- PR receives multiple commits in quick succession

**Evidence**:
- COST-GOVERNANCE.md lines 114-122
- ADR optimization table line 84

**Quantified Savings**:
- 10-20% reduction in redundant runs
- Prevents wasted runner time on superseded commits
- For 50 runs/month with 5 duplicates: 50 → 45 runs
- At $0.05/run (10 min): $2.50/month → $2.25/month

**RFC 2119 Level**: SHOULD (COST-GOVERNANCE line 19)

**Atomicity**: 97%

**Tag**: helpful

**Impact**: 7/10

**Created**: 2025-12-20

**Validated**: 1 (COST-GOVERNANCE policy)

**Category**: CI/CD Cost Optimization

**Pattern**:
```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

**Use Case**: Particularly valuable for:
- Long-running test suites
- Build workflows on active PR branches
- Workflows triggered by every commit

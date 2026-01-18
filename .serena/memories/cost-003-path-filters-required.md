# Skill-Cost-003: Path Filters Required

**Statement**: Add path filters to all workflows to prevent unnecessary runs

**Context**: When creating or modifying GitHub Actions workflows

**Action Pattern**:
- MUST include `paths:` filter on `push:` and `pull_request:` triggers
- MUST include workflow file itself in paths filter
- MUST scope to relevant source directories only
- SHOULD use negative patterns to exclude irrelevant paths

**Trigger Condition**:
- Creating new workflow file
- Workflow runs on every commit regardless of file changes

**Evidence**:
- COST-GOVERNANCE.md lines 96-112
- ADR optimization table line 81

**Quantified Savings**:
- 40-60% fewer workflow runs
- For 100 runs/month with avg 10 min each: 1000 min → 500 min
- At $0.005/min ARM: $5/month → $2.50/month = $2.50/month saved per workflow

**RFC 2119 Level**: MUST (COST-GOVERNANCE line 18)

**Atomicity**: 95%

**Tag**: helpful

**Impact**: 9/10

**Created**: 2025-12-20

**Validated**: 1 (COST-GOVERNANCE policy)

**Category**: CI/CD Cost Optimization

**Pattern**:
```yaml
on:
  push:
    branches: [main]
    paths:
      - 'src/**'
      - 'tests/**'
      - '.github/workflows/this-workflow.yml'
  pull_request:
    branches: [main]
    paths:
      - 'src/**'
      - 'tests/**'
      - '.github/workflows/this-workflow.yml'
```

**Negative Pattern** (exclude docs-only changes):
```yaml
on:
  push:
    branches: [main]
    paths-ignore:
      - 'docs/**'
      - '**.md'
      - 'LICENSE'
```

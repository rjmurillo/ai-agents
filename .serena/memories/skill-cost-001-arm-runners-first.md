# Skill-Cost-001: ARM Runners First

**Statement**: Use ubuntu-24.04-arm for new GitHub Actions workflows

**Context**: When creating or modifying GitHub Actions workflow files

**Action Pattern**: 
- MUST use `runs-on: ubuntu-24.04-arm` as default runner
- MUST NOT use `ubuntu-latest` unless ARM compatibility issue documented
- MUST include ADR-007 comment explaining runner choice

**Trigger Condition**: 
- Creating new `.github/workflows/*.yml` file
- Modifying existing workflow runner selection

**Evidence**: 
- ADR-007 GitHub Actions Runner Selection
- COST-GOVERNANCE.md sections 8-34

**Quantified Savings**: 
- 37.5% reduction in runner costs
- $0.005/min vs $0.008/min for ubuntu-latest
- For 100 hours/month: $30/month vs $48/month = $18/month saved

**RFC 2119 Level**: MUST (ADR-007 line 44)

**Atomicity**: 98%

**Tag**: helpful

**Impact**: 9/10

**Created**: 2025-12-20

**Validated**: 2 (ADR-007 acceptance, COST-GOVERNANCE policy)

**Category**: CI/CD Cost Optimization

**Example**:
```yaml
jobs:
  build:
    # ADR-007: Use ARM runner for cost efficiency (37.5% savings)
    runs-on: ubuntu-24.04-arm
```

**Fallback Pattern**:
```yaml
jobs:
  build:
    # ADR-007: Using x64 due to [specific tool] ARM incompatibility
    # TODO: Re-evaluate when [tool] adds ARM support
    runs-on: ubuntu-latest
```

# Skill-Cost-010: Avoid Windows Runners Unless Required

**Statement**: MUST NOT use windows-latest unless Windows-specific testing required

**Context**: When selecting runner type for GitHub Actions workflows

**Action Pattern**:
- MUST NOT use `runs-on: windows-latest` without Windows-specific justification
- MUST document Windows-only requirement in ADR-007 exception
- SHOULD use PowerShell Core on Linux ARM instead when possible
- MUST verify tool requires Windows, not just PowerShell

**Trigger Condition**:
- Workflow needs to run PowerShell scripts
- Considering Windows runner for non-Windows-specific task

**Evidence**:
- ADR-007 lines 46-47, 54
- COST-GOVERNANCE.md lines 33-34

**Quantified Savings**:
- Windows: $0.016/min vs ARM: $0.005/min (69% cost premium)
- Example: 100 hours/month
  - Windows: 6000 min × $0.016 = $96/month
  - ARM: 6000 min × $0.005 = $30/month
  - Savings: $66/month per workflow

**RFC 2119 Level**: MUST NOT (ADR-007 line 46)

**Atomicity**: 97%

**Tag**: helpful

**Impact**: 9/10

**Created**: 2025-12-20

**Validated**: 2 (ADR-007, COST-GOVERNANCE)

**Category**: CI/CD Cost Optimization

**Valid Windows Use Cases**:
- Windows-specific APIs (not available on PowerShell Core)
- .NET Framework (not .NET Core/6+)
- Windows-only tools with no Linux alternative
- Testing Windows-specific behavior

**Invalid Windows Use Cases**:
```yaml
# WRONG: PowerShell runs fine on Linux
jobs:
  test:
    runs-on: windows-latest  # 3.2x more expensive than ARM
    steps:
      - run: pwsh ./test.ps1  # This works on ubuntu-24.04-arm
```

**Correct Pattern**:
```yaml
# CORRECT: PowerShell Core on ARM
jobs:
  test:
    # ADR-007: PowerShell Core cross-platform, ARM sufficient
    runs-on: ubuntu-24.04-arm
    steps:
      - run: pwsh ./test.ps1
```

# CI Runner Selection

## Skill-CI-Runner-001: Prefer Linux Runners (95%)

**Statement**: Prefer ubuntu-latest over windows-latest for GitHub Actions - MUCH faster.

**Evidence**: User feedback PR #47: "prefer 'linux-latest' runners. MUCH faster"

**Exceptions**:

- PowerShell Desktop required (not pwsh/PowerShell Core)
- Windows-specific features or APIs needed
- Testing Windows-only behavior

**Pattern**:

```yaml
# Default: Use Linux
jobs:
  build:
    runs-on: ubuntu-latest

# Exception: Windows-specific testing
  windows-test:
    runs-on: windows-latest
    if: needs.check.outputs.windows-required == 'true'
```

**ARM Runners** (cost optimization):

```yaml
# 37% cheaper than x64
runs-on: ubuntu-24.04-arm
```

**Speed Comparison**:

| Runner | Startup | Cost |
|--------|---------|------|
| ubuntu-latest | ~10s | Base |
| windows-latest | ~45s | 2x |
| ubuntu-arm | ~12s | 0.63x |

# Test Location Standards

This document defines where test files should be located in the ai-agents repository.

## Directory Structure

```text
ai-agents/
  tests/                          # All Pester test files
    *.Tests.ps1                   # Test files following Pester naming convention
  .claude/skills/github/
    scripts/                      # Production PowerShell scripts
    modules/                      # PowerShell modules
```

## Test File Location Rules

### Rule 1: All tests in /tests directory

All Pester test files MUST be placed in the `/tests/` directory at the repository root.

**Rationale:**

- Centralized location makes test discovery simple
- CI/CD workflows can easily target a single directory
- Separation of concerns between production code and test code
- Follows PowerShell community conventions

### Rule 2: Test file naming convention

Test files MUST follow the pattern: `{ScriptName}.Tests.ps1`

**Examples:**

| Script | Test File |
|--------|-----------|
| `Invoke-CopilotAssignment.ps1` | `Invoke-CopilotAssignment.Tests.ps1` |
| `Get-PRContext.ps1` | `Get-PRContext.Tests.ps1` |

### Rule 3: Module tests

Module tests should be named after the module: `{ModuleName}.Tests.ps1`

**Example:** `GitHubHelpers.Tests.ps1` for the GitHubHelpers.psm1 module.

### Rule 4: Path references in tests

Tests MUST use relative paths from the test file to locate production code.

```powershell
BeforeAll {
    $repoRoot = Join-Path $PSScriptRoot ".."
    $scriptPath = Join-Path $repoRoot ".claude" "skills" "github" "scripts" "issue" "ScriptName.ps1"
}
```

## Test Types and Organization

### Pattern-based tests

Verify code structure, naming conventions, and presence of required elements. These tests read the script content and match against patterns.

```powershell
It "Has IssueNumber as mandatory parameter" {
    $scriptContent | Should -Match '\[Parameter\(Mandatory\)\]'
}
```

### Functional tests

Test actual function behavior with mock data. These tests extract functions from scripts and invoke them with test inputs.

```powershell
It "Returns null for empty comments array" {
    $result = Get-MaintainerGuidance -Comments @() -Maintainers @("user")
    $result | Should -BeNullOrEmpty
}
```

### Integration tests

Test multiple components working together. These may require mocking external dependencies like `gh` CLI.

## CI/CD Integration

The Pester tests workflow discovers tests via:

```yaml
- name: Run Pester Tests
  run: |
    Invoke-Pester -Path tests/ -CI -Output Detailed
```

## Exceptions

No exceptions to these standards are currently defined. If a new pattern emerges that requires tests in a different location, update this document first.

## Related Documents

- [AGENTS.md](../../AGENTS.md) - Main project documentation
- [powershell-testing-patterns](../../.serena/memories/powershell-testing-patterns.md) - Testing patterns memory

# Testable Workflow Authorization Pattern

**Importance**: CRITICAL  
**Date**: 2026-01-04  
**Scope**: Workflow security, ADR-006 compliance

## The Pattern

When workflows need authorization logic, **ALWAYS use PowerShell scripts, NEVER inline YAML conditionals.**

### Two-Job Pattern

```yaml
jobs:
  check-authorization:
    runs-on: ubuntu-latest
    outputs:
      authorized: ${{ steps.auth-check.outputs.authorized }}
    steps:
      - uses: actions/checkout@hash
      - shell: pwsh
        env:
          # Pass ALL untrusted input via environment variables
          USER_INPUT: ${{ github.event.comment.body }}
        run: |
          $result = & ./scripts/workflows/Check-Authorization.ps1 -Input $env:USER_INPUT
          "authorized=$result" | Out-File -Append $env:GITHUB_OUTPUT

  main-job:
    needs: check-authorization
    if: needs.check-authorization.outputs.authorized == 'true'
    steps:
      # ... main workflow logic
```

## Why This Matters

### ADR-006 Violation Example (BAD)

```yaml
if: |
  (
    github.event_name == 'issue_comment' &&
    contains(github.event.comment.body, '@trigger') &&
    contains(fromJson('["MEMBER","OWNER"]'), github.event.comment.author_association)
  ) ||
  # ... 20 more lines of untestable logic
```

**Problems**:
- ❌ Untestable (can't unit test YAML)
- ❌ Undebuggable (no breakpoints, no variable inspection)
- ❌ Silent failures (fromJson() errors invisible)
- ❌ No error handling (YAML has no try-catch)
- ❌ No audit logging
- ❌ Can't validate without workflow runs

### Compliant Pattern (GOOD)

```powershell
# scripts/workflows/Check-Authorization.ps1
[CmdletBinding()]
param([string]$Input)

$ErrorActionPreference = 'Stop'

try {
    # Authorization logic here
    $isAuthorized = Test-Authorization -Input $Input

    # Audit log
    if ($env:GITHUB_STEP_SUMMARY) {
        "## Authorization: $isAuthorized" | Add-Content $env:GITHUB_STEP_SUMMARY
    }

    Write-Output $isAuthorized.ToString().ToLower()
    exit 0
} catch {
    Write-Error "Auth failed: $_"
    exit 1
}
```

**Benefits**:
- ✅ Testable (Pester tests)
- ✅ Debuggable (breakpoints, variable inspection)
- ✅ Error handling (try-catch with exit codes)
- ✅ Audit logging (GitHub Actions summary)
- ✅ Validated locally (no workflow runs needed)

## Command Injection Prevention

**CRITICAL**: NEVER use string interpolation for GitHub event data.

### Unsafe (DO NOT DO THIS)

```yaml
run: |
  ./script.ps1 -Title "${{ github.event.issue.title }}"
```

If issue title is: `"; rm -rf / #`, this becomes:
```bash
./script.ps1 -Title ""; rm -rf / #"
```

### Safe Pattern

```yaml
env:
  ISSUE_TITLE: ${{ github.event.issue.title }}
run: |
  ./script.ps1 -Title $env:ISSUE_TITLE
```

PowerShell treats `$env:ISSUE_TITLE` as a single string value, preventing injection.

## Real-World Example

See: `.github/workflows/claude.yml` and `tests/workflows/Test-ClaudeAuthorization.ps1`

**Scenario**: Restrict Claude invocation to MEMBER/OWNER/COLLABORATOR or specific bots

**Implementation**:
- 27 Pester tests covering all scenarios
- Comprehensive error handling
- Audit logging to GitHub Actions summary
- Command injection safe (all inputs via env vars)
- Case-sensitive @claude mention detection

## When To Use

Use this pattern when:
- Authorization logic (who can trigger)
- Complex conditionals (more than simple property checks)
- String parsing (verdicts, labels, JSON)
- Any logic that needs testing

## Related

- ADR-006: No logic in workflow YAML
- `.agents/architecture/claude-workflow-authorization-pattern.md`: Full documentation
- Security guide: https://github.blog/security/vulnerability-research/how-to-catch-github-actions-workflow-injections-before-attackers-do/
- `security-012-workflow-author-association.md`: Previous pattern (replaced)

## Deprecation Note

GitHub may deprecate `author_association` from webhook payloads in the future (timeline not confirmed).
Plan migration to alternative authorization methods (team membership API, collaborator API, or GitHub Apps) when deprecation occurs.

## Testing Template

```powershell
# Check-Authorization.Tests.ps1
Describe 'Check-Authorization' {
    It 'Should authorize valid users' {
        $result = & ./Check-Authorization.ps1 -Input '@trigger'
        $result | Should -Be 'true'
        $LASTEXITCODE | Should -Be 0
    }

    It 'Should deny invalid users' {
        $result = & ./Check-Authorization.ps1 -Input 'no trigger'
        $result | Should -Be 'false'
        $LASTEXITCODE | Should -Be 0
    }

    It 'Should handle errors gracefully' {
        { & ./Check-Authorization.ps1 -Input $null -ErrorAction Stop } | Should -Throw
        $LASTEXITCODE | Should -Be 1
    }
}
```

## Enforcement

**Pre-commit validation**: Check for complex YAML conditionals

**Code review**: Flag any authorization logic in workflow YAML

**Required**: PowerShell script + Pester tests for all authorization workflows

## Migration Path

If you find inline YAML authorization:

1. Extract logic to `tests/workflows/Check-*.ps1`
2. Add comprehensive Pester tests
3. Update workflow to two-job pattern
4. Use environment variables for all GitHub event data
5. Add audit logging
6. Verify tests pass locally before pushing

## Related

- [workflow-false-positive-verdict-parsing-2025-12-28](workflow-false-positive-verdict-parsing-2025-12-28.md)
- [workflow-false-positive-verdict-parsing-fix-2025-12-28](workflow-false-positive-verdict-parsing-fix-2025-12-28.md)
- [workflow-patterns-batch-changes-reduce-cogs](workflow-patterns-batch-changes-reduce-cogs.md)
- [workflow-patterns-composite-action](workflow-patterns-composite-action.md)
- [workflow-patterns-matrix-artifacts](workflow-patterns-matrix-artifacts.md)

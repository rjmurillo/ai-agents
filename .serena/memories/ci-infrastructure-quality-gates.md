# CI Quality Gates

## Skill-CI-001: Pre-Commit Syntax Validation (92%)

**Statement**: Run static syntax analysis (PSScriptAnalyzer) in pre-commit hook to catch errors before commit.

**Evidence**: PR #79 - Get-PRContext.ps1 committed with syntax error, caught only at runtime.

```powershell
# .githooks/pre-commit
# Validates STAGED content (not working tree) to catch all committed errors
$stagedFiles = git diff --cached --name-only --diff-filter=ACM |
    Where-Object { $_ -match '\.ps1$' }

foreach ($file in $stagedFiles) {
    # Get staged content, not working tree file
    $stagedContent = git show ":$file"
    $result = Invoke-ScriptAnalyzer -ScriptDefinition $stagedContent -Severity Error
    if ($result) {
        Write-Host "Syntax errors in staged content: $file" -ForegroundColor Red
        $result | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
        exit 1
    }
}
```

**Why staged content matters**: Validating working tree files can miss errors when:

1. Developer stages broken code
2. Developer fixes the file in working tree (but doesn't re-stage)
3. Pre-commit passes because working tree is now valid
4. Broken staged content gets committed

## Skill-CI-Infrastructure-003: Quality Gate as Required Check (92%)

**Statement**: Make AI Quality Gate a required GitHub branch protection check, not manual trigger.

**Evidence**: PR #60 merged without Quality Gate, PR #211 manual trigger caught vulnerability.

```yaml
# Branch protection settings
required_status_checks:
  - "AI Quality Gate / security"
  - "AI Quality Gate / qa"
```

## Skill-CI-Integration-Test-001: Workflow Integration Testing (88%)

**Statement**: Test GitHub Actions workflows in dry-run mode before merging changes.

**Evidence**: PR #212 - First failure 5 hours post-merge on real issue creation.

```yaml
# .github/workflows/workflow-validation.yml
on:
  pull_request:
    paths:
      - '.github/workflows/**'
      - '.github/scripts/**'

jobs:
  validate:
    steps:
      - name: Test PowerShell modules
        shell: pwsh
        run: |
          Import-Module ./.github/scripts/AIReviewCommon.psm1
          Get-Command -Module AIReviewCommon
```

## Related

- [ci-infrastructure-001-fail-fast-infrastructure-failures](ci-infrastructure-001-fail-fast-infrastructure-failures.md)
- [ci-infrastructure-002-explicit-retry-timing](ci-infrastructure-002-explicit-retry-timing.md)
- [ci-infrastructure-003-job-status-verdict-distinction](ci-infrastructure-003-job-status-verdict-distinction.md)
- [ci-infrastructure-004-error-message-investigation](ci-infrastructure-004-error-message-investigation.md)
- [ci-infrastructure-ai-integration](ci-infrastructure-ai-integration.md)

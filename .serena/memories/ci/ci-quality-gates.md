# CI Quality Gates

## Skill-CI-001: Pre-Commit Syntax Validation (92%)

**Statement**: Run static syntax analysis (PSScriptAnalyzer) in pre-commit hook to catch errors before commit.

**Evidence**: PR #79 - Get-PRContext.ps1 committed with syntax error, caught only at runtime.

```powershell
# .githooks/pre-commit
$changedFiles = git diff --cached --name-only --diff-filter=ACM |
    Where-Object { $_ -match '\.ps1$' }

foreach ($file in $changedFiles) {
    $result = Invoke-ScriptAnalyzer -Path $file -Severity Error
    if ($result) {
        Write-Host "Syntax errors in $file" -ForegroundColor Red
        exit 1
    }
}
```

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

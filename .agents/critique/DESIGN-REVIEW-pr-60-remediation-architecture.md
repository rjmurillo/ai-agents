# Architecture Design Review: PR #60 Remediation Plan

**Reviewer**: Architect Agent
**Date**: 2025-12-18
**Subject**: Detailed architectural recommendations for PR #60 remediation plan
**Plan Reference**: [002-pr-60-remediation-plan.md](../planning/PR-60/002-pr-60-remediation-plan.md)

---

## Executive Summary

This review provides **specific, implementable designs** for the five architectural concerns raised during PR #60 remediation planning. Each section includes exact code patterns, file paths, and migration strategies.

---

## 1. Error Handling Architecture

### Problem Statement

The plan proposes replacing `|| true` with "explicit error handling" but does not define what that pattern looks like consistently across bash and PowerShell contexts.

### Architectural Decision

**Pattern**: Structured Result Aggregation with Deferred Failure

**Rationale**: Workflow steps should collect all errors, continue processing where safe, and report aggregated failures at the end. This prevents partial state (e.g., 2 of 5 labels applied) without visibility.

### Exact Implementation

#### 1.1 Bash Error Handling Wrapper

Create new file: `.github/scripts/gh-error-handler.sh`

```bash
#!/bin/bash
# gh-error-handler.sh - Standardized error handling for gh CLI operations

# Initialize error tracking (call at start of step)
init_error_tracking() {
    export GH_ERRORS=()
    export GH_WARNINGS=()
}

# Execute gh command with error capture (non-fatal)
# Usage: gh_safe "operation description" gh issue edit 123 --add-label "bug"
gh_safe() {
    local description="$1"
    shift
    local output
    local exit_code

    output=$("$@" 2>&1)
    exit_code=$?

    if [ $exit_code -ne 0 ]; then
        GH_ERRORS+=("$description: $output (exit $exit_code)")
        echo "::warning::$description failed: $output"
        return 1
    fi
    return 0
}

# Execute gh command (fatal - stops workflow on failure)
# Usage: gh_required "operation description" gh auth status
gh_required() {
    local description="$1"
    shift
    local output
    local exit_code

    output=$("$@" 2>&1)
    exit_code=$?

    if [ $exit_code -ne 0 ]; then
        echo "::error::$description failed: $output"
        exit 1
    fi
    echo "$output"
}

# Report aggregated errors at step end
# Returns: 0 if no errors, 1 if errors exist
report_errors() {
    local error_count=${#GH_ERRORS[@]}

    if [ $error_count -gt 0 ]; then
        echo "::group::Error Summary ($error_count failures)"
        for error in "${GH_ERRORS[@]}"; do
            echo "  - $error"
        done
        echo "::endgroup::"

        # Write to job summary
        {
            echo "### Error Summary"
            echo ""
            echo "| Operation | Error |"
            echo "|-----------|-------|"
            for error in "${GH_ERRORS[@]}"; do
                echo "| ${error%%:*} | ${error#*:} |"
            done
        } >> "$GITHUB_STEP_SUMMARY"

        return 1
    fi
    return 0
}
```

#### 1.2 Usage in Workflow

File: `.github/workflows/ai-issue-triage.yml`

```yaml
- name: Apply Labels
  env:
    ISSUE_NUMBER: ${{ github.event.issue.number }}
    LABELS: ${{ steps.parse-categorize.outputs.labels }}
  run: |
    source .github/scripts/gh-error-handler.sh
    init_error_tracking

    if [ -n "$LABELS" ]; then
      for label in $LABELS; do
        # Validate label format first (security)
        if [[ ! "$label" =~ ^[a-zA-Z0-9._-]+$ ]]; then
          GH_ERRORS+=("Invalid label format: $label")
          continue
        fi

        # Create label if needed (warning on failure)
        gh_safe "Create label '$label'" \
          gh label create "$label" --description "Auto-created by AI triage" 2>/dev/null || true

        # Apply label (tracked error)
        gh_safe "Apply label '$label' to issue #$ISSUE_NUMBER" \
          gh issue edit "$ISSUE_NUMBER" --add-label "$label"
      done
    fi

    # Report errors but don't fail the step (labels are best-effort)
    report_errors || echo "::warning::Some labels could not be applied"
```

#### 1.3 PowerShell Equivalent Pattern

Add to: `.claude/skills/github/modules/GitHubHelpers.psm1`

```powershell
#region Error Aggregation

class GitHubOperationResult {
    [bool]$Success
    [string]$Operation
    [string]$Error
    [object]$Data

    GitHubOperationResult([string]$operation) {
        $this.Operation = $operation
        $this.Success = $true
    }
}

class GitHubErrorAggregator {
    [System.Collections.Generic.List[GitHubOperationResult]]$Results

    GitHubErrorAggregator() {
        $this.Results = [System.Collections.Generic.List[GitHubOperationResult]]::new()
    }

    [GitHubOperationResult] Execute([string]$operation, [scriptblock]$action) {
        $result = [GitHubOperationResult]::new($operation)
        try {
            $result.Data = & $action
            if ($LASTEXITCODE -ne 0) {
                $result.Success = $false
                $result.Error = "Exit code: $LASTEXITCODE"
            }
        }
        catch {
            $result.Success = $false
            $result.Error = $_.Exception.Message
        }
        $this.Results.Add($result)
        return $result
    }

    [bool] HasErrors() {
        return $this.Results | Where-Object { -not $_.Success } | Measure-Object | Select-Object -ExpandProperty Count -gt 0
    }

    [string] GetSummary() {
        $failed = $this.Results | Where-Object { -not $_.Success }
        if ($failed.Count -eq 0) { return "All operations succeeded" }

        $summary = "Failed operations:`n"
        foreach ($f in $failed) {
            $summary += "  - $($f.Operation): $($f.Error)`n"
        }
        return $summary
    }
}

function New-GitHubErrorAggregator {
    return [GitHubErrorAggregator]::new()
}

Export-ModuleMember -Function 'New-GitHubErrorAggregator'

#endregion
```

### Error Propagation Design

```
Workflow Step
    |
    +-- init_error_tracking()
    |
    +-- gh_safe() calls (non-fatal, collected)
    |       |
    |       +-- Success: continue
    |       +-- Failure: add to GH_ERRORS, emit ::warning::, continue
    |
    +-- gh_required() calls (fatal)
    |       |
    |       +-- Success: continue
    |       +-- Failure: emit ::error::, exit 1
    |
    +-- report_errors()
            |
            +-- Write summary to GITHUB_STEP_SUMMARY
            +-- Return exit code based on policy (fail-fast vs continue)
```

---

## 2. Module vs Script Exit Behavior

### Problem Statement

Task 1.4 proposes using `$MyInvocation.ScriptName` to detect context. This is **unreliable**.

### Why `$MyInvocation.ScriptName` Is Problematic

1. **Varies by invocation method**: Different when called via `&`, `.`, or `Import-Module`
2. **Empty in unexpected contexts**: Interactive sessions, `Invoke-Expression`, remoting
3. **Not intuitive**: Callers don't know what behavior to expect

### Architectural Decision

**Pattern**: Terminating Exceptions with Caller-Controlled Policy

**Principle**: Module functions should NEVER call `exit`. They throw typed exceptions. Scripts decide how to handle them.

### Exact Implementation

#### 2.1 Custom Exception Type

Add to: `.claude/skills/github/modules/GitHubHelpers.psm1`

```powershell
#region Custom Exceptions

class GitHubOperationException : System.Exception {
    [int]$ExitCode
    [string]$Operation

    GitHubOperationException([string]$message, [int]$exitCode) : base($message) {
        $this.ExitCode = $exitCode
        $this.Operation = "Unknown"
    }

    GitHubOperationException([string]$message, [int]$exitCode, [string]$operation) : base($message) {
        $this.ExitCode = $exitCode
        $this.Operation = $operation
    }
}

class GitHubAuthenticationException : GitHubOperationException {
    GitHubAuthenticationException([string]$message) : base($message, 4, "Authentication") {}
}

class GitHubResourceNotFoundException : GitHubOperationException {
    GitHubResourceNotFoundException([string]$message) : base($message, 2, "ResourceLookup") {}
}

class GitHubApiException : GitHubOperationException {
    GitHubApiException([string]$message) : base($message, 3, "ApiCall") {}
}

class GitHubValidationException : GitHubOperationException {
    GitHubValidationException([string]$message) : base($message, 1, "Validation") {}
}

#endregion
```

#### 2.2 Updated `Write-ErrorAndExit` (Deprecated)

```powershell
function Write-ErrorAndExit {
    <#
    .SYNOPSIS
        DEPRECATED: Use specific exception types instead.
        Throws GitHubOperationException for backward compatibility.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Message,

        [Parameter(Mandatory)]
        [int]$ExitCode
    )

    Write-Warning "Write-ErrorAndExit is deprecated. Use throw [GitHubOperationException] instead."

    throw [GitHubOperationException]::new($Message, $ExitCode)
}
```

#### 2.3 Script Entry Point Pattern

Scripts should follow this pattern:

```powershell
# Post-IssueComment.ps1 (entry point script)

[CmdletBinding()]
param(...)

# Set error action for script context
$ErrorActionPreference = 'Stop'

try {
    Import-Module (Join-Path $PSScriptRoot ".." ".." "modules" "GitHubHelpers.psm1") -Force

    # All module functions now throw exceptions
    Assert-GhAuthenticated  # throws GitHubAuthenticationException
    $resolved = Resolve-RepoParams -Owner $Owner -Repo $Repo  # throws GitHubValidationException

    # ... rest of script logic ...
}
catch [GitHubAuthenticationException] {
    Write-Error $_.Exception.Message
    exit $_.Exception.ExitCode  # 4
}
catch [GitHubValidationException] {
    Write-Error $_.Exception.Message
    exit $_.Exception.ExitCode  # 1
}
catch [GitHubApiException] {
    Write-Error $_.Exception.Message
    exit $_.Exception.ExitCode  # 3
}
catch [GitHubOperationException] {
    Write-Error $_.Exception.Message
    exit $_.Exception.ExitCode
}
catch {
    Write-Error "Unexpected error: $_"
    exit 99
}
```

#### 2.4 Updated Module Functions

```powershell
function Assert-GhAuthenticated {
    [CmdletBinding()]
    param()

    if (-not (Test-GhAuthenticated)) {
        throw [GitHubAuthenticationException]::new(
            "GitHub CLI (gh) is not installed or not authenticated. Run 'gh auth login' first."
        )
    }
}

function Assert-ValidBodyFile {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$BodyFile,

        [Parameter()]
        [string]$AllowedBase
    )

    if (-not (Test-Path $BodyFile)) {
        throw [GitHubResourceNotFoundException]::new("Body file not found: $BodyFile")
    }

    if ($AllowedBase -and -not (Test-SafeFilePath -Path $BodyFile -AllowedBase $AllowedBase)) {
        throw [GitHubValidationException]::new("Body file path traversal not allowed: $BodyFile")
    }
}
```

### Caller Behavior Contract

| Context | Behavior | How Caller Knows |
|---------|----------|------------------|
| Script (entry point) | Catches exception, calls `exit` with code | Script is responsible for exit |
| Module function | Exception propagates | Catch blocks in caller |
| Interactive | Exception displayed, session continues | PowerShell default |
| Pester test | Exception caught by Should -Throw | Test framework handles |

---

## 3. Security Function Integration Pattern

### Problem Statement

The plan says "update scripts to use security helpers" but doesn't define how to ensure NEW scripts automatically get protection.

### Architectural Decision

**Pattern**: Parameter Validation Attributes + Mandatory Security Pipeline

### Exact Implementation

#### 3.1 PowerShell ValidateScript Attributes

```powershell
# Define reusable validation attributes
class ValidateGitHubOwnerAttribute : System.Management.Automation.ValidateArgumentsAttribute {
    [void] Validate([object]$arguments, [System.Management.Automation.EngineIntrinsics]$engineIntrinsics) {
        $name = $arguments -as [string]
        if (-not [string]::IsNullOrWhiteSpace($name)) {
            if ($name -notmatch '^[a-zA-Z0-9]([a-zA-Z0-9-]{0,37}[a-zA-Z0-9])?$') {
                throw [System.Management.Automation.ValidationMetadataException]::new(
                    "Invalid GitHub owner name: $name. Must be 1-39 alphanumeric characters or hyphens, cannot start/end with hyphen."
                )
            }
        }
    }
}

class ValidateGitHubRepoAttribute : System.Management.Automation.ValidateArgumentsAttribute {
    [void] Validate([object]$arguments, [System.Management.Automation.EngineIntrinsics]$engineIntrinsics) {
        $name = $arguments -as [string]
        if (-not [string]::IsNullOrWhiteSpace($name)) {
            if ($name -notmatch '^[a-zA-Z0-9._-]{1,100}$') {
                throw [System.Management.Automation.ValidationMetadataException]::new(
                    "Invalid GitHub repository name: $name. Must be 1-100 alphanumeric characters, hyphens, underscores, or periods."
                )
            }
        }
    }
}

class ValidateSafeFilePathAttribute : System.Management.Automation.ValidateArgumentsAttribute {
    [void] Validate([object]$arguments, [System.Management.Automation.EngineIntrinsics]$engineIntrinsics) {
        $path = $arguments -as [string]
        if (-not [string]::IsNullOrWhiteSpace($path)) {
            if ($path -match '\.\.[/\\]') {
                throw [System.Management.Automation.ValidationMetadataException]::new(
                    "Path traversal not allowed: $path"
                )
            }
        }
    }
}
```

#### 3.2 Script Parameter Declaration Pattern

```powershell
# Post-IssueComment.ps1 - With automatic validation
[CmdletBinding(DefaultParameterSetName = 'BodyText')]
param(
    [ValidateGitHubOwner()]
    [string]$Owner,

    [ValidateGitHubRepo()]
    [string]$Repo,

    [Parameter(Mandatory)]
    [ValidateRange(1, [int]::MaxValue)]
    [int]$Issue,

    [Parameter(ParameterSetName = 'BodyText', Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string]$Body,

    [Parameter(ParameterSetName = 'BodyFile', Mandatory)]
    [ValidateSafeFilePath()]
    [ValidateScript({ Test-Path $_ -PathType Leaf })]
    [string]$BodyFile,

    [ValidatePattern('^[A-Za-z0-9_-]+$')]
    [string]$Marker
)
```

#### 3.3 Ensuring New Scripts Get Protection

**Strategy**: Script Template + CI Validation

Create: `.claude/skills/github/templates/script-template.ps1`

```powershell
<#
.SYNOPSIS
    [REPLACE: Brief description]

.DESCRIPTION
    [REPLACE: Detailed description]

.PARAMETER Owner
    Repository owner. Inferred from git remote if not provided.
    SECURITY: Validated against GitHub naming rules (CWE-78 mitigation).

.PARAMETER Repo
    Repository name. Inferred from git remote if not provided.
    SECURITY: Validated against GitHub naming rules (CWE-78 mitigation).

.NOTES
    Exit Codes: 0=Success, 1=Invalid params, 2=Resource not found, 3=API error, 4=Not authenticated
    Security: All inputs validated via parameter attributes
#>

#Requires -Version 7.0

[CmdletBinding()]
param(
    [ValidateGitHubOwner()]
    [string]$Owner,

    [ValidateGitHubRepo()]
    [string]$Repo

    # [REPLACE: Add script-specific parameters with appropriate validation]
)

$ErrorActionPreference = 'Stop'

try {
    Import-Module (Join-Path $PSScriptRoot ".." ".." "modules" "GitHubHelpers.psm1") -Force

    Assert-GhAuthenticated
    $resolved = Resolve-RepoParams -Owner $Owner -Repo $Repo
    $Owner = $resolved.Owner
    $Repo = $resolved.Repo

    # [REPLACE: Script logic here]

}
catch [GitHubAuthenticationException] {
    Write-Error $_.Exception.Message
    exit 4
}
catch [GitHubValidationException] {
    Write-Error $_.Exception.Message
    exit 1
}
catch [GitHubResourceNotFoundException] {
    Write-Error $_.Exception.Message
    exit 2
}
catch [GitHubApiException] {
    Write-Error $_.Exception.Message
    exit 3
}
catch {
    Write-Error "Unexpected error: $_"
    exit 99
}
```

#### 3.4 CI Validation for New Scripts

Add to: `.github/workflows/ci.yml`

```yaml
- name: Validate Script Security Patterns
  shell: pwsh
  run: |
    $scripts = Get-ChildItem -Path ".claude/skills/github/scripts" -Filter "*.ps1" -Recurse

    $violations = @()

    foreach ($script in $scripts) {
      $content = Get-Content $script.FullName -Raw

      # Check for required module import
      if ($content -notmatch 'Import-Module.*GitHubHelpers\.psm1') {
        $violations += "$($script.Name): Missing GitHubHelpers module import"
      }

      # Check for Owner/Repo validation attributes
      if ($content -match 'param\s*\(' -and $content -match '\[string\]\s*\$Owner') {
        if ($content -notmatch '\[ValidateGitHubOwner\(\)\]') {
          $violations += "$($script.Name): Owner parameter missing ValidateGitHubOwner attribute"
        }
      }

      # Check for BodyFile validation
      if ($content -match '\$BodyFile') {
        if ($content -notmatch '\[ValidateSafeFilePath\(\)\]') {
          $violations += "$($script.Name): BodyFile parameter missing ValidateSafeFilePath attribute"
        }
      }

      # Check for ErrorActionPreference
      if ($content -notmatch '\$ErrorActionPreference\s*=\s*[''"]Stop[''"]') {
        $violations += "$($script.Name): Missing ErrorActionPreference = 'Stop'"
      }
    }

    if ($violations.Count -gt 0) {
      Write-Error "Security validation failures:`n$($violations -join "`n")"
      exit 1
    }

    Write-Host "All scripts pass security validation" -ForegroundColor Green
```

---

## 4. PowerShell vs Bash Decision

### Architectural Decision

**Decision**: Standardize on PowerShell for all parsing and data manipulation; Bash only for simple command invocation.

### Rationale

| Criterion | PowerShell | Bash |
|-----------|------------|------|
| JSON parsing | Native (`ConvertFrom-Json`) | Requires `jq` |
| Error handling | Structured (try/catch) | Exit codes only |
| String manipulation | Safe by default | Shell expansion risks |
| Testing | Pester framework | Limited |
| Cross-platform | Full support | WSL/Git Bash variations |
| AI output parsing | Type-safe | Regex fragile |

### Exact Scope of Changes

#### Files to Convert to PowerShell

| File | Current | Convert? | Rationale |
|------|---------|----------|-----------|
| `.github/workflows/ai-issue-triage.yml` - "Parse Categorization Results" | Bash | YES | JSON parsing, regex |
| `.github/workflows/ai-issue-triage.yml` - "Parse Roadmap Results" | Bash | YES | JSON parsing |
| `.github/workflows/ai-issue-triage.yml` - "Apply Labels" | Bash | YES | Loop with validation |
| `.github/workflows/ai-issue-triage.yml` - "Assign Milestone" | Bash | YES | API call with validation |
| `.github/actions/ai-review/action.yml` - "Install Copilot CLI" | Bash | NO | npm install, simple |
| `.github/actions/ai-review/action.yml` - "Build context" | Bash | PARTIAL | gh commands, but complex parsing |
| `.github/actions/ai-review/action.yml` - "Parse output" | Bash | YES | Regex parsing |

#### Files to Keep as Bash

| File | Rationale |
|------|-----------|
| npm install steps | Simple shell commands |
| git operations | Native command interface |
| Environment variable exports | Shell-native |

### Migration Example

**Before** (Bash with `|| true`):
```bash
for label in $LABELS; do
  gh label create "$label" --description "Auto-created" || true
  gh issue edit "$ISSUE_NUMBER" --add-label "$label" || true
done
```

**After** (PowerShell with error aggregation):
```powershell
$aggregator = New-GitHubErrorAggregator

foreach ($label in $Labels -split '\s+') {
    # Validate
    if ($label -notmatch '^[a-zA-Z0-9._-]+$') {
        Write-Warning "Skipping invalid label: $label"
        continue
    }

    # Create (optional)
    $aggregator.Execute("Create label '$label'", {
        gh label create $label --description "Auto-created by AI triage" 2>$null
    }) | Out-Null

    # Apply (tracked)
    $aggregator.Execute("Apply label '$label'", {
        gh issue edit $env:ISSUE_NUMBER --add-label $label
    })
}

if ($aggregator.HasErrors()) {
    Write-Warning $aggregator.GetSummary()
}
```

### Maintenance Cost Analysis

| Approach | Initial Effort | Ongoing Maintenance | Risk |
|----------|----------------|---------------------|------|
| Keep mixed | 0 hours | High (two paradigms) | High (inconsistent error handling) |
| Full PowerShell | 8-12 hours | Low (one paradigm) | Low (testable, typed) |
| Minimal conversion | 4-6 hours | Medium | Medium |

**Recommendation**: Full conversion for all parsing steps. Keep bash only for `npm install`, `git` commands, and simple `gh` calls without output processing.

---

## 5. API Response Contract for Paginated Results

### Problem Statement

Task 3.2 proposes adding a completion indicator but doesn't define the contract or migration path.

### Current Contract

```powershell
function Invoke-GhApiPaginated {
    # Returns: [array] - Items from all pages
    return @($allItems)
}
```

### Proposed Contract

```powershell
function Invoke-GhApiPaginated {
    # Returns: [PSCustomObject] with Items, Complete, Error properties
    return [PSCustomObject]@{
        Items = @($allItems)
        Complete = $complete
        Error = $errorMessage
    }
}
```

### Architectural Decision

**Pattern**: Rich Result Object with Backward Compatibility Wrapper

### Exact Implementation

#### 5.1 New Return Type

```powershell
class PaginatedApiResult {
    [array]$Items
    [bool]$Complete
    [string]$Error
    [int]$PagesFetched
    [int]$TotalItems

    PaginatedApiResult() {
        $this.Items = @()
        $this.Complete = $false
        $this.Error = $null
        $this.PagesFetched = 0
        $this.TotalItems = 0
    }

    # Allow array-like access for backward compatibility
    [object] GetEnumerator() {
        return $this.Items.GetEnumerator()
    }

    [int] get_Count() {
        return $this.Items.Count
    }
}
```

#### 5.2 Updated Function

```powershell
function Invoke-GhApiPaginated {
    <#
    .SYNOPSIS
        Calls GitHub API with pagination support.

    .OUTPUTS
        PaginatedApiResult - Object with Items, Complete, Error, PagesFetched, TotalItems

    .NOTES
        BREAKING CHANGE in v2.0: Return type changed from [array] to [PaginatedApiResult].
        Use .Items property to access the array, or use -LegacyOutput for [array] return.
    #>
    [CmdletBinding()]
    [OutputType([PaginatedApiResult])]
    param(
        [Parameter(Mandatory)]
        [string]$Endpoint,

        [ValidateRange(1, 100)]
        [int]$PageSize = 100,

        # Backward compatibility switch
        [switch]$LegacyOutput
    )

    $result = [PaginatedApiResult]::new()
    $allItems = [System.Collections.Generic.List[object]]::new()
    $page = 1

    do {
        Write-Verbose "Fetching page $page from $Endpoint"

        $separator = if ($Endpoint -match '\?') { '&' } else { '?' }
        $url = "$Endpoint${separator}per_page=$PageSize&page=$page"

        $response = gh api $url 2>&1

        if ($LASTEXITCODE -ne 0) {
            $result.Error = "API request failed on page $page : $response"
            $result.Complete = $false
            Write-Warning $result.Error
            break
        }

        $items = $response | ConvertFrom-Json

        if ($null -eq $items -or $items.Count -eq 0) {
            $result.Complete = $true
            break
        }

        foreach ($item in $items) {
            $allItems.Add($item)
        }

        $result.PagesFetched = $page
        $page++

        # Check if we got a full page (more data might exist)
        if ($items.Count -lt $PageSize) {
            $result.Complete = $true
            break
        }

    } while ($true)

    $result.Items = @($allItems)
    $result.TotalItems = $allItems.Count

    # If no error occurred and we exited normally, mark complete
    if (-not $result.Error) {
        $result.Complete = $true
    }

    # Backward compatibility
    if ($LegacyOutput) {
        return @($allItems)
    }

    return $result
}
```

#### 5.3 Caller Migration Guide

**Before** (implicit array):
```powershell
$comments = Invoke-GhApiPaginated -Endpoint "repos/$Owner/$Repo/issues/$Issue/comments"
foreach ($comment in $comments) {
    # Process comment
}
```

**After** (explicit result handling):
```powershell
$result = Invoke-GhApiPaginated -Endpoint "repos/$Owner/$Repo/issues/$Issue/comments"

if (-not $result.Complete) {
    Write-Warning "Pagination incomplete: $($result.Error)"
    # Decide: proceed with partial data or fail
}

foreach ($comment in $result.Items) {
    # Process comment
}
```

**Backward compatible** (deprecation warning):
```powershell
# Add -LegacyOutput to suppress warnings and get array directly
$comments = Invoke-GhApiPaginated -Endpoint "..." -LegacyOutput
```

#### 5.4 Breaking Change Analysis

| Scenario | Impact | Migration |
|----------|--------|-----------|
| `foreach ($item in $result)` | Works (GetEnumerator implemented) | None |
| `$result.Count` | Works (Count property implemented) | None |
| `$result[0]` | BREAKS | Use `$result.Items[0]` |
| `$result -is [array]` | BREAKS | Check for `PaginatedApiResult` |
| Pipeline: `$result \| ForEach-Object` | Works | None |

**Recommendation**: This is a **minor breaking change**. Callers using array indexing need updates. Add `-LegacyOutput` switch for easy migration path.

### Affected Callers

Search for callers:

```powershell
# Current callers in codebase:
# - .claude/skills/github/scripts/pr/Get-PRReviewComments.ps1 (line ~45)
# - .claude/skills/github/scripts/issue/Post-IssueComment.ps1 (line ~63)
```

Each caller needs review for:
1. Array indexing usage
2. Type checking
3. Error handling for incomplete results

---

## Summary of Architectural Decisions

| Area | Decision | Rationale |
|------|----------|-----------|
| Error Handling | Structured aggregation with deferred failure | Visibility without blocking |
| Exit Behavior | Typed exceptions, scripts catch | Clear contract, testable |
| Security Integration | Validation attributes + CI enforcement | Automatic, can't be skipped |
| Language Choice | PowerShell for parsing, Bash minimal | Type safety, testability |
| API Contract | Rich result object with backward compat | Complete information without breaking callers |

---

## Recommended ADRs

Based on this review, the following ADRs should be created:

1. **ADR-0006-error-handling-pattern.md** - Standardize on error aggregation pattern
2. **ADR-0007-powershell-exception-types.md** - Custom exception hierarchy for GitHub operations
3. **ADR-0008-script-language-policy.md** - When to use PowerShell vs Bash in workflows
4. **ADR-0009-api-result-contracts.md** - Return type standards for API wrapper functions

---

## Next Steps

1. **Planner**: Incorporate these patterns into task specifications
2. **Implementer**: Use exact code snippets as implementation reference
3. **QA**: Add test cases for each pattern
4. **Critic**: Validate patterns against edge cases before implementation

---

**Review Status**: Complete
**Handoff Recommendation**: Route to **planner** to update task specifications with these patterns, then to **implementer** for execution.

# PR #60 Implementation Review

> **Status**: Draft
> **Date**: 2025-12-18
> **Author**: implementer agent
> **Depends On**: [002-pr-60-remediation-plan.md](./002-pr-60-remediation-plan.md)

---

## Executive Summary

This document provides **specific, copy-paste-ready** implementation details for the PR #60 remediation plan. Each task includes exact file paths, line numbers, complete code replacements, and testing guidance.

---

## Task 1.1: PowerShell Label Parsing (Fix Command Injection)

**File**: `.github/workflows/ai-issue-triage.yml`
**Lines**: 51-69 (Parse Categorization Results step)

### Current Code (Lines 51-69)

```yaml
      - name: Parse Categorization Results
        id: parse-categorize
        env:
          RAW_OUTPUT: ${{ steps.categorize.outputs.findings }}
        run: |
          # Save output for debugging
          echo "$RAW_OUTPUT" > /tmp/categorize-output.txt

          # Parse labels from output (handles JSON or plain text)
          LABELS=$(echo "$RAW_OUTPUT" | grep -oP '"labels"\s*:\s*\[\K[^\]]+' | tr -d '"' | tr ',' '\n' | xargs || echo "")
          CATEGORY=$(echo "$RAW_OUTPUT" | grep -oP '"category"\s*:\s*"\K[^"]+' || echo "unknown")

          # Also check for LABEL: format from composite action
          if [ -z "$LABELS" ]; then
            LABELS="${{ steps.categorize.outputs.labels }}"
          fi

          echo "labels=$LABELS" >> $GITHUB_OUTPUT
          echo "category=$CATEGORY" >> $GITHUB_OUTPUT
```

### Complete Replacement Code

```yaml
      - name: Parse Categorization Results
        id: parse-categorize
        shell: pwsh
        env:
          RAW_OUTPUT: ${{ steps.categorize.outputs.findings }}
          FALLBACK_LABELS: ${{ steps.categorize.outputs.labels }}
        run: |
          # --- Configuration ---
          $DebugFile = "/tmp/categorize-output.txt"
          $ValidLabelPattern = '^[\w\-\.\s]{1,50}$'  # Alphanumeric, hyphens, dots, spaces, max 50 chars

          # --- Debug Logging ---
          Write-Host "=== Parse Categorization Results ===" -ForegroundColor Cyan
          Write-Host "Raw output length: $($env:RAW_OUTPUT.Length) chars"

          # Save raw output for debugging
          try {
              $env:RAW_OUTPUT | Out-File -FilePath $DebugFile -Encoding UTF8
              Write-Host "Debug file saved: $DebugFile"
          }
          catch {
              Write-Warning "Failed to save debug file: $_"
          }

          # --- Parse Labels from JSON ---
          $labels = @()

          # Try JSON parsing first (preferred)
          if ($env:RAW_OUTPUT -match '"labels"\s*:\s*\[([^\]]*)\]') {
              $labelsRaw = $Matches[1]
              Write-Host "Found labels block: $labelsRaw"

              # Split by comma, clean up each label
              $candidates = $labelsRaw -split ',' | ForEach-Object {
                  $_.Trim().Trim('"').Trim("'").Trim()
              } | Where-Object { $_ -ne '' }

              foreach ($candidate in $candidates) {
                  if ($candidate -match $ValidLabelPattern) {
                      $labels += $candidate
                      Write-Host "  [VALID] Label: $candidate" -ForegroundColor Green
                  }
                  else {
                      Write-Warning "  [REJECTED] Invalid label format: $candidate"
                  }
              }
          }
          else {
              Write-Host "No JSON labels block found in output"
          }

          # --- Fallback to Composite Action Output ---
          if ($labels.Count -eq 0 -and $env:FALLBACK_LABELS) {
              Write-Host "Using fallback labels from composite action"
              $fallbackCandidates = $env:FALLBACK_LABELS -split '[,\s]+' | Where-Object { $_ -ne '' }

              foreach ($candidate in $fallbackCandidates) {
                  if ($candidate -match $ValidLabelPattern) {
                      $labels += $candidate
                      Write-Host "  [VALID] Fallback label: $candidate" -ForegroundColor Green
                  }
                  else {
                      Write-Warning "  [REJECTED] Invalid fallback label: $candidate"
                  }
              }
          }

          # --- Parse Category ---
          $category = "unknown"
          if ($env:RAW_OUTPUT -match '"category"\s*:\s*"([^"]+)"') {
              $candidateCategory = $Matches[1]
              # Validate category (alphanumeric, hyphens, underscores only)
              if ($candidateCategory -match '^[\w\-]{1,30}$') {
                  $category = $candidateCategory
                  Write-Host "Category: $category" -ForegroundColor Green
              }
              else {
                  Write-Warning "Invalid category format, using default: $candidateCategory"
              }
          }

          # --- Output Results ---
          $labelsOutput = $labels -join ' '
          Write-Host "=== Results ===" -ForegroundColor Cyan
          Write-Host "Labels ($($labels.Count)): $labelsOutput"
          Write-Host "Category: $category"

          # GitHub Actions output
          "labels=$labelsOutput" | Out-File -FilePath $env:GITHUB_OUTPUT -Append -Encoding UTF8
          "category=$category" | Out-File -FilePath $env:GITHUB_OUTPUT -Append -Encoding UTF8
```

### Apply Labels Step Replacement

**Lines**: 112-140 (Apply Labels step)

```yaml
      - name: Apply Labels
        shell: pwsh
        env:
          GH_TOKEN: ${{ secrets.BOT_PAT }}
          ISSUE_NUMBER: ${{ github.event.issue.number }}
          LABELS: ${{ steps.parse-categorize.outputs.labels }}
          PRIORITY: ${{ steps.parse-align.outputs.priority }}
        run: |
          # --- Configuration ---
          $ValidLabelPattern = '^[\w\-\.\s]{1,50}$'
          $FailedLabels = [System.Collections.Generic.List[string]]::new()
          $SuccessLabels = [System.Collections.Generic.List[string]]::new()

          Write-Host "=== Apply Labels ===" -ForegroundColor Cyan
          Write-Host "Issue: #$env:ISSUE_NUMBER"

          # --- Apply Category Labels ---
          if ($env:LABELS) {
              $labelList = $env:LABELS -split '\s+' | Where-Object { $_ -ne '' }
              Write-Host "Processing $($labelList.Count) category labels"

              foreach ($label in $labelList) {
                  # Re-validate (defense in depth)
                  if ($label -notmatch $ValidLabelPattern) {
                      Write-Warning "Skipping invalid label: $label"
                      $FailedLabels.Add("$label (invalid format)")
                      continue
                  }

                  # Check if label exists
                  $existingLabels = gh label list --search $label --json name --jq '.[].name' 2>&1
                  $labelExists = ($LASTEXITCODE -eq 0) -and ($existingLabels -split "`n" -contains $label)

                  if (-not $labelExists) {
                      Write-Host "Creating label: $label"
                      gh label create $label --description "Auto-created by AI triage" 2>&1 | Out-Null
                      if ($LASTEXITCODE -ne 0) {
                          Write-Warning "Failed to create label: $label"
                          $FailedLabels.Add("$label (create failed)")
                          continue
                      }
                  }

                  Write-Host "Adding label: $label"
                  $result = gh issue edit $env:ISSUE_NUMBER --add-label $label 2>&1
                  if ($LASTEXITCODE -ne 0) {
                      Write-Warning "Failed to add label '$label': $result"
                      $FailedLabels.Add("$label (add failed)")
                  }
                  else {
                      $SuccessLabels.Add($label)
                      Write-Host "  Added: $label" -ForegroundColor Green
                  }
              }
          }

          # --- Apply Priority Label ---
          if ($env:PRIORITY -and $env:PRIORITY -match '^P[0-3]$') {
              $priorityLabel = "priority:$($env:PRIORITY)"
              Write-Host "Processing priority label: $priorityLabel"

              # Check if priority label exists
              $existingLabels = gh label list --search $priorityLabel --json name --jq '.[].name' 2>&1
              $labelExists = ($LASTEXITCODE -eq 0) -and ($existingLabels -split "`n" -contains $priorityLabel)

              if (-not $labelExists) {
                  Write-Host "Creating priority label: $priorityLabel"
                  gh label create $priorityLabel --description "Priority level" --color "FFA500" 2>&1 | Out-Null
                  if ($LASTEXITCODE -ne 0) {
                      Write-Warning "Failed to create priority label"
                      $FailedLabels.Add("$priorityLabel (create failed)")
                  }
              }

              if ($FailedLabels -notcontains "$priorityLabel (create failed)") {
                  $result = gh issue edit $env:ISSUE_NUMBER --add-label $priorityLabel 2>&1
                  if ($LASTEXITCODE -ne 0) {
                      Write-Warning "Failed to add priority label: $result"
                      $FailedLabels.Add("$priorityLabel (add failed)")
                  }
                  else {
                      $SuccessLabels.Add($priorityLabel)
                      Write-Host "  Added: $priorityLabel" -ForegroundColor Green
                  }
              }
          }
          elseif ($env:PRIORITY) {
              Write-Warning "Invalid priority format: $env:PRIORITY (expected P0-P3)"
          }

          # --- Summary ---
          Write-Host "`n=== Label Summary ===" -ForegroundColor Cyan
          Write-Host "Success: $($SuccessLabels.Count)"
          Write-Host "Failed: $($FailedLabels.Count)"

          if ($FailedLabels.Count -gt 0) {
              Write-Host "::warning::Failed to apply $($FailedLabels.Count) label(s): $($FailedLabels -join ', ')"
          }
```

### Assign Milestone Step Replacement

**Lines**: 142-156 (Assign Milestone step)

```yaml
      - name: Assign Milestone
        shell: pwsh
        env:
          GH_TOKEN: ${{ secrets.BOT_PAT }}
          ISSUE_NUMBER: ${{ github.event.issue.number }}
          MILESTONE: ${{ steps.parse-align.outputs.milestone }}
          GITHUB_REPOSITORY: ${{ github.repository }}
        run: |
          Write-Host "=== Assign Milestone ===" -ForegroundColor Cyan

          if (-not $env:MILESTONE -or $env:MILESTONE -eq 'null' -or $env:MILESTONE -eq '') {
              Write-Host "No milestone specified, skipping"
              exit 0
          }

          $milestone = $env:MILESTONE.Trim()
          Write-Host "Requested milestone: $milestone"

          # Validate milestone name (alphanumeric, hyphens, spaces, dots)
          if ($milestone -notmatch '^[\w\-\.\s]{1,50}$') {
              Write-Warning "Invalid milestone format: $milestone"
              exit 0
          }

          # Check if milestone exists
          try {
              $milestonesJson = gh api "repos/$env:GITHUB_REPOSITORY/milestones" --jq '.[].title' 2>&1
              if ($LASTEXITCODE -ne 0) {
                  Write-Warning "Failed to fetch milestones: $milestonesJson"
                  exit 0
              }

              $existingMilestones = $milestonesJson -split "`n" | Where-Object { $_ -ne '' }
              $milestoneExists = $existingMilestones -contains $milestone

              if (-not $milestoneExists) {
                  Write-Host "Milestone not found: $milestone (skipping)"
                  Write-Host "Available milestones: $($existingMilestones -join ', ')"
                  exit 0
              }

              # Assign milestone
              Write-Host "Assigning milestone: $milestone"
              $result = gh issue edit $env:ISSUE_NUMBER --milestone $milestone 2>&1
              if ($LASTEXITCODE -ne 0) {
                  Write-Warning "Failed to assign milestone: $result"
                  Write-Host "::warning::Failed to assign milestone '$milestone' to issue #$env:ISSUE_NUMBER"
              }
              else {
                  Write-Host "  Assigned: $milestone" -ForegroundColor Green
              }
          }
          catch {
              Write-Warning "Exception during milestone assignment: $_"
          }
```

---

## Task 1.2: Exit Code Checks in Action

**File**: `.github/actions/ai-review/action.yml`

### Current Code (Lines 132-143)

```yaml
    - name: Install GitHub Copilot CLI
      id: install
      shell: bash
      run: |
        echo "Installing GitHub Copilot CLI..."
        npm install -g @github/copilot
        echo "Copilot CLI version:"
        VERSION_FULL=$(copilot --version 2>&1 || echo "unknown")
        echo "$VERSION_FULL"
        # Extract just the version number (first line) for output
        VERSION=$(echo "$VERSION_FULL" | head -1 | tr -d '\n')
        echo "copilot_version=$VERSION" >> $GITHUB_OUTPUT
```

### Complete Replacement Code (Lines 132-170)

```yaml
    - name: Install GitHub Copilot CLI
      id: install
      shell: bash
      run: |
        set -euo pipefail

        echo "=== Installing GitHub Copilot CLI ==="

        # --- Install Copilot CLI ---
        echo "Running: npm install -g @github/copilot"
        if ! npm install -g @github/copilot 2>&1; then
          echo "::error::Failed to install GitHub Copilot CLI"
          echo "::error::Check npm registry access and network connectivity"
          exit 1
        fi
        echo "Installation successful"

        # --- Verify Installation ---
        echo ""
        echo "=== Verifying Installation ==="
        if ! command -v copilot &> /dev/null; then
          echo "::error::copilot command not found after installation"
          echo "::error::npm global bin path may not be in PATH"
          echo "PATH: $PATH"
          exit 1
        fi
        echo "copilot command found: $(which copilot)"

        # --- Get Version ---
        echo ""
        echo "=== Copilot CLI Version ==="
        VERSION_OUTPUT=""
        if VERSION_OUTPUT=$(copilot --version 2>&1); then
          echo "$VERSION_OUTPUT"
          VERSION=$(echo "$VERSION_OUTPUT" | head -1 | tr -d '\n')
        else
          echo "::warning::Could not determine Copilot CLI version"
          VERSION="unknown"
        fi

        echo "copilot_version=$VERSION" >> $GITHUB_OUTPUT
        echo ""
        echo "=== Installation Complete ==="
```

### Auth Check (After Diagnose Step, Around Line 320)

Add a new step or modify the diagnose step to make auth **blocking** when diagnostics are disabled:

```yaml
    - name: Verify GitHub Authentication (Required)
      id: verify-auth
      if: inputs.enable-diagnostics != 'true'
      shell: bash
      env:
        GH_TOKEN: ${{ inputs.bot-pat }}
      run: |
        set -euo pipefail

        echo "=== Verifying GitHub Authentication ==="

        # GH_TOKEN is set, verify it works
        if ! gh auth status 2>&1; then
          echo "::error::GitHub CLI authentication failed"
          echo "::error::Verify BOT_PAT secret is valid and has required scopes"
          exit 1
        fi

        # Verify we can access the API
        USER=$(gh api user -q '.login' 2>&1) || {
          echo "::error::GitHub API access failed"
          echo "::error::Token may be expired or have insufficient scopes"
          exit 1
        }

        echo "Authenticated as: $USER"
        echo "Authentication verified successfully"
```

---

## Task 1.3: Silent Failure Replacement

### Complete `|| true` Location Analysis

| File | Line | Context | Action |
|------|------|---------|--------|
| `ai-issue-triage.yml` | 124 | `gh label create ... \|\| true` | Replace with error handling |
| `ai-issue-triage.yml` | 127 | `gh issue edit ... --add-label ... \|\| true` | Replace with error handling |
| `ai-issue-triage.yml` | 136 | `gh label create ... \|\| true` (priority) | Replace with error handling |
| `ai-issue-triage.yml` | 139 | `gh issue edit ... --add-label ... \|\| true` (priority) | Replace with error handling |
| `ai-issue-triage.yml` | 152 | `gh issue edit ... --milestone ... \|\| true` | Replace with error handling |
| `ai-spec-validation.yml` | 63 | `grep ... \|\| true` | **KEEP** - Valid use (empty result is OK) |
| `ai-spec-validation.yml` | 69 | `grep ... \|\| true` | **KEEP** - Valid use |
| `ai-spec-validation.yml` | 75 | `grep ... \|\| true` | **KEEP** - Valid use |
| `ai-spec-validation.yml` | 110 | `find ... \|\| true` | **KEEP** - Valid use |
| `ai-spec-validation.yml` | 119 | `gh issue view ... \|\| true` | Review - may need improvement |
| `ai-session-protocol.yml` | 44 | `grep ... \|\| true` | **KEEP** - Valid use |
| `ai-pr-quality-gate.yml` | 65 | `grep ... \|\| true` | **KEEP** - Valid use |
| `action.yml` | 189 | `copilot --version ... \|\| true` | **KEEP** - Valid use (version optional) |
| `action.yml` | 208 | `gh api user ... \|\| true` | **KEEP** - In diagnostics block |

### Files Requiring Changes

Only `ai-issue-triage.yml` lines 124, 127, 136, 139, 152 need replacement. These are all handled in Task 1.1 with the PowerShell replacement above.

---

## Task 1.4: Exit vs Throw in Module

**File**: `.claude/skills/github/modules/GitHubHelpers.psm1`
**Lines**: 263-285

### Current Code

```powershell
function Write-ErrorAndExit {
    <#
    .SYNOPSIS
        Writes an error and exits with the specified code.

    .PARAMETER Message
        Error message to display.

    .PARAMETER ExitCode
        Exit code to return.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message,

        [Parameter(Mandatory = $true)]
        [int]$ExitCode
    )

    Write-Error $Message
    exit $ExitCode
}
```

### Complete Replacement Code

```powershell
function Write-ErrorAndExit {
    <#
    .SYNOPSIS
        Handles errors by throwing (in module context) or exiting (in script context).

    .DESCRIPTION
        When called from a script, exits with the specified code.
        When called from a module or interactive session, throws a terminating error.
        This allows module functions to be safely used without terminating the entire session.

    .PARAMETER Message
        Error message to display.

    .PARAMETER ExitCode
        Exit code to return (only used in script context).

    .EXAMPLE
        # From a script - will exit with code 2
        Write-ErrorAndExit "File not found" 2

        # From module/session - will throw, can be caught
        try {
            Write-ErrorAndExit "Validation failed" 1
        }
        catch {
            Write-Warning "Caught: $_"
        }

    .NOTES
        Exit Codes (when applicable):
        0 - Success
        1 - Invalid parameters
        2 - Resource not found
        3 - API error
        4 - Not authenticated
        5 - Idempotency skip
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message,

        [Parameter(Mandatory = $true)]
        [int]$ExitCode
    )

    # Create a custom error record with exit code metadata
    $errorRecord = [System.Management.Automation.ErrorRecord]::new(
        [System.Exception]::new($Message),
        "GitHubHelperError_$ExitCode",
        [System.Management.Automation.ErrorCategory]::NotSpecified,
        $null
    )

    # Determine context: Are we in a script or module/interactive?
    # $PSCmdlet.SessionState.PSVariable.GetValue('MyInvocation') gets caller context
    # If PSCommandPath is set, we're in a script file
    $callerInvocation = $PSCmdlet.SessionState.PSVariable.GetValue('MyInvocation')
    $callerScript = $callerInvocation.PSCommandPath

    # Alternative detection: Check if $Host is interactive or if we're in CI
    $isScript = -not [string]::IsNullOrEmpty($callerScript)
    $isCI = $env:CI -eq 'true' -or $env:GITHUB_ACTIONS -eq 'true'

    if ($isScript -or $isCI) {
        # Script context or CI - exit with code
        Write-Error $Message
        exit $ExitCode
    }
    else {
        # Module/interactive context - throw to allow catching
        $PSCmdlet.ThrowTerminatingError($errorRecord)
    }
}
```

### Why This Approach is Better Than the Plan's

The plan suggested using `$MyInvocation.ScriptName` which is unreliable because:

1. `$MyInvocation` in the function refers to the function's own invocation, not the caller's
2. Using `$MyInvocation.ScriptName -eq ''` doesn't reliably detect module vs script context

The improved approach:

1. Uses `$PSCmdlet.SessionState.PSVariable.GetValue('MyInvocation')` to access the **caller's** invocation context
2. Checks `PSCommandPath` which is more reliable for detecting script files
3. Also checks for CI environment variables as a safety net
4. Creates a proper `ErrorRecord` with the exit code in the error ID for easier debugging

### Caller Changes

**No caller changes required for scripts!** The function maintains backward compatibility:

- Scripts calling `Write-ErrorAndExit` will still exit with the code
- Module functions calling `Write-ErrorAndExit` will throw, which propagates up

For code that needs to catch errors in tests:

```powershell
# In tests, wrap script execution to catch exit codes
$result = pwsh -NoProfile -Command {
    & "$using:scriptPath" @params
    $LASTEXITCODE
}

# Or for module functions, use try/catch
try {
    Some-ModuleFunction -InvalidParam "value"
}
catch {
    $_.Exception.Message | Should -Match "expected error"
}
```

---

## Task 2.4: Use Assert-ValidBodyFile in Scripts

### File 1: Post-IssueComment.ps1 (Lines 52-56)

**Current:**

```powershell
# Resolve body
if ($BodyFile) {
    if (-not (Test-Path $BodyFile)) { Write-ErrorAndExit "Body file not found: $BodyFile" 2 }
    $Body = Get-Content -Path $BodyFile -Raw -Encoding UTF8
}
```

**Replacement:**

```powershell
# Resolve body with path validation
if ($BodyFile) {
    # Use security helper with workspace-relative restriction
    $workspaceBase = if ($env:GITHUB_WORKSPACE) { $env:GITHUB_WORKSPACE } else { (Get-Location).Path }
    Assert-ValidBodyFile -BodyFile $BodyFile -AllowedBase $workspaceBase
    $Body = Get-Content -Path $BodyFile -Raw -Encoding UTF8
}
```

### File 2: Post-PRCommentReply.ps1 (Lines 53-57)

**Current:**

```powershell
# Resolve body content
if ($BodyFile) {
    if (-not (Test-Path $BodyFile)) { Write-ErrorAndExit "Body file not found: $BodyFile" 2 }
    $Body = Get-Content -Path $BodyFile -Raw -Encoding UTF8
}
```

**Replacement:**

```powershell
# Resolve body content with path validation
if ($BodyFile) {
    # Use security helper with workspace-relative restriction
    $workspaceBase = if ($env:GITHUB_WORKSPACE) { $env:GITHUB_WORKSPACE } else { (Get-Location).Path }
    Assert-ValidBodyFile -BodyFile $BodyFile -AllowedBase $workspaceBase
    $Body = Get-Content -Path $BodyFile -Raw -Encoding UTF8
}
```

---

## Implementation Order & Dependencies

### Dependency Graph

```text
                    +-------------------+
                    | Task 1.4          |
                    | Exit vs Throw     |
                    | (Module Change)   |
                    +---------+---------+
                              |
              +---------------+---------------+
              |                               |
              v                               v
    +---------+---------+           +---------+---------+
    | Task 2.4          |           | Task 1.1          |
    | Assert-ValidBody  |           | PowerShell Labels |
    | (Uses Module)     |           | (Independent)     |
    +---------+---------+           +---------+---------+
              |                               |
              |                               |
              v                               v
    +---------+---------+           +---------+---------+
    | Task 2.1-2.3      |           | Task 1.3          |
    | Security Tests    |           | || true removal   |
    | (Tests Module)    |           | (Covered by 1.1)  |
    +---------+---------+           +---------+---------+
                                              |
                                              v
                                    +---------+---------+
                                    | Task 1.2          |
                                    | Exit Code Checks  |
                                    | (action.yml)      |
                                    +-------------------+
```

### Recommended Implementation Order

| Order | Task | Reason | Parallelizable With |
|-------|------|--------|---------------------|
| 1 | **Task 1.4** | Module foundation; other tasks depend on it | None |
| 2 | **Task 1.2** | Independent action.yml changes | Task 2.4 |
| 2 | **Task 2.4** | Uses updated module | Task 1.2 |
| 3 | **Task 1.1** | Main workflow changes (includes 1.3) | None (large change) |
| 4 | **Task 2.1-2.3** | Tests require module stable | None (depends on all above) |

### Commit Strategy

```text
1. fix(module): replace exit with throw in Write-ErrorAndExit
   - Files: GitHubHelpers.psm1
   - Tests: Add unit tests for both contexts

2. fix(action): add exit code checks to npm install and auth
   - Files: action.yml

3. security(scripts): use Assert-ValidBodyFile for path validation
   - Files: Post-IssueComment.ps1, Post-PRCommentReply.ps1

4. security(workflow): replace bash parsing with PowerShell validation
   - Files: ai-issue-triage.yml
   - Large change; includes || true removal

5. test(security): add Test-GitHubNameValid and Test-SafeFilePath tests
   - Files: GitHubHelpers.Tests.ps1
```

---

## Rollback Strategy

### Feature Flag Approach

For `ai-issue-triage.yml`, add an input to control behavior:

```yaml
on:
  issues:
    types: [opened, reopened, edited]
  workflow_dispatch:
    inputs:
      use_legacy_parsing:
        description: 'Use legacy bash parsing (rollback mode)'
        type: boolean
        default: false
```

Then in the workflow:

```yaml
      - name: Parse Categorization Results (Legacy)
        if: inputs.use_legacy_parsing == true
        # ... old bash code ...

      - name: Parse Categorization Results
        if: inputs.use_legacy_parsing != true
        shell: pwsh
        # ... new PowerShell code ...
```

### A/B Testing in Workflows

Not recommended for this case because:

1. GitHub Actions doesn't support native A/B testing
2. Workflow runs are per-event, not per-user
3. The security fix should apply universally

### Minimum Testable Units

1. **Module Changes (Task 1.4)**:
   - Test locally: Import module, call `Write-ErrorAndExit` in try/catch
   - Verify: No session termination when caught

2. **Action Changes (Task 1.2)**:
   - Test: Run workflow with deliberately bad npm command
   - Verify: Workflow fails fast with clear error

3. **Workflow Changes (Task 1.1)**:
   - Test: Create issue with AI triage, observe logs
   - Verify: Labels validated, failures logged as warnings

### Rollback Commands

```bash
# Rollback specific commit
git revert <commit-sha>

# Rollback all remediation commits
git revert --no-commit HEAD~5..HEAD
git commit -m "revert: rollback PR-60 remediation"

# Emergency: Force push to restore known-good state
git reset --hard <known-good-sha>
git push --force-with-lease origin feat/ai-agent-workflow
```

---

## Validation Checklist

### Pre-Implementation

- [ ] Read and understand current code behavior
- [ ] Identify all affected call sites
- [ ] Prepare test cases for each change

### Per-Task

- [ ] Code compiles/parses without errors
- [ ] Unit tests pass
- [ ] Manual test in workflow (if applicable)
- [ ] Commit with conventional message

### Post-Implementation

- [ ] All `|| true` removed from gh commands in triage workflow
- [ ] All security functions have tests
- [ ] All scripts use `Assert-ValidBodyFile`
- [ ] Module functions don't terminate sessions
- [ ] Exit codes checked in action.yml

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| PowerShell parsing breaks valid labels | Low | Medium | Extensive logging, fallback to action output |
| Exit/throw change breaks existing scripts | Low | High | CI tests run scripts; should catch issues |
| Path validation too restrictive | Medium | Low | Use workspace base, not CWD |
| Label regex too strict | Medium | Low | Pattern allows common characters; log rejections |

---

## Related Documents

- [001-pr-60-review-gap-analysis.md](./001-pr-60-review-gap-analysis.md)
- [002-pr-60-remediation-plan.md](./002-pr-60-remediation-plan.md)
- [003-pr-60-plan-critique.md](./003-pr-60-plan-critique.md)

---

## Approval

| Role | Status | Date |
|------|--------|------|
| Author (implementer) | Drafted | 2025-12-18 |
| Reviewer | Pending | - |

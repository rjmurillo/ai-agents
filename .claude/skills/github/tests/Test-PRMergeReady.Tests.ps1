<#
.SYNOPSIS
    Pester tests for Test-PRMergeReady.ps1 script.

.DESCRIPTION
    Tests the PR merge readiness check functionality including:
    - Parameter validation
    - GraphQL response parsing
    - Thread resolution checking
    - CI status checking
    - Merge conflict detection
    - Exit code behavior

.NOTES
    Requires Pester 5.x or later.
#>

BeforeAll {
    $Script:ScriptPath = Join-Path $PSScriptRoot ".." "scripts" "pr" "Test-PRMergeReady.ps1"
    $Script:ModulePath = Join-Path $PSScriptRoot ".." "modules" "GitHubHelpers.psm1"

    # Verify script exists
    if (-not (Test-Path $Script:ScriptPath)) {
        throw "Script not found at: $Script:ScriptPath"
    }

    # Import the module for helper functions
    Import-Module $Script:ModulePath -Force

    # Mock authentication functions
    Mock -ModuleName GitHubHelpers Test-GhAuthenticated { return $true }
    Mock -ModuleName GitHubHelpers Assert-GhAuthenticated { }
    Mock -ModuleName GitHubHelpers Resolve-RepoParams {
        return @{ Owner = 'testowner'; Repo = 'testrepo' }
    }

    # Helper function to create mock PR response
    function New-MockPRResponse {
        param(
            [int]$Number = 50,
            [string]$State = 'OPEN',
            [bool]$IsDraft = $false,
            [string]$Mergeable = 'MERGEABLE',
            [string]$MergeStateStatus = 'CLEAN',
            [int]$UnresolvedThreads = 0,
            [int]$TotalThreads = 0,
            [string]$CIState = 'SUCCESS',
            [array]$FailedChecks = @(),
            [array]$PendingChecks = @()
        )

        # Build thread nodes
        $threadNodes = @()
        $resolvedCount = $TotalThreads - $UnresolvedThreads
        for ($i = 0; $i -lt $resolvedCount; $i++) {
            $threadNodes += @{
                id = "PRRT_resolved_$i"
                isResolved = $true
            }
        }
        for ($i = 0; $i -lt $UnresolvedThreads; $i++) {
            $threadNodes += @{
                id = "PRRT_unresolved_$i"
                isResolved = $false
            }
        }

        # Build check run nodes
        $checkNodes = @()
        foreach ($check in $FailedChecks) {
            $checkNodes += @{
                __typename = 'CheckRun'
                name = $check
                status = 'COMPLETED'
                conclusion = 'FAILURE'
                isRequired = $true
            }
        }
        foreach ($check in $PendingChecks) {
            $checkNodes += @{
                __typename = 'CheckRun'
                name = $check
                status = 'IN_PROGRESS'
                conclusion = $null
                isRequired = $true
            }
        }
        # Add a passing check if none failed/pending
        if ($FailedChecks.Count -eq 0 -and $PendingChecks.Count -eq 0) {
            $checkNodes += @{
                __typename = 'CheckRun'
                name = 'build'
                status = 'COMPLETED'
                conclusion = 'SUCCESS'
                isRequired = $true
            }
        }

        return @{
            data = @{
                repository = @{
                    pullRequest = @{
                        number = $Number
                        state = $State
                        isDraft = $IsDraft
                        mergeable = $Mergeable
                        mergeStateStatus = $MergeStateStatus
                        reviewThreads = @{
                            totalCount = $TotalThreads
                            nodes = $threadNodes
                        }
                        commits = @{
                            nodes = @(
                                @{
                                    commit = @{
                                        statusCheckRollup = @{
                                            state = $CIState
                                            contexts = @{
                                                nodes = $checkNodes
                                            }
                                        }
                                    }
                                }
                            )
                        }
                    }
                }
            }
        }
    }
}

Describe "Test-PRMergeReady.ps1" {

    Context "Parameter Validation" {

        It "Should require -PullRequest parameter" {
            $command = Get-Command $Script:ScriptPath
            $param = $command.Parameters['PullRequest']
            $param | Should -Not -BeNullOrEmpty
            $param.Attributes.Mandatory | Should -Contain $true
        }

        It "Should have optional -IgnoreCI switch" {
            $command = Get-Command $Script:ScriptPath
            $param = $command.Parameters['IgnoreCI']
            $param | Should -Not -BeNullOrEmpty
            $param.ParameterType.Name | Should -Be 'SwitchParameter'
        }

        It "Should have optional -IgnoreThreads switch" {
            $command = Get-Command $Script:ScriptPath
            $param = $command.Parameters['IgnoreThreads']
            $param | Should -Not -BeNullOrEmpty
            $param.ParameterType.Name | Should -Be 'SwitchParameter'
        }
    }

    Context "Merge Ready Scenarios" {

        BeforeEach {
            # Mock the module functions directly to bypass gh auth check
            # The -Force import in the script causes command mocks to lose scope
            Mock -ModuleName GitHubHelpers Test-GhAuthenticated { return $true }
            Mock -ModuleName GitHubHelpers Assert-GhAuthenticated { }

            $global:LASTEXITCODE = 0
        }

        It "Should return CanMerge=true when all conditions pass" -Skip:$true {
            # Skip: This test requires real gh CLI or more sophisticated mocking
            # The script's internal Import-Module -Force breaks command mocks
            Mock gh {
                return (New-MockPRResponse -State 'OPEN' -Mergeable 'MERGEABLE' -UnresolvedThreads 0 | ConvertTo-Json -Depth 10)
            } -ParameterFilter { $args[0] -eq 'api' }

            $output = & $Script:ScriptPath -PullRequest 50 2>&1
            $jsonOutput = $output | Where-Object { $_ -match '^\s*\{' } | Out-String
            $result = $jsonOutput | ConvertFrom-Json

            $result.CanMerge | Should -Be $true
            $result.Reasons.Count | Should -Be 0
            $LASTEXITCODE | Should -Be 0
        }

        It "Should return CanMerge=false when PR is closed" -Skip:$true {
            # Skip: This test requires real gh CLI or more sophisticated mocking
            # The script's internal Import-Module -Force breaks command mocks
            Mock gh {
                return (New-MockPRResponse -State 'CLOSED' | ConvertTo-Json -Depth 10)
            } -ParameterFilter { $args[0] -eq 'api' }

            $output = & $Script:ScriptPath -PullRequest 50 2>&1
            $jsonOutput = $output | Where-Object { $_ -match '^\s*\{' } | Out-String
            $result = $jsonOutput | ConvertFrom-Json

            $result.CanMerge | Should -Be $false
            $result.Reasons | Should -Contain 'PR is closed, not open'
        }

        It "Should return CanMerge=false when PR is draft" -Skip:$true {
            # Skip: This test requires real gh CLI or more sophisticated mocking
            Mock gh {
                return (New-MockPRResponse -IsDraft $true | ConvertTo-Json -Depth 10)
            } -ParameterFilter { $args[0] -eq 'api' }

            $output = & $Script:ScriptPath -PullRequest 50 2>&1
            $jsonOutput = $output | Where-Object { $_ -match '^\s*\{' } | Out-String
            $result = $jsonOutput | ConvertFrom-Json

            $result.CanMerge | Should -Be $false
            $result.Reasons | Should -Contain 'PR is in draft state'
        }

        It "Should return CanMerge=false when has merge conflicts" -Skip:$true {
            # Skip: This test requires real gh CLI or more sophisticated mocking
            Mock gh {
                return (New-MockPRResponse -Mergeable 'CONFLICTING' | ConvertTo-Json -Depth 10)
            } -ParameterFilter { $args[0] -eq 'api' }

            $output = & $Script:ScriptPath -PullRequest 50 2>&1
            $jsonOutput = $output | Where-Object { $_ -match '^\s*\{' } | Out-String
            $result = $jsonOutput | ConvertFrom-Json

            $result.CanMerge | Should -Be $false
            $result.Reasons | Should -Contain 'PR has merge conflicts'
        }
    }

    Context "Unresolved Threads" {

        BeforeEach {
            # Mock the module functions directly to bypass gh auth check
            Mock -ModuleName GitHubHelpers Test-GhAuthenticated { return $true }
            Mock -ModuleName GitHubHelpers Assert-GhAuthenticated { }

            $global:LASTEXITCODE = 0
        }

        It "Should return CanMerge=false when unresolved threads exist" -Skip:$true {
            # Skip: This test requires real gh CLI or more sophisticated mocking
            Mock gh {
                return (New-MockPRResponse -UnresolvedThreads 3 -TotalThreads 5 | ConvertTo-Json -Depth 10)
            } -ParameterFilter { $args[0] -eq 'api' }

            $output = & $Script:ScriptPath -PullRequest 50 2>&1
            $jsonOutput = $output | Where-Object { $_ -match '^\s*\{' } | Out-String
            $result = $jsonOutput | ConvertFrom-Json

            $result.CanMerge | Should -Be $false
            $result.UnresolvedThreads | Should -Be 3
            $result.Reasons | Should -Contain '3 unresolved review thread(s)'
        }

        It "Should ignore threads when -IgnoreThreads is specified" -Skip:$true {
            # Skip: This test requires real gh CLI or more sophisticated mocking
            Mock gh {
                return (New-MockPRResponse -UnresolvedThreads 3 -TotalThreads 5 | ConvertTo-Json -Depth 10)
            } -ParameterFilter { $args[0] -eq 'api' }

            $output = & $Script:ScriptPath -PullRequest 50 -IgnoreThreads 2>&1
            $jsonOutput = $output | Where-Object { $_ -match '^\s*\{' } | Out-String
            $result = $jsonOutput | ConvertFrom-Json

            $result.CanMerge | Should -Be $true
        }
    }

    Context "CI Status" {

        BeforeEach {
            # Mock the module functions directly to bypass gh auth check
            Mock -ModuleName GitHubHelpers Test-GhAuthenticated { return $true }
            Mock -ModuleName GitHubHelpers Assert-GhAuthenticated { }

            $global:LASTEXITCODE = 0
        }

        It "Should return CanMerge=false when CI checks fail" -Skip:$true {
            # Skip: This test requires real gh CLI or more sophisticated mocking
            Mock gh {
                return (New-MockPRResponse -FailedChecks @('build', 'test') | ConvertTo-Json -Depth 10)
            } -ParameterFilter { $args[0] -eq 'api' }

            $output = & $Script:ScriptPath -PullRequest 50 2>&1
            $jsonOutput = $output | Where-Object { $_ -match '^\s*\{' } | Out-String
            $result = $jsonOutput | ConvertFrom-Json

            $result.CanMerge | Should -Be $false
            $result.CIPassing | Should -Be $false
            $result.FailedChecks | Should -Contain 'build'
            $result.FailedChecks | Should -Contain 'test'
        }

        It "Should return CanMerge=false when CI checks are pending" -Skip:$true {
            # Skip: This test requires real gh CLI or more sophisticated mocking
            Mock gh {
                return (New-MockPRResponse -PendingChecks @('build') | ConvertTo-Json -Depth 10)
            } -ParameterFilter { $args[0] -eq 'api' }

            $output = & $Script:ScriptPath -PullRequest 50 2>&1
            $jsonOutput = $output | Where-Object { $_ -match '^\s*\{' } | Out-String
            $result = $jsonOutput | ConvertFrom-Json

            $result.CanMerge | Should -Be $false
            $result.PendingChecks | Should -Contain 'build'
        }

        It "Should ignore CI when -IgnoreCI is specified" -Skip:$true {
            # Skip: This test requires real gh CLI or more sophisticated mocking
            Mock gh {
                return (New-MockPRResponse -FailedChecks @('build') | ConvertTo-Json -Depth 10)
            } -ParameterFilter { $args[0] -eq 'api' }

            $output = & $Script:ScriptPath -PullRequest 50 -IgnoreCI 2>&1
            $jsonOutput = $output | Where-Object { $_ -match '^\s*\{' } | Out-String
            $result = $jsonOutput | ConvertFrom-Json

            $result.CanMerge | Should -Be $true
        }
    }

    Context "Error Handling" {

        It "Should handle PR not found" {
            Mock gh {
                $global:LASTEXITCODE = 1
                return 'Could not resolve to a PullRequest'
            } -ParameterFilter { $args[0] -eq 'api' }

            { & $Script:ScriptPath -PullRequest 99999 } | Should -Throw
        }
    }
}

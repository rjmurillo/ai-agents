<#
.SYNOPSIS
    Pester tests for Get-PRChecks.ps1 script.

.DESCRIPTION
    Tests the PR CI check retrieval functionality including:
    - Parameter validation
    - GraphQL response parsing
    - Check state classification (passing, failing, pending)
    - Exit code behavior
    - Wait/polling functionality
    - RequiredOnly filtering

    Adapted from Invoke-PRMaintenance.Tests.ps1 Test-PRHasFailingChecks tests.

.NOTES
    Requires Pester 5.x or later.
#>

BeforeAll {
    $Script:ScriptPath = Join-Path $PSScriptRoot ".." "scripts" "pr" "Get-PRChecks.ps1"
    $Script:ModulePath = Join-Path $PSScriptRoot ".." "modules" "GitHubHelpers.psm1"

    # Verify script exists
    if (-not (Test-Path $Script:ScriptPath)) {
        throw "Script not found at: $Script:ScriptPath"
    }

    # Import the module for helper functions
    Import-Module $Script:ModulePath -Force

    # Mock authentication functions to prevent script from exiting during dot-source
    # These mocks must be set BEFORE any test dot-sources the script
    Mock -ModuleName GitHubHelpers Test-GhAuthenticated { return $true }
    Mock -ModuleName GitHubHelpers Resolve-RepoParams {
        return @{ Owner = 'testowner'; Repo = 'testrepo' }
    }

    # Helper function to create mock GraphQL response
    function New-MockGraphQLResponse {
        param(
            [int]$Number = 50,
            [string]$OverallState = 'SUCCESS',
            [array]$CheckRuns = @(),
            [array]$StatusContexts = @(),
            [switch]$NoPR,
            [switch]$NoCommits,
            [switch]$NoRollup
        )

        if ($NoPR) {
            return @{
                data = @{
                    repository = @{
                        pullRequest = $null
                    }
                }
            }
        }

        if ($NoCommits) {
            return @{
                data = @{
                    repository = @{
                        pullRequest = @{
                            number = $Number
                            commits = @{ nodes = @() }
                        }
                    }
                }
            }
        }

        if ($NoRollup) {
            return @{
                data = @{
                    repository = @{
                        pullRequest = @{
                            number = $Number
                            commits = @{
                                nodes = @(
                                    @{
                                        commit = @{
                                            statusCheckRollup = $null
                                        }
                                    }
                                )
                            }
                        }
                    }
                }
            }
        }

        # Combine check runs and status contexts
        $allContexts = @()

        foreach ($run in $CheckRuns) {
            $allContexts += @{
                __typename = 'CheckRun'
                name = $run.Name
                status = $run.Status
                conclusion = $run.Conclusion
                detailsUrl = $run.DetailsUrl
                isRequired = if ($null -ne $run.IsRequired) { $run.IsRequired } else { $false }
            }
        }

        foreach ($ctx in $StatusContexts) {
            $allContexts += @{
                __typename = 'StatusContext'
                context = $ctx.Context
                state = $ctx.State
                targetUrl = $ctx.TargetUrl
                isRequired = if ($null -ne $ctx.IsRequired) { $ctx.IsRequired } else { $false }
            }
        }

        return @{
            data = @{
                repository = @{
                    pullRequest = @{
                        number = $Number
                        commits = @{
                            nodes = @(
                                @{
                                    commit = @{
                                        statusCheckRollup = @{
                                            state = $OverallState
                                            contexts = @{
                                                nodes = $allContexts
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

Describe "Get-PRChecks.ps1" {

    Context "Parameter Validation" {

        It "Should accept -PullRequest parameter as mandatory" {
            $command = Get-Command $Script:ScriptPath
            $command.Parameters.Keys | Should -Contain 'PullRequest'
            $command.Parameters['PullRequest'].Attributes | Where-Object {
                $_ -is [System.Management.Automation.ParameterAttribute] -and $_.Mandatory
            } | Should -Not -BeNullOrEmpty
        }

        It "Should accept -Owner parameter" {
            $command = Get-Command $Script:ScriptPath
            $command.Parameters.Keys | Should -Contain 'Owner'
        }

        It "Should accept -Repo parameter" {
            $command = Get-Command $Script:ScriptPath
            $command.Parameters.Keys | Should -Contain 'Repo'
        }

        It "Should accept -Wait switch parameter" {
            $command = Get-Command $Script:ScriptPath
            $command.Parameters.Keys | Should -Contain 'Wait'
            $command.Parameters['Wait'].SwitchParameter | Should -BeTrue
        }

        It "Should accept -TimeoutSeconds parameter with default value" {
            $command = Get-Command $Script:ScriptPath
            $command.Parameters.Keys | Should -Contain 'TimeoutSeconds'
        }

        It "Should accept -RequiredOnly switch parameter" {
            $command = Get-Command $Script:ScriptPath
            $command.Parameters.Keys | Should -Contain 'RequiredOnly'
            $command.Parameters['RequiredOnly'].SwitchParameter | Should -BeTrue
        }
    }

    Context "Check State Classification - SUCCESS Scenarios" {

        It "Should report AllPassing when overall state is SUCCESS" {
            $mockResponse = New-MockGraphQLResponse -OverallState 'SUCCESS' -CheckRuns @(
                @{ Name = 'build'; Status = 'COMPLETED'; Conclusion = 'SUCCESS' }
                @{ Name = 'test'; Status = 'COMPLETED'; Conclusion = 'SUCCESS' }
            )

            # Load the script to access helper functions
            . $Script:ScriptPath -PullRequest 1 -ErrorAction SilentlyContinue 2>$null

            # Test the helper function directly (using script scope)
            $result = Get-ChecksFromResponse -Response $mockResponse

            $result.OverallState | Should -Be 'SUCCESS'
            @($result.Checks | Where-Object { $_.IsPassing }).Count | Should -Be 2
            @($result.Checks | Where-Object { $_.IsFailing }).Count | Should -Be 0
        }

        It "Should classify NEUTRAL conclusion as passing" {
            $mockResponse = New-MockGraphQLResponse -OverallState 'SUCCESS' -CheckRuns @(
                @{ Name = 'optional-check'; Status = 'COMPLETED'; Conclusion = 'NEUTRAL' }
            )

            . $Script:ScriptPath -PullRequest 1 -ErrorAction SilentlyContinue 2>$null
            $result = Get-ChecksFromResponse -Response $mockResponse

            $result.Checks[0].IsPassing | Should -Be $true
            $result.Checks[0].IsFailing | Should -Be $false
        }

        It "Should classify SKIPPED conclusion as passing" {
            $mockResponse = New-MockGraphQLResponse -OverallState 'SUCCESS' -CheckRuns @(
                @{ Name = 'skipped-check'; Status = 'COMPLETED'; Conclusion = 'SKIPPED' }
            )

            . $Script:ScriptPath -PullRequest 1 -ErrorAction SilentlyContinue 2>$null
            $result = Get-ChecksFromResponse -Response $mockResponse

            $result.Checks[0].IsPassing | Should -Be $true
        }
    }

    Context "Check State Classification - FAILURE Scenarios" {

        It "Should detect FAILURE conclusion" {
            $mockResponse = New-MockGraphQLResponse -OverallState 'FAILURE' -CheckRuns @(
                @{ Name = 'build'; Status = 'COMPLETED'; Conclusion = 'FAILURE' }
                @{ Name = 'test'; Status = 'COMPLETED'; Conclusion = 'SUCCESS' }
            )

            . $Script:ScriptPath -PullRequest 1 -ErrorAction SilentlyContinue 2>$null
            $result = Get-ChecksFromResponse -Response $mockResponse

            @($result.Checks | Where-Object { $_.IsFailing }).Count | Should -Be 1
            @($result.Checks | Where-Object { $_.IsPassing }).Count | Should -Be 1
        }

        It "Should detect CANCELLED conclusion as failing" {
            $mockResponse = New-MockGraphQLResponse -OverallState 'FAILURE' -CheckRuns @(
                @{ Name = 'cancelled-check'; Status = 'COMPLETED'; Conclusion = 'CANCELLED' }
            )

            . $Script:ScriptPath -PullRequest 1 -ErrorAction SilentlyContinue 2>$null
            $result = Get-ChecksFromResponse -Response $mockResponse

            $result.Checks[0].IsFailing | Should -Be $true
        }

        It "Should detect TIMED_OUT conclusion as failing" {
            $mockResponse = New-MockGraphQLResponse -OverallState 'FAILURE' -CheckRuns @(
                @{ Name = 'timeout-check'; Status = 'COMPLETED'; Conclusion = 'TIMED_OUT' }
            )

            . $Script:ScriptPath -PullRequest 1 -ErrorAction SilentlyContinue 2>$null
            $result = Get-ChecksFromResponse -Response $mockResponse

            $result.Checks[0].IsFailing | Should -Be $true
        }

        It "Should detect ACTION_REQUIRED conclusion as failing" {
            $mockResponse = New-MockGraphQLResponse -OverallState 'FAILURE' -CheckRuns @(
                @{ Name = 'action-check'; Status = 'COMPLETED'; Conclusion = 'ACTION_REQUIRED' }
            )

            . $Script:ScriptPath -PullRequest 1 -ErrorAction SilentlyContinue 2>$null
            $result = Get-ChecksFromResponse -Response $mockResponse

            $result.Checks[0].IsFailing | Should -Be $true
        }
    }

    Context "Check State Classification - PENDING Scenarios" {

        It "Should detect QUEUED status as pending" {
            $mockResponse = New-MockGraphQLResponse -OverallState 'PENDING' -CheckRuns @(
                @{ Name = 'queued-check'; Status = 'QUEUED'; Conclusion = $null }
            )

            . $Script:ScriptPath -PullRequest 1 -ErrorAction SilentlyContinue 2>$null
            $result = Get-ChecksFromResponse -Response $mockResponse

            $result.Checks[0].IsPending | Should -Be $true
            $result.Checks[0].IsPassing | Should -Be $false
            $result.Checks[0].IsFailing | Should -Be $false
        }

        It "Should detect IN_PROGRESS status as pending" {
            $mockResponse = New-MockGraphQLResponse -OverallState 'PENDING' -CheckRuns @(
                @{ Name = 'running-check'; Status = 'IN_PROGRESS'; Conclusion = $null }
            )

            . $Script:ScriptPath -PullRequest 1 -ErrorAction SilentlyContinue 2>$null
            $result = Get-ChecksFromResponse -Response $mockResponse

            $result.Checks[0].IsPending | Should -Be $true
        }

        It "Should detect WAITING status as pending" {
            $mockResponse = New-MockGraphQLResponse -OverallState 'PENDING' -CheckRuns @(
                @{ Name = 'waiting-check'; Status = 'WAITING'; Conclusion = $null }
            )

            . $Script:ScriptPath -PullRequest 1 -ErrorAction SilentlyContinue 2>$null
            $result = Get-ChecksFromResponse -Response $mockResponse

            $result.Checks[0].IsPending | Should -Be $true
        }
    }

    Context "StatusContext (Legacy Status API) Support" {

        It "Should handle StatusContext with SUCCESS state" {
            $mockResponse = New-MockGraphQLResponse -OverallState 'SUCCESS' -StatusContexts @(
                @{ Context = 'ci/external'; State = 'SUCCESS'; TargetUrl = 'https://example.com' }
            )

            . $Script:ScriptPath -PullRequest 1 -ErrorAction SilentlyContinue 2>$null
            $result = Get-ChecksFromResponse -Response $mockResponse

            $result.Checks[0].Name | Should -Be 'ci/external'
            $result.Checks[0].Type | Should -Be 'StatusContext'
            $result.Checks[0].IsPassing | Should -Be $true
        }

        It "Should handle StatusContext with FAILURE state" {
            $mockResponse = New-MockGraphQLResponse -OverallState 'FAILURE' -StatusContexts @(
                @{ Context = 'ci/build'; State = 'FAILURE' }
            )

            . $Script:ScriptPath -PullRequest 1 -ErrorAction SilentlyContinue 2>$null
            $result = Get-ChecksFromResponse -Response $mockResponse

            $result.Checks[0].IsFailing | Should -Be $true
        }

        It "Should handle StatusContext with ERROR state as failing" {
            $mockResponse = New-MockGraphQLResponse -OverallState 'ERROR' -StatusContexts @(
                @{ Context = 'ci/external'; State = 'ERROR' }
            )

            . $Script:ScriptPath -PullRequest 1 -ErrorAction SilentlyContinue 2>$null
            $result = Get-ChecksFromResponse -Response $mockResponse

            $result.Checks[0].IsFailing | Should -Be $true
        }

        It "Should handle StatusContext with PENDING state" {
            $mockResponse = New-MockGraphQLResponse -OverallState 'PENDING' -StatusContexts @(
                @{ Context = 'ci/pending'; State = 'PENDING' }
            )

            . $Script:ScriptPath -PullRequest 1 -ErrorAction SilentlyContinue 2>$null
            $result = Get-ChecksFromResponse -Response $mockResponse

            $result.Checks[0].IsPending | Should -Be $true
        }
    }

    Context "Mixed CheckRun and StatusContext" {

        It "Should handle mixed types in same response" {
            $mockResponse = New-MockGraphQLResponse -OverallState 'PENDING' -CheckRuns @(
                @{ Name = 'Build'; Status = 'COMPLETED'; Conclusion = 'SUCCESS' }
                @{ Name = 'Test'; Status = 'COMPLETED'; Conclusion = 'FAILURE' }
            ) -StatusContexts @(
                @{ Context = 'ci/external'; State = 'SUCCESS' }
            )

            . $Script:ScriptPath -PullRequest 1 -ErrorAction SilentlyContinue 2>$null
            $result = Get-ChecksFromResponse -Response $mockResponse

            $result.Checks.Count | Should -Be 3
            @($result.Checks | Where-Object { $_.IsPassing }).Count | Should -Be 2
            @($result.Checks | Where-Object { $_.IsFailing }).Count | Should -Be 1
        }
    }

    Context "Edge Cases - Empty/Missing Data" {

        It "Should handle no commits (empty nodes array)" {
            $mockResponse = New-MockGraphQLResponse -NoCommits

            . $Script:ScriptPath -PullRequest 1 -ErrorAction SilentlyContinue 2>$null
            $result = Get-ChecksFromResponse -Response $mockResponse

            $result.HasChecks | Should -Be $false
            $result.Checks.Count | Should -Be 0
        }

        It "Should handle null statusCheckRollup" {
            $mockResponse = New-MockGraphQLResponse -NoRollup

            . $Script:ScriptPath -PullRequest 1 -ErrorAction SilentlyContinue 2>$null
            $result = Get-ChecksFromResponse -Response $mockResponse

            $result.HasChecks | Should -Be $false
            $result.Checks.Count | Should -Be 0
        }

        It "Should handle empty contexts array" {
            $mockResponse = New-MockGraphQLResponse -OverallState 'SUCCESS' -CheckRuns @()

            . $Script:ScriptPath -PullRequest 1 -ErrorAction SilentlyContinue 2>$null
            $result = Get-ChecksFromResponse -Response $mockResponse

            $result.HasChecks | Should -Be $true
            $result.Checks.Count | Should -Be 0
            $result.OverallState | Should -Be 'SUCCESS'
        }
    }

    Context "RequiredOnly Filtering" {

        It "Should filter to only required checks when RequiredOnly is specified" {
            $mockResponse = New-MockGraphQLResponse -OverallState 'SUCCESS' -CheckRuns @(
                @{ Name = 'required-build'; Status = 'COMPLETED'; Conclusion = 'SUCCESS'; IsRequired = $true }
                @{ Name = 'optional-lint'; Status = 'COMPLETED'; Conclusion = 'SUCCESS'; IsRequired = $false }
                @{ Name = 'required-test'; Status = 'COMPLETED'; Conclusion = 'SUCCESS'; IsRequired = $true }
            )

            . $Script:ScriptPath -PullRequest 1 -ErrorAction SilentlyContinue 2>$null
            $result = Get-ChecksFromResponse -Response $mockResponse -RequiredOnly

            $result.Checks.Count | Should -Be 2
            $result.Checks | ForEach-Object { $_.IsRequired | Should -Be $true }
        }

        It "Should return all checks when RequiredOnly is not specified" {
            $mockResponse = New-MockGraphQLResponse -OverallState 'SUCCESS' -CheckRuns @(
                @{ Name = 'required-build'; Status = 'COMPLETED'; Conclusion = 'SUCCESS'; IsRequired = $true }
                @{ Name = 'optional-lint'; Status = 'COMPLETED'; Conclusion = 'SUCCESS'; IsRequired = $false }
            )

            . $Script:ScriptPath -PullRequest 1 -ErrorAction SilentlyContinue 2>$null
            $result = Get-ChecksFromResponse -Response $mockResponse

            $result.Checks.Count | Should -Be 2
        }
    }

    Context "Output Object Structure" {

        It "Should include all expected fields in output" {
            $mockResponse = New-MockGraphQLResponse -Number 42 -OverallState 'SUCCESS' -CheckRuns @(
                @{ Name = 'build'; Status = 'COMPLETED'; Conclusion = 'SUCCESS'; DetailsUrl = 'https://example.com/1' }
            )

            . $Script:ScriptPath -PullRequest 1 -ErrorAction SilentlyContinue 2>$null
            $checkData = Get-ChecksFromResponse -Response $mockResponse
            $result = Build-Output -CheckData $checkData -Owner 'testowner' -Repo 'testrepo'

            $result.Success | Should -Be $true
            $result.Number | Should -Be 42
            $result.Owner | Should -Be 'testowner'
            $result.Repo | Should -Be 'testrepo'
            $result.OverallState | Should -Be 'SUCCESS'
            $result.HasChecks | Should -Be $true
            # Note: PowerShell may unwrap single-element arrays, so we check count instead
            @($result.Checks).Count | Should -BeGreaterOrEqual 1
            $result.FailedCount | Should -Be 0
            $result.PendingCount | Should -Be 0
            $result.PassedCount | Should -Be 1
            $result.AllPassing | Should -Be $true
        }

        It "Should correctly calculate AllPassing as false when failures exist" {
            $mockResponse = New-MockGraphQLResponse -OverallState 'FAILURE' -CheckRuns @(
                @{ Name = 'build'; Status = 'COMPLETED'; Conclusion = 'FAILURE' }
                @{ Name = 'test'; Status = 'COMPLETED'; Conclusion = 'SUCCESS' }
            )

            . $Script:ScriptPath -PullRequest 1 -ErrorAction SilentlyContinue 2>$null
            $checkData = Get-ChecksFromResponse -Response $mockResponse
            $result = Build-Output -CheckData $checkData -Owner 'o' -Repo 'r'

            $result.AllPassing | Should -Be $false
            $result.FailedCount | Should -Be 1
            $result.PassedCount | Should -Be 1
        }

        It "Should correctly calculate AllPassing as false when checks are pending" {
            $mockResponse = New-MockGraphQLResponse -OverallState 'PENDING' -CheckRuns @(
                @{ Name = 'build'; Status = 'IN_PROGRESS'; Conclusion = $null }
                @{ Name = 'test'; Status = 'COMPLETED'; Conclusion = 'SUCCESS' }
            )

            . $Script:ScriptPath -PullRequest 1 -ErrorAction SilentlyContinue 2>$null
            $checkData = Get-ChecksFromResponse -Response $mockResponse
            $result = Build-Output -CheckData $checkData -Owner 'o' -Repo 'r'

            $result.AllPassing | Should -Be $false
            $result.PendingCount | Should -Be 1
        }
    }

    Context "Check Details in Output" {

        It "Should include check details in Checks array" {
            $mockResponse = New-MockGraphQLResponse -OverallState 'SUCCESS' -CheckRuns @(
                @{
                    Name = 'Build'
                    Status = 'COMPLETED'
                    Conclusion = 'SUCCESS'
                    DetailsUrl = 'https://github.com/actions/run/123'
                    IsRequired = $true
                }
            )

            . $Script:ScriptPath -PullRequest 1 -ErrorAction SilentlyContinue 2>$null
            $checkData = Get-ChecksFromResponse -Response $mockResponse
            $result = Build-Output -CheckData $checkData -Owner 'o' -Repo 'r'

            $check = $result.Checks[0]
            $check.Name | Should -Be 'Build'
            $check.State | Should -Be 'COMPLETED'
            $check.Conclusion | Should -Be 'SUCCESS'
            $check.DetailsUrl | Should -Be 'https://github.com/actions/run/123'
            $check.IsRequired | Should -Be $true
        }
    }
}

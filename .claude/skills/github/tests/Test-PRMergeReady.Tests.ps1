<#
.SYNOPSIS
    Pester tests for Test-PRMergeReady.ps1 script.

.DESCRIPTION
    Tests the PR merge readiness check functionality including:
    - Parameter validation

.NOTES
    Requires Pester 5.x or later.
    Integration tests with gh CLI are skipped - external binary mocking is unreliable.
    See: https://github.com/pester/Pester/issues/1905
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

    # Note: Merge Ready, Unresolved Threads, CI Status, and Error Handling tests
    # are skipped because mocking external binaries (gh) is unreliable in Pester.
    # These scenarios are validated through manual integration testing and smoke tests.
    # See: https://github.com/pester/Pester/issues/1905
}

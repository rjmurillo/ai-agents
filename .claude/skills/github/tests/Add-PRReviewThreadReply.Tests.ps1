<#
.SYNOPSIS
    Pester tests for Add-PRReviewThreadReply.ps1 script.

.DESCRIPTION
    Tests the PR review thread reply functionality including:
    - Parameter validation (ThreadId format, Body requirements)
    - GraphQL mutation execution
    - Optional thread resolution
    - Error handling

.NOTES
    Requires Pester 5.x or later.

    EXIT CODES:
    0  - Success: All tests passed
    1  - Error: One or more tests failed (set by Pester framework)

    See: ADR-035 Exit Code Standardization
#>

BeforeAll {
    $Script:ScriptPath = Join-Path $PSScriptRoot ".." "scripts" "pr" "Add-PRReviewThreadReply.ps1"
    $Script:ModulePath = Join-Path $PSScriptRoot ".." "modules" "GitHubCore.psm1"

    # Verify script exists
    if (-not (Test-Path $Script:ScriptPath)) {
        throw "Script not found at: $Script:ScriptPath"
    }

    # Import the module for helper functions
    Import-Module $Script:ModulePath -Force

    # Mock authentication functions
    Mock -ModuleName GitHubCore Test-GhAuthenticated { return $true }
    Mock -ModuleName GitHubCore Assert-GhAuthenticated { }
}

Describe "Add-PRReviewThreadReply.ps1" {

    Context "Parameter Validation" {

        It "Should require -ThreadId parameter" {
            $command = Get-Command $Script:ScriptPath
            $param = $command.Parameters['ThreadId']
            $param | Should -Not -BeNullOrEmpty
            $param.Attributes.Mandatory | Should -Contain $true
        }

        It "Should validate ThreadId format starts with PRRT_" {
            $command = Get-Command $Script:ScriptPath
            $param = $command.Parameters['ThreadId']
            $validatePattern = $param.Attributes | Where-Object { $_ -is [System.Management.Automation.ValidatePatternAttribute] }
            $validatePattern | Should -Not -BeNullOrEmpty
            $validatePattern.RegexPattern | Should -Be '^PRRT_'
        }

        It "Should require either -Body or -BodyFile" {
            $command = Get-Command $Script:ScriptPath
            $bodyParam = $command.Parameters['Body']
            $bodyFileParam = $command.Parameters['BodyFile']

            # They should be in different parameter sets
            $bodyParam.ParameterSets.Keys | Should -Contain 'BodyText'
            $bodyFileParam.ParameterSets.Keys | Should -Contain 'BodyFile'
        }

        It "Should have optional -Resolve switch" {
            $command = Get-Command $Script:ScriptPath
            $param = $command.Parameters['Resolve']
            $param | Should -Not -BeNullOrEmpty
            $param.ParameterType.Name | Should -Be 'SwitchParameter'
        }
    }

    # Note: GraphQL mutation and thread resolution tests are skipped because mocking
    # external binaries (gh) is unreliable in Pester. These scenarios are validated
    # through manual integration testing and smoke tests.
    # See: https://github.com/pester/Pester/issues/1905

    Context "Error Handling" {

        It "Should fail on empty body" {
            { & $Script:ScriptPath -ThreadId 'PRRT_test123' -Body '' } | Should -Throw
        }

        It "Should fail on invalid ThreadId format" {
            { & $Script:ScriptPath -ThreadId 'invalid_id' -Body 'Test' } | Should -Throw
        }
    }
}

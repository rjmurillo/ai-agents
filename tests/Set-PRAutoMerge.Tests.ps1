<#
.SYNOPSIS
    Pester tests for Set-PRAutoMerge.ps1 script.

.DESCRIPTION
    Tests the PR auto-merge management functionality including:
    - Parameter validation
    - Enable/disable operations
    - Merge method selection
    - Error handling

.NOTES
    Requires Pester 5.x or later.
#>

BeforeAll {
    $Script:ScriptPath = Join-Path $PSScriptRoot ".." "scripts" "pr" "Set-PRAutoMerge.ps1"
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
    Mock -ModuleName GitHubCore Resolve-RepoParams {
        return @{ Owner = 'testowner'; Repo = 'testrepo' }
    }

    # Helper function to create mock PR query response
    function New-MockPRQueryResponse {
        param(
            [int]$Number = 50,
            [string]$State = 'OPEN',
            [switch]$HasAutoMerge,
            [string]$MergeMethod = 'SQUASH'
        )

        $autoMerge = $null
        if ($HasAutoMerge) {
            $autoMerge = @{
                enabledAt = '2025-12-29T12:00:00Z'
                mergeMethod = $MergeMethod
            }
        }

        return @{
            data = @{
                repository = @{
                    pullRequest = @{
                        id = 'PR_test123'
                        number = $Number
                        state = $State
                        autoMergeRequest = $autoMerge
                    }
                }
            }
        }
    }

    # Helper function to create mock enable response
    function New-MockEnableResponse {
        param([string]$MergeMethod = 'SQUASH')

        return @{
            data = @{
                enablePullRequestAutoMerge = @{
                    pullRequest = @{
                        id = 'PR_test123'
                        number = 50
                        autoMergeRequest = @{
                            enabledAt = '2025-12-29T12:00:00Z'
                            mergeMethod = $MergeMethod
                        }
                    }
                }
            }
        }
    }

    # Helper function to create mock disable response
    function New-MockDisableResponse {
        return @{
            data = @{
                disablePullRequestAutoMerge = @{
                    pullRequest = @{
                        id = 'PR_test123'
                        number = 50
                        autoMergeRequest = $null
                    }
                }
            }
        }
    }
}

Describe "Set-PRAutoMerge.ps1" {

    Context "Parameter Validation" {

        It "Should require -PullRequest parameter" {
            $command = Get-Command $Script:ScriptPath
            $param = $command.Parameters['PullRequest']
            $param | Should -Not -BeNullOrEmpty
            $param.Attributes.Mandatory | Should -Contain $true
        }

        It "Should have -Enable and -Disable in separate parameter sets" {
            $command = Get-Command $Script:ScriptPath
            $enableParam = $command.Parameters['Enable']
            $disableParam = $command.Parameters['Disable']

            $enableParam.ParameterSets.Keys | Should -Contain 'Enable'
            $disableParam.ParameterSets.Keys | Should -Contain 'Disable'
        }

        It "Should validate MergeMethod values" {
            $command = Get-Command $Script:ScriptPath
            $param = $command.Parameters['MergeMethod']
            $validateSet = $param.Attributes | Where-Object { $_ -is [System.Management.Automation.ValidateSetAttribute] }
            $validateSet.ValidValues | Should -Contain 'MERGE'
            $validateSet.ValidValues | Should -Contain 'SQUASH'
            $validateSet.ValidValues | Should -Contain 'REBASE'
        }

        It "Should default MergeMethod to SQUASH" {
            $command = Get-Command $Script:ScriptPath
            $param = $command.Parameters['MergeMethod']
            $param.DefaultValue | Should -Be 'SQUASH'
        }
    }

    Context "Enable Auto-Merge" {

        BeforeEach {
            # Mock gh auth status to simulate authenticated state
            Mock gh {
                $global:LASTEXITCODE = 0
                return ''
            } -ParameterFilter { $args[0] -eq 'auth' -and $args[1] -eq 'status' }

            $Script:CallCount = 0
            $global:LASTEXITCODE = 0
        }

        It "Should enable auto-merge with default SQUASH method" {
            Mock gh {
                param($args)
                $Script:CallCount++
                if ($Script:CallCount -eq 1) {
                    # PR query
                    return (New-MockPRQueryResponse | ConvertTo-Json -Depth 10)
                }
                else {
                    # Enable mutation
                    return (New-MockEnableResponse -MergeMethod 'SQUASH' | ConvertTo-Json -Depth 10)
                }
            } -ParameterFilter { $args[0] -eq 'api' }

            $output = & $Script:ScriptPath -PullRequest 50 -Enable 2>&1
            $jsonOutput = $output | Where-Object { $_ -match '^\s*\{' } | Out-String
            $result = $jsonOutput | ConvertFrom-Json

            $result.Success | Should -Be $true
            $result.Action | Should -Be 'Enabled'
            $result.MergeMethod | Should -Be 'SQUASH'
        }

        It "Should enable auto-merge with specified method" {
            Mock gh {
                param($args)
                $Script:CallCount++
                if ($Script:CallCount -eq 1) {
                    return (New-MockPRQueryResponse | ConvertTo-Json -Depth 10)
                }
                else {
                    return (New-MockEnableResponse -MergeMethod 'REBASE' | ConvertTo-Json -Depth 10)
                }
            } -ParameterFilter { $args[0] -eq 'api' }

            $output = & $Script:ScriptPath -PullRequest 50 -Enable -MergeMethod REBASE 2>&1
            $jsonOutput = $output | Where-Object { $_ -match '^\s*\{' } | Out-String
            $result = $jsonOutput | ConvertFrom-Json

            $result.MergeMethod | Should -Be 'REBASE'
        }
    }

    Context "Disable Auto-Merge" {

        BeforeEach {
            # Mock gh auth status to simulate authenticated state
            Mock gh {
                $global:LASTEXITCODE = 0
                return ''
            } -ParameterFilter { $args[0] -eq 'auth' -and $args[1] -eq 'status' }

            $Script:CallCount = 0
            $global:LASTEXITCODE = 0
        }

        It "Should disable auto-merge when currently enabled" {
            Mock gh {
                param($args)
                $Script:CallCount++
                if ($Script:CallCount -eq 1) {
                    return (New-MockPRQueryResponse -HasAutoMerge | ConvertTo-Json -Depth 10)
                }
                else {
                    return (New-MockDisableResponse | ConvertTo-Json -Depth 10)
                }
            } -ParameterFilter { $args[0] -eq 'api' }

            $output = & $Script:ScriptPath -PullRequest 50 -Disable 2>&1
            $jsonOutput = $output | Where-Object { $_ -match '^\s*\{' } | Out-String
            $result = $jsonOutput | ConvertFrom-Json

            $result.Success | Should -Be $true
            $result.Action | Should -Be 'Disabled'
            $result.AutoMergeEnabled | Should -Be $false
        }

        It "Should report no change when already disabled" {
            Mock gh {
                return (New-MockPRQueryResponse | ConvertTo-Json -Depth 10)
            } -ParameterFilter { $args[0] -eq 'api' }

            $output = & $Script:ScriptPath -PullRequest 50 -Disable 2>&1
            $jsonOutput = $output | Where-Object { $_ -match '^\s*\{' } | Out-String
            $result = $jsonOutput | ConvertFrom-Json

            $result.Action | Should -Be 'NoChange'
            $result.Message | Should -BeLike '*already disabled*'
        }
    }

    Context "Error Handling" {

        It "Should handle PR not found" {
            Mock gh {
                $global:LASTEXITCODE = 1
                return 'Could not resolve to a PullRequest'
            } -ParameterFilter { $args[0] -eq 'api' }

            { & $Script:ScriptPath -PullRequest 99999 -Enable } | Should -Throw
        }

        It "Should handle auto-merge not enabled in repo" {
            $Script:CallCount = 0
            Mock gh {
                param($args)
                $Script:CallCount++
                if ($Script:CallCount -eq 1) {
                    $global:LASTEXITCODE = 0
                    return (New-MockPRQueryResponse | ConvertTo-Json -Depth 10)
                }
                else {
                    $global:LASTEXITCODE = 1
                    return 'Auto-merge is not allowed for this repository'
                }
            } -ParameterFilter { $args[0] -eq 'api' }

            { & $Script:ScriptPath -PullRequest 50 -Enable } | Should -Throw
        }
    }
}

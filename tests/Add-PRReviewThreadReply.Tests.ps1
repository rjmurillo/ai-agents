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

    # Helper function to create mock reply response
    function New-MockReplyResponse {
        param(
            [string]$ThreadId = 'PRRT_test123',
            [int]$DatabaseId = 123456789,
            [string]$Author = 'testuser'
        )

        return @{
            data = @{
                addPullRequestReviewThreadReply = @{
                    comment = @{
                        id = 'C_test123'
                        databaseId = $DatabaseId
                        url = "https://github.com/owner/repo/pull/1#discussion_r$DatabaseId"
                        createdAt = '2025-12-29T12:00:00Z'
                        author = @{ login = $Author }
                    }
                }
            }
        }
    }

    # Helper function to create mock resolve response
    function New-MockResolveResponse {
        param([bool]$IsResolved = $true)

        return @{
            data = @{
                resolveReviewThread = @{
                    thread = @{
                        id = 'PRRT_test123'
                        isResolved = $IsResolved
                    }
                }
            }
        }
    }
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

    Context "GraphQL Mutation" {

        BeforeEach {
            # Mock gh auth status to simulate authenticated state
            Mock gh {
                $global:LASTEXITCODE = 0
                return ''
            } -ParameterFilter { $args[0] -eq 'auth' -and $args[1] -eq 'status' }

            # Default mock for gh api graphql
            Mock gh {
                return (New-MockReplyResponse | ConvertTo-Json -Depth 10)
            } -ParameterFilter { $args[0] -eq 'api' -and $args[1] -eq 'graphql' }

            # Track LASTEXITCODE
            $global:LASTEXITCODE = 0
        }

        AfterEach {
            # Clean up mocks
            $global:LASTEXITCODE = $null
        }

        It "Should call GraphQL API with correct mutation" {
            # Re-mock auth to ensure it's available in this scope
            Mock gh {
                $global:LASTEXITCODE = 0
                return ''
            } -ParameterFilter { $args[0] -eq 'auth' -and $args[1] -eq 'status' }

            Mock gh {
                param($args)
                # Verify the query contains the mutation
                $queryArg = $args | Where-Object { $_ -match 'addPullRequestReviewThreadReply' }
                if ($queryArg) {
                    return (New-MockReplyResponse | ConvertTo-Json -Depth 10)
                }
                return '{}'
            } -ParameterFilter { $args[0] -eq 'api' }

            $result = & $Script:ScriptPath -ThreadId 'PRRT_test123' -Body 'Test reply' 2>&1

            Should -Invoke gh -Times 1 -ParameterFilter { $args[0] -eq 'api' }
        }

        It "Should return structured JSON output on success" {
            $output = & $Script:ScriptPath -ThreadId 'PRRT_test123' -Body 'Test reply' 2>&1

            # Find the JSON output line
            $jsonOutput = $output | Where-Object { $_ -match '^\s*\{' }
            $jsonOutput | Should -Not -BeNullOrEmpty
        }
    }

    Context "Thread Resolution" {

        BeforeEach {
            # Mock gh auth status to simulate authenticated state
            Mock gh {
                $global:LASTEXITCODE = 0
                return ''
            } -ParameterFilter { $args[0] -eq 'auth' -and $args[1] -eq 'status' }

            $Script:CallCount = 0
            Mock gh {
                param($args)
                $Script:CallCount++
                if ($Script:CallCount -eq 1) {
                    return (New-MockReplyResponse | ConvertTo-Json -Depth 10)
                }
                else {
                    return (New-MockResolveResponse | ConvertTo-Json -Depth 10)
                }
            } -ParameterFilter { $args[0] -eq 'api' }

            $global:LASTEXITCODE = 0
        }

        It "Should resolve thread when -Resolve is specified" {
            $output = & $Script:ScriptPath -ThreadId 'PRRT_test123' -Body 'Fixed' -Resolve 2>&1

            # Should call API twice: once for reply, once for resolve
            Should -Invoke gh -Times 2 -ParameterFilter { $args[0] -eq 'api' }
        }

        It "Should not resolve thread when -Resolve is not specified" {
            $output = & $Script:ScriptPath -ThreadId 'PRRT_test123' -Body 'Test reply' 2>&1

            # Should only call API once for reply
            Should -Invoke gh -Times 1 -ParameterFilter { $args[0] -eq 'api' }
        }
    }

    Context "Error Handling" {

        It "Should fail on empty body" {
            { & $Script:ScriptPath -ThreadId 'PRRT_test123' -Body '' } | Should -Throw
        }

        It "Should fail on invalid ThreadId format" {
            { & $Script:ScriptPath -ThreadId 'invalid_id' -Body 'Test' } | Should -Throw
        }

        It "Should handle API errors gracefully" {
            Mock gh {
                $global:LASTEXITCODE = 1
                return 'Error: Thread not found'
            } -ParameterFilter { $args[0] -eq 'api' }

            { & $Script:ScriptPath -ThreadId 'PRRT_test123' -Body 'Test' } | Should -Throw
        }
    }
}

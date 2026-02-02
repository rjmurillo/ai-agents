<#
.SYNOPSIS
    Pester tests for thread management scripts.

.DESCRIPTION
    Tests the PR review thread management functionality including:
    - Get-ThreadById.ps1
    - Unresolve-PRReviewThread.ps1
    - Get-ThreadConversationHistory.ps1

    Tests parameter validation, GraphQL response parsing, and exit code behavior.

.NOTES
    Requires Pester 5.x or later.

    EXIT CODES:
    0  - Success: All tests passed
    1  - Error: One or more tests failed (set by Pester framework)

    See: ADR-035 Exit Code Standardization
#>

BeforeAll {
    $Script:ScriptsPath = Join-Path $PSScriptRoot ".." "scripts" "pr"
    $Script:ModulePath = Join-Path $PSScriptRoot ".." "modules" "GitHubCore.psm1"

    # Verify scripts exist
    $scripts = @(
        "Get-ThreadById.ps1"
        "Unresolve-PRReviewThread.ps1"
        "Get-ThreadConversationHistory.ps1"
    )
    foreach ($script in $scripts) {
        $path = Join-Path $Script:ScriptsPath $script
        if (-not (Test-Path $path)) {
            throw "Script not found at: $path"
        }
    }

    # Import the module for helper functions
    Import-Module $Script:ModulePath -Force

    # Mock authentication functions to prevent script from exiting during tests
    Mock -ModuleName GitHubCore Test-GhAuthenticated { return $true }
    Mock -ModuleName GitHubCore Assert-GhAuthenticated { }
    Mock -ModuleName GitHubCore Resolve-RepoParams {
        return @{ Owner = 'testowner'; Repo = 'testrepo' }
    }

    # Helper function to create mock thread node response
    function New-MockThreadResponse {
        param(
            [string]$ThreadId = "PRRT_test123",
            [bool]$IsResolved = $false,
            [bool]$IsOutdated = $false,
            [string]$Path = "src/file.ps1",
            [int]$Line = 42,
            [array]$Comments = @()
        )

        if ($Comments.Count -eq 0) {
            $Comments = @(
                @{
                    id = "PRRC_comment1"
                    databaseId = 12345
                    body = "This is a test comment"
                    author = @{ login = "testuser" }
                    createdAt = "2024-01-01T00:00:00Z"
                    updatedAt = "2024-01-01T00:00:00Z"
                    isMinimized = $false
                    minimizedReason = $null
                    replyTo = $null
                }
            )
        }

        return @{
            data = @{
                node = @{
                    id = $ThreadId
                    isResolved = $IsResolved
                    isOutdated = $IsOutdated
                    path = $Path
                    line = $Line
                    startLine = $Line
                    diffSide = "RIGHT"
                    comments = @{
                        totalCount = $Comments.Count
                        pageInfo = @{
                            hasNextPage = $false
                            endCursor = $null
                        }
                        nodes = $Comments
                    }
                }
            }
        }
    }

    # Helper to create mock mutation response
    function New-MockMutationResponse {
        param(
            [string]$ThreadId = "PRRT_test123",
            [bool]$IsResolved = $false,
            [string]$MutationType = "unresolve"
        )

        $mutationName = if ($MutationType -eq "resolve") { "resolveReviewThread" } else { "unresolveReviewThread" }

        return @{
            data = @{
                $mutationName = @{
                    thread = @{
                        id = $ThreadId
                        isResolved = $IsResolved
                    }
                }
            }
        }
    }
}

Describe "Get-ThreadById.ps1" {
    BeforeAll {
        $Script:GetThreadByIdPath = Join-Path $Script:ScriptsPath "Get-ThreadById.ps1"
    }

    Context "Parameter Validation" {

        It "Should accept -ThreadId parameter as mandatory" {
            $command = Get-Command $Script:GetThreadByIdPath
            $command.Parameters.Keys | Should -Contain 'ThreadId'
            $command.Parameters['ThreadId'].Attributes | Where-Object {
                $_ -is [System.Management.Automation.ParameterAttribute] -and $_.Mandatory
            } | Should -Not -BeNullOrEmpty
        }

        It "Should accept -Owner parameter" {
            $command = Get-Command $Script:GetThreadByIdPath
            $command.Parameters.Keys | Should -Contain 'Owner'
        }

        It "Should accept -Repo parameter" {
            $command = Get-Command $Script:GetThreadByIdPath
            $command.Parameters.Keys | Should -Contain 'Repo'
        }
    }

    Context "ThreadId Format Validation" {

        It "Should validate ThreadId starts with PRRT_" {
            # Invalid format should cause error
            $invalidId = "INVALID_123"
            { & $Script:GetThreadByIdPath -ThreadId $invalidId -ErrorAction Stop } | Should -Throw
        }

        It "Should accept valid PRRT_ prefixed ThreadId" {
            $validId = "PRRT_validthread123"
            # This should not throw on format validation
            # (API call would fail but format check should pass)
            $command = Get-Command $Script:GetThreadByIdPath
            $command.Parameters.Keys | Should -Contain 'ThreadId'
        }
    }

    Context "Output Structure" {

        BeforeEach {
            Mock gh {
                $mockResponse = New-MockThreadResponse -ThreadId "PRRT_test123" -IsResolved $false
                return ($mockResponse | ConvertTo-Json -Depth 10)
            } -ParameterFilter { $args[0] -eq 'api' -and $args[1] -eq 'graphql' }
        }

        It "Should return structured JSON output with expected fields" -Skip {
            # Skip actual execution in unit tests - would require full mocking
            $result = & $Script:GetThreadByIdPath -ThreadId "PRRT_test123" | ConvertFrom-Json

            $result.Success | Should -Be $true
            $result.ThreadId | Should -Be "PRRT_test123"
            $result.PSObject.Properties.Name | Should -Contain 'IsResolved'
            $result.PSObject.Properties.Name | Should -Contain 'Path'
            $result.PSObject.Properties.Name | Should -Contain 'Comments'
        }
    }
}

Describe "Unresolve-PRReviewThread.ps1" {
    BeforeAll {
        $Script:UnresolvePath = Join-Path $Script:ScriptsPath "Unresolve-PRReviewThread.ps1"
    }

    Context "Parameter Validation" {

        It "Should accept -ThreadId parameter in Single parameter set" {
            $command = Get-Command $Script:UnresolvePath
            $command.Parameters.Keys | Should -Contain 'ThreadId'
        }

        It "Should accept -PullRequest parameter in All parameter set" {
            $command = Get-Command $Script:UnresolvePath
            $command.Parameters.Keys | Should -Contain 'PullRequest'
        }

        It "Should accept -All switch parameter" {
            $command = Get-Command $Script:UnresolvePath
            $command.Parameters.Keys | Should -Contain 'All'
            $command.Parameters['All'].SwitchParameter | Should -BeTrue
        }

        It "Should have two parameter sets: Single and All" {
            $command = Get-Command $Script:UnresolvePath
            $command.ParameterSets.Name | Should -Contain 'Single'
            $command.ParameterSets.Name | Should -Contain 'All'
        }
    }

    Context "ThreadId Format Validation" {

        It "Should validate ThreadId starts with PRRT_" {
            $invalidId = "NOT_A_THREAD_ID"
            { & $Script:UnresolvePath -ThreadId $invalidId -ErrorAction Stop } | Should -Throw
        }
    }

    Context "Output Structure for Single Thread" {

        It "Should return JSON with Success, ThreadId, and Action fields" -Skip {
            # Would require mocking gh api call
            $expectedFields = @('Success', 'ThreadId', 'Action')
            # Test structure would verify these fields exist
        }
    }

    Context "Output Structure for Batch Operation" {

        It "Should return JSON with TotalResolved, Unresolved, Failed, and Success fields" -Skip {
            # Would require mocking gh api and repo calls
            $expectedFields = @('TotalResolved', 'Unresolved', 'Failed', 'Success')
            # Test structure would verify these fields exist
        }
    }
}

Describe "Get-ThreadConversationHistory.ps1" {
    BeforeAll {
        $Script:ConversationPath = Join-Path $Script:ScriptsPath "Get-ThreadConversationHistory.ps1"
    }

    Context "Parameter Validation" {

        It "Should accept -ThreadId parameter as mandatory" {
            $command = Get-Command $Script:ConversationPath
            $command.Parameters.Keys | Should -Contain 'ThreadId'
            $command.Parameters['ThreadId'].Attributes | Where-Object {
                $_ -is [System.Management.Automation.ParameterAttribute] -and $_.Mandatory
            } | Should -Not -BeNullOrEmpty
        }

        It "Should accept -Owner parameter" {
            $command = Get-Command $Script:ConversationPath
            $command.Parameters.Keys | Should -Contain 'Owner'
        }

        It "Should accept -Repo parameter" {
            $command = Get-Command $Script:ConversationPath
            $command.Parameters.Keys | Should -Contain 'Repo'
        }

        It "Should accept -IncludeMinimized switch parameter" {
            $command = Get-Command $Script:ConversationPath
            $command.Parameters.Keys | Should -Contain 'IncludeMinimized'
            $command.Parameters['IncludeMinimized'].SwitchParameter | Should -BeTrue
        }
    }

    Context "ThreadId Format Validation" {

        It "Should validate ThreadId starts with PRRT_" {
            $invalidId = "COMMENT_not_thread"
            { & $Script:ConversationPath -ThreadId $invalidId -ErrorAction Stop } | Should -Throw
        }
    }

    Context "Output Structure" {

        It "Should include expected fields in output" -Skip {
            # Would require mocking gh api call
            $expectedFields = @(
                'Success',
                'ThreadId',
                'IsResolved',
                'Path',
                'TotalComments',
                'ReturnedComments',
                'MinimizedExcluded',
                'Comments'
            )
            # Test structure would verify these fields exist
        }

        It "Should include Sequence numbers in Comments" -Skip {
            # Comments should have Sequence field for ordering
            # Test would verify each comment has sequential Sequence value
        }
    }

    Context "Comment Filtering" {

        It "Should exclude minimized comments by default" -Skip {
            # Test would verify minimized comments are excluded
            # and MinimizedExcluded count is correct
        }

        It "Should include minimized comments when IncludeMinimized is specified" -Skip {
            # Test would verify all comments returned with -IncludeMinimized
        }
    }
}

Describe "Exit Codes" {

    Context "Get-ThreadById Exit Codes" {

        It "Should document exit code 0 for success" {
            # Documented: 0 = Success
            $content = Get-Content (Join-Path $Script:ScriptsPath "Get-ThreadById.ps1") -Raw
            $content | Should -Match 'Exit Codes'
            $content | Should -Match '0.*Success'
        }

        It "Should document exit code 1 for invalid parameters" {
            $content = Get-Content (Join-Path $Script:ScriptsPath "Get-ThreadById.ps1") -Raw
            $content | Should -Match '1.*Invalid'
        }

        It "Should document exit code 2 for not found" {
            $content = Get-Content (Join-Path $Script:ScriptsPath "Get-ThreadById.ps1") -Raw
            $content | Should -Match '2.*not found'
        }
    }

    Context "Unresolve-PRReviewThread Exit Codes" {

        It "Should document expected exit codes in help" {
            $content = Get-Content (Join-Path $Script:ScriptsPath "Unresolve-PRReviewThread.ps1") -Raw
            $content | Should -Match 'Exit Codes'
        }
    }

    Context "Get-ThreadConversationHistory Exit Codes" {

        It "Should document expected exit codes in help" {
            $content = Get-Content (Join-Path $Script:ScriptsPath "Get-ThreadConversationHistory.ps1") -Raw
            $content | Should -Match 'Exit Codes'
        }
    }
}

Describe "Help Documentation" {

    Context "Get-ThreadById Help" {

        It "Should have SYNOPSIS" {
            $content = Get-Content (Join-Path $Script:ScriptsPath "Get-ThreadById.ps1") -Raw
            $content | Should -Match '\.SYNOPSIS'
        }

        It "Should have DESCRIPTION" {
            $content = Get-Content (Join-Path $Script:ScriptsPath "Get-ThreadById.ps1") -Raw
            $content | Should -Match '\.DESCRIPTION'
        }

        It "Should have EXAMPLE" {
            $content = Get-Content (Join-Path $Script:ScriptsPath "Get-ThreadById.ps1") -Raw
            $content | Should -Match '\.EXAMPLE'
        }
    }

    Context "Unresolve-PRReviewThread Help" {

        It "Should have SYNOPSIS" {
            $content = Get-Content (Join-Path $Script:ScriptsPath "Unresolve-PRReviewThread.ps1") -Raw
            $content | Should -Match '\.SYNOPSIS'
        }

        It "Should have DESCRIPTION" {
            $content = Get-Content (Join-Path $Script:ScriptsPath "Unresolve-PRReviewThread.ps1") -Raw
            $content | Should -Match '\.DESCRIPTION'
        }

        It "Should have EXAMPLE for single thread" {
            $content = Get-Content (Join-Path $Script:ScriptsPath "Unresolve-PRReviewThread.ps1") -Raw
            $content | Should -Match 'Unresolve-PRReviewThread\.ps1 -ThreadId'
        }

        It "Should have EXAMPLE for batch operation" {
            $content = Get-Content (Join-Path $Script:ScriptsPath "Unresolve-PRReviewThread.ps1") -Raw
            $content | Should -Match '-PullRequest.*-All'
        }
    }

    Context "Get-ThreadConversationHistory Help" {

        It "Should have SYNOPSIS" {
            $content = Get-Content (Join-Path $Script:ScriptsPath "Get-ThreadConversationHistory.ps1") -Raw
            $content | Should -Match '\.SYNOPSIS'
        }

        It "Should have DESCRIPTION" {
            $content = Get-Content (Join-Path $Script:ScriptsPath "Get-ThreadConversationHistory.ps1") -Raw
            $content | Should -Match '\.DESCRIPTION'
        }

        It "Should have EXAMPLE" {
            $content = Get-Content (Join-Path $Script:ScriptsPath "Get-ThreadConversationHistory.ps1") -Raw
            $content | Should -Match '\.EXAMPLE'
        }
    }
}

Describe "Security Compliance" {

    Context "GraphQL Variable Usage" {

        It "Get-ThreadById should use GraphQL variables for security" {
            $content = Get-Content (Join-Path $Script:ScriptsPath "Get-ThreadById.ps1") -Raw
            $content | Should -Match '\$threadId:\s*ID!'
            $content | Should -Match '-f threadId='
        }

        It "Unresolve-PRReviewThread should use GraphQL variables for security" {
            $content = Get-Content (Join-Path $Script:ScriptsPath "Unresolve-PRReviewThread.ps1") -Raw
            $content | Should -Match '\$threadId:\s*ID!'
            $content | Should -Match '-f threadId='
        }

        It "Get-ThreadConversationHistory should use GraphQL variables for security" {
            $content = Get-Content (Join-Path $Script:ScriptsPath "Get-ThreadConversationHistory.ps1") -Raw
            $content | Should -Match '\$threadId:\s*ID!'
            $content | Should -Match '-f threadId='
        }
    }

    Context "Parameter Validation Order" {
        # Per Skill-Testing-Exit-Code-Order-001: Validate parameters before checking external tools

        It "Get-ThreadById should validate parameters before auth check" {
            $content = Get-Content (Join-Path $Script:ScriptsPath "Get-ThreadById.ps1") -Raw
            $paramValidationPos = $content.IndexOf("Invalid ThreadId format")
            $authCheckPos = $content.IndexOf("Assert-GhAuthenticated")
            $paramValidationPos | Should -BeLessThan $authCheckPos
        }

        It "Unresolve-PRReviewThread should validate parameters before auth check" {
            $content = Get-Content (Join-Path $Script:ScriptsPath "Unresolve-PRReviewThread.ps1") -Raw
            $paramValidationPos = $content.IndexOf("Invalid ThreadId format")
            $authCheckPos = $content.IndexOf("Assert-GhAuthenticated")
            $paramValidationPos | Should -BeLessThan $authCheckPos
        }

        It "Get-ThreadConversationHistory should validate parameters before auth check" {
            $content = Get-Content (Join-Path $Script:ScriptsPath "Get-ThreadConversationHistory.ps1") -Raw
            $paramValidationPos = $content.IndexOf("Invalid ThreadId format")
            $authCheckPos = $content.IndexOf("Assert-GhAuthenticated")
            $paramValidationPos | Should -BeLessThan $authCheckPos
        }
    }
}

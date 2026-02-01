<#
.SYNOPSIS
    Pester tests for Get-AllPRsWithComments function.

.DESCRIPTION
    Tests the GraphQL PR query function including:
    - Parameter validation
    - Single page response parsing
    - Cursor-based pagination
    - Date-based early termination
    - Filtering to only PRs with review comments
    - Error handling for GraphQL failures

.NOTES
    Requires Pester 5.x or later.

    EXIT CODES:
    0  - Success: All tests passed
    1  - Error: One or more tests failed (set by Pester framework)

    See: ADR-035 Exit Code Standardization
#>

BeforeAll {
    $Script:ModulePath = Join-Path $PSScriptRoot ".." "modules" "GitHubCore.psm1"

    if (-not (Test-Path $Script:ModulePath)) {
        throw "Module not found at: $Script:ModulePath"
    }

    Import-Module $Script:ModulePath -Force

    function New-MockPRNode {
        param(
            [int]$Number = 1,
            [string]$Title = "Test PR",
            [string]$State = "MERGED",
            [string]$AuthorLogin = "testuser",
            [string]$UpdatedAt = "2025-12-01T00:00:00Z",
            [bool]$HasComments = $true
        )

        $comments = if ($HasComments) {
            @(
                @{
                    id    = "PRRC_comment_$Number"
                    body  = "Review comment on PR $Number"
                    author = @{ login = "reviewer1" }
                    createdAt = $UpdatedAt
                    path  = "src/file.ps1"
                }
            )
        }
        else {
            @()
        }

        return @{
            number        = $Number
            title         = $Title
            state         = $State
            author        = @{ login = $AuthorLogin }
            createdAt     = $UpdatedAt
            updatedAt     = $UpdatedAt
            mergedAt      = $UpdatedAt
            closedAt      = $null
            reviewThreads = @{
                nodes = @(
                    @{
                        isResolved = $false
                        isOutdated = $false
                        comments   = @{ nodes = $comments }
                    }
                )
            }
        }
    }

    function New-MockGraphQLResponse {
        param(
            [array]$Nodes = @(),
            [bool]$HasNextPage = $false,
            [string]$EndCursor = $null
        )

        $response = @{
            data = @{
                repository = @{
                    pullRequests = @{
                        pageInfo = @{
                            hasNextPage = $HasNextPage
                            endCursor   = $EndCursor
                        }
                        nodes = $Nodes
                    }
                }
            }
        }

        return ($response | ConvertTo-Json -Depth 10)
    }
}

Describe "Get-AllPRsWithComments" {

    BeforeEach {
        # Reset LASTEXITCODE before each test
        $global:LASTEXITCODE = 0
    }

    Context "Parameter validation" {

        It "Requires Owner parameter" {
            { Get-AllPRsWithComments -Repo "testrepo" -Since (Get-Date) } |
                Should -Throw
        }

        It "Requires Repo parameter" {
            { Get-AllPRsWithComments -Owner "testowner" -Since (Get-Date) } |
                Should -Throw
        }

        It "Requires Since parameter" {
            { Get-AllPRsWithComments -Owner "testowner" -Repo "testrepo" } |
                Should -Throw
        }
    }

    Context "Single page of results" {

        It "Returns PRs with review comments" {
            $pr1 = New-MockPRNode -Number 1 -HasComments $true
            $pr2 = New-MockPRNode -Number 2 -HasComments $true
            $mockResponse = New-MockGraphQLResponse -Nodes @($pr1, $pr2)

            Mock -ModuleName GitHubCore gh { return $mockResponse }
            Mock -ModuleName GitHubCore -CommandName 'gh' -MockWith {
                $global:LASTEXITCODE = 0
                return $mockResponse
            }

            $result = Get-AllPRsWithComments -Owner "testowner" -Repo "testrepo" -Since ([datetime]"2025-01-01")

            $result | Should -HaveCount 2
            $result[0].number | Should -Be 1
            $result[1].number | Should -Be 2
        }

        It "Filters out PRs without review comments" {
            $prWithComments = New-MockPRNode -Number 1 -HasComments $true
            $prWithoutComments = New-MockPRNode -Number 2 -HasComments $false
            $mockResponse = New-MockGraphQLResponse -Nodes @($prWithComments, $prWithoutComments)

            Mock -ModuleName GitHubCore -CommandName 'gh' -MockWith {
                $global:LASTEXITCODE = 0
                return $mockResponse
            }

            $result = Get-AllPRsWithComments -Owner "testowner" -Repo "testrepo" -Since ([datetime]"2025-01-01")

            $result | Should -HaveCount 1
            $result[0].number | Should -Be 1
        }
    }

    Context "Date filtering" {

        It "Stops pagination when PRs are older than Since date" {
            $recentPR = New-MockPRNode -Number 1 -UpdatedAt "2025-12-15T00:00:00Z"
            $oldPR = New-MockPRNode -Number 2 -UpdatedAt "2025-01-01T00:00:00Z"
            $mockResponse = New-MockGraphQLResponse -Nodes @($recentPR, $oldPR) -HasNextPage $true -EndCursor "cursor1"

            Mock -ModuleName GitHubCore -CommandName 'gh' -MockWith {
                $global:LASTEXITCODE = 0
                return $mockResponse
            }

            $result = Get-AllPRsWithComments -Owner "testowner" -Repo "testrepo" -Since ([datetime]"2025-06-01")

            # Should only include the recent PR (old one triggers early stop)
            $result | Should -HaveCount 1
            $result[0].number | Should -Be 1
        }

        It "Returns empty array when no PRs match date range" {
            $oldPR = New-MockPRNode -Number 1 -UpdatedAt "2024-01-01T00:00:00Z"
            $mockResponse = New-MockGraphQLResponse -Nodes @($oldPR)

            Mock -ModuleName GitHubCore -CommandName 'gh' -MockWith {
                $global:LASTEXITCODE = 0
                return $mockResponse
            }

            $result = Get-AllPRsWithComments -Owner "testowner" -Repo "testrepo" -Since ([datetime]"2025-06-01")

            $result | Should -HaveCount 0
        }
    }

    Context "Pagination" {

        It "Follows cursor-based pagination across multiple pages" {
            $callCount = 0

            Mock -ModuleName GitHubCore -CommandName 'gh' -MockWith {
                $global:LASTEXITCODE = 0
                $callCount++

                if ($callCount -eq 1) {
                    $pr1 = New-MockPRNode -Number 1 -UpdatedAt "2025-12-15T00:00:00Z"
                    return (New-MockGraphQLResponse -Nodes @($pr1) -HasNextPage $true -EndCursor "cursor1")
                }
                else {
                    $pr2 = New-MockPRNode -Number 2 -UpdatedAt "2025-12-10T00:00:00Z"
                    return (New-MockGraphQLResponse -Nodes @($pr2) -HasNextPage $false)
                }
            }

            $result = Get-AllPRsWithComments -Owner "testowner" -Repo "testrepo" -Since ([datetime]"2025-01-01")

            $result | Should -HaveCount 2
        }

        It "Respects MaxPages limit" {
            Mock -ModuleName GitHubCore -CommandName 'gh' -MockWith {
                $global:LASTEXITCODE = 0
                $pr = New-MockPRNode -Number 1 -UpdatedAt "2025-12-15T00:00:00Z"
                return (New-MockGraphQLResponse -Nodes @($pr) -HasNextPage $true -EndCursor "cursor_next")
            }

            $result = Get-AllPRsWithComments -Owner "testowner" -Repo "testrepo" -Since ([datetime]"2025-01-01") -MaxPages 2

            # Should have called gh twice (MaxPages = 2), each returning 1 PR
            Should -Invoke -ModuleName GitHubCore -CommandName 'gh' -Times 2
        }
    }

    Context "Error handling" {

        It "Throws on GraphQL API failure" {
            Mock -ModuleName GitHubCore -CommandName 'gh' -MockWith {
                $global:LASTEXITCODE = 1
                return "API rate limit exceeded"
            }

            { Get-AllPRsWithComments -Owner "testowner" -Repo "testrepo" -Since ([datetime]"2025-01-01") } |
                Should -Throw "*Failed to query PRs*"
        }
    }
}

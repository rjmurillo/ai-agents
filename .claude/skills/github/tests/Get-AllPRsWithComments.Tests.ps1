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
    - GraphQL injection prevention via parameterized variables

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

    function New-MockGraphQLData {
        param(
            [array]$Nodes = @(),
            [bool]$HasNextPage = $false,
            [string]$EndCursor = $null
        )

        return @{
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
}

Describe "Get-AllPRsWithComments" {

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

        It "Rejects MaxPages value of 0" {
            { Get-AllPRsWithComments -Owner "testowner" -Repo "testrepo" -Since (Get-Date) -MaxPages 0 } |
                Should -Throw
        }

        It "Rejects negative MaxPages value" {
            { Get-AllPRsWithComments -Owner "testowner" -Repo "testrepo" -Since (Get-Date) -MaxPages -1 } |
                Should -Throw
        }
    }

    Context "Single page of results" {

        It "Returns PRs with review comments" {
            $pr1 = New-MockPRNode -Number 1 -HasComments $true
            $pr2 = New-MockPRNode -Number 2 -HasComments $true
            $mockData = New-MockGraphQLData -Nodes @($pr1, $pr2)

            Mock -ModuleName GitHubCore -CommandName 'Invoke-GhGraphQL' -MockWith {
                return $mockData
            }

            $result = Get-AllPRsWithComments -Owner "testowner" -Repo "testrepo" -Since ([datetime]"2025-01-01")

            $result | Should -HaveCount 2
            $result[0].number | Should -Be 1
            $result[1].number | Should -Be 2
        }

        It "Filters out PRs without review comments" {
            $prWithComments = New-MockPRNode -Number 1 -HasComments $true
            $prWithoutComments = New-MockPRNode -Number 2 -HasComments $false
            $mockData = New-MockGraphQLData -Nodes @($prWithComments, $prWithoutComments)

            Mock -ModuleName GitHubCore -CommandName 'Invoke-GhGraphQL' -MockWith {
                return $mockData
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
            $mockData = New-MockGraphQLData -Nodes @($recentPR, $oldPR) -HasNextPage $true -EndCursor "cursor1"

            Mock -ModuleName GitHubCore -CommandName 'Invoke-GhGraphQL' -MockWith {
                return $mockData
            }

            $result = Get-AllPRsWithComments -Owner "testowner" -Repo "testrepo" -Since ([datetime]"2025-06-01")

            # Should only include the recent PR (old one triggers early stop)
            $result | Should -HaveCount 1
            $result[0].number | Should -Be 1
        }

        It "Returns empty array when no PRs match date range" {
            $oldPR = New-MockPRNode -Number 1 -UpdatedAt "2024-01-01T00:00:00Z"
            $mockData = New-MockGraphQLData -Nodes @($oldPR)

            Mock -ModuleName GitHubCore -CommandName 'Invoke-GhGraphQL' -MockWith {
                return $mockData
            }

            $result = Get-AllPRsWithComments -Owner "testowner" -Repo "testrepo" -Since ([datetime]"2025-06-01")

            $result | Should -HaveCount 0
        }
    }

    Context "Pagination" {

        It "Follows cursor-based pagination across multiple pages" {
            $script:callCount = 0

            Mock -ModuleName GitHubCore -CommandName 'Invoke-GhGraphQL' -MockWith {
                $script:callCount++

                if ($script:callCount -eq 1) {
                    $pr1 = New-MockPRNode -Number 1 -UpdatedAt "2025-12-15T00:00:00Z"
                    return (New-MockGraphQLData -Nodes @($pr1) -HasNextPage $true -EndCursor "cursor1")
                }
                else {
                    $pr2 = New-MockPRNode -Number 2 -UpdatedAt "2025-12-10T00:00:00Z"
                    return (New-MockGraphQLData -Nodes @($pr2) -HasNextPage $false)
                }
            }

            $result = Get-AllPRsWithComments -Owner "testowner" -Repo "testrepo" -Since ([datetime]"2025-01-01")

            $result | Should -HaveCount 2
        }

        It "Respects MaxPages limit" {
            Mock -ModuleName GitHubCore -CommandName 'Invoke-GhGraphQL' -MockWith {
                $pr = New-MockPRNode -Number 1 -UpdatedAt "2025-12-15T00:00:00Z"
                return (New-MockGraphQLData -Nodes @($pr) -HasNextPage $true -EndCursor "cursor_next")
            }

            $result = Get-AllPRsWithComments -Owner "testowner" -Repo "testrepo" -Since ([datetime]"2025-01-01") -MaxPages 2

            # Should have called Invoke-GhGraphQL twice (MaxPages = 2), each returning 1 PR
            Should -Invoke -ModuleName GitHubCore -CommandName 'Invoke-GhGraphQL' -Times 2
        }
    }

    Context "GraphQL variable parameterization" {

        It "Passes Owner and Repo as GraphQL variables, not interpolated into query" {
            Mock -ModuleName GitHubCore -CommandName 'Invoke-GhGraphQL' -MockWith {
                $mockData = New-MockGraphQLData -Nodes @()
                return $mockData
            }

            Get-AllPRsWithComments -Owner 'injection"attempt' -Repo 'mal}icious' -Since ([datetime]"2025-01-01")

            # Verify variables were passed via the -Variables parameter
            Should -Invoke -ModuleName GitHubCore -CommandName 'Invoke-GhGraphQL' -Times 1 -ParameterFilter {
                $Variables.owner -eq 'injection"attempt' -and
                $Variables.repo -eq 'mal}icious'
            }
        }

        It "Uses parameterized query with GraphQL variable declarations" {
            Mock -ModuleName GitHubCore -CommandName 'Invoke-GhGraphQL' -MockWith {
                $mockData = New-MockGraphQLData -Nodes @()
                return $mockData
            }

            Get-AllPRsWithComments -Owner "testowner" -Repo "testrepo" -Since ([datetime]"2025-01-01")

            # Verify the query uses variable declarations, not string interpolation
            Should -Invoke -ModuleName GitHubCore -CommandName 'Invoke-GhGraphQL' -Times 1 -ParameterFilter {
                $Query -match '\$owner:\s*String!' -and
                $Query -match '\$repo:\s*String!' -and
                $Query -notmatch '"testowner"' -and
                $Query -notmatch '"testrepo"'
            }
        }

        It "Passes cursor as GraphQL variable for pagination" {
            $script:callCount = 0

            Mock -ModuleName GitHubCore -CommandName 'Invoke-GhGraphQL' -MockWith {
                $script:callCount++

                if ($script:callCount -eq 1) {
                    $pr1 = New-MockPRNode -Number 1 -UpdatedAt "2025-12-15T00:00:00Z"
                    return (New-MockGraphQLData -Nodes @($pr1) -HasNextPage $true -EndCursor "test_cursor_abc")
                }
                else {
                    return (New-MockGraphQLData -Nodes @() -HasNextPage $false)
                }
            }

            Get-AllPRsWithComments -Owner "testowner" -Repo "testrepo" -Since ([datetime]"2025-01-01")

            # Second call should include cursor variable
            Should -Invoke -ModuleName GitHubCore -CommandName 'Invoke-GhGraphQL' -Times 1 -ParameterFilter {
                $Variables.cursor -eq "test_cursor_abc"
            }
        }
    }

    Context "Error handling" {

        It "Throws on GraphQL API failure" {
            Mock -ModuleName GitHubCore -CommandName 'Invoke-GhGraphQL' -MockWith {
                throw "GraphQL request failed: API rate limit exceeded"
            }

            { Get-AllPRsWithComments -Owner "testowner" -Repo "testrepo" -Since ([datetime]"2025-01-01") } |
                Should -Throw "*GraphQL request failed*"
        }
    }
}

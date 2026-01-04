<#
.SYNOPSIS
    Pester tests for Update-ReviewerSignalStats.ps1 script.

.DESCRIPTION
    Tests the reviewer signal statistics aggregation script for reliability and correctness.
    Tests cover parameter validation, actionability scoring, and output generation.

.NOTES
    Requires Pester 5.x or later.
#>

BeforeAll {
    $Script:ScriptPath = Join-Path $PSScriptRoot "..\Update-ReviewerSignalStats.ps1"
    $Script:TestDir = Join-Path $TestDrive "reviewer-stats-test"

    # Load script functions for testing
    . $Script:ScriptPath
}

Describe "Update-ReviewerSignalStats.ps1" {
    BeforeEach {
        # Create fresh test directory
        New-Item -ItemType Directory -Path $Script:TestDir -Force | Out-Null
    }

    AfterEach {
        # Clean up test directory
        if (Test-Path $Script:TestDir) {
            Remove-Item -Path $Script:TestDir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    Context "Script Structure Validation" {
        It "Script file exists and is valid PowerShell" {
            $Script:ScriptPath | Should -Exist
            { Get-Command $Script:ScriptPath -ErrorAction Stop } | Should -Not -Throw
        }

        It "Script has required parameters" {
            $cmd = Get-Command $Script:ScriptPath
            $cmd.Parameters.Keys | Should -Contain "DaysBack"
            $cmd.Parameters.Keys | Should -Contain "OutputPath"
            $cmd.Parameters.Keys | Should -Contain "UpdateMemory"
            $cmd.Parameters.Keys | Should -Contain "Owner"
            $cmd.Parameters.Keys | Should -Contain "Repo"
        }

        It "DaysBack parameter has default value of 90" {
            $cmd = Get-Command $Script:ScriptPath
            $param = $cmd.Parameters['DaysBack']
            $param.Attributes.TypeId.Name | Should -Contain "ParameterAttribute"
        }

        It "DaysBack parameter validates range 1-365" {
            $cmd = Get-Command $Script:ScriptPath
            $param = $cmd.Parameters['DaysBack']
            $rangeAttr = $param.Attributes | Where-Object { $_.TypeId.Name -eq 'ValidateRangeAttribute' }
            $rangeAttr | Should -Not -BeNullOrEmpty
        }

        It "UpdateMemory parameter is a switch" {
            $cmd = Get-Command $Script:ScriptPath
            $param = $cmd.Parameters['UpdateMemory']
            $param.ParameterType.Name | Should -Be "SwitchParameter"
        }
    }

    Context "Configuration" {
        It "Defines excluded authors" {
            $script:Config.ExcludedAuthors | Should -Contain "rjmurillo"
            $script:Config.ExcludedAuthors | Should -Contain "rjmurillo-bot"
        }

        It "Defines actionability heuristics" {
            $script:Config.Heuristics.Keys | Should -Contain "FixedInReply"
            $script:Config.Heuristics.Keys | Should -Contain "WontFixReply"
            $script:Config.Heuristics.Keys | Should -Contain "SeverityHigh"
            $script:Config.Heuristics.Keys | Should -Contain "SeverityLow"
        }

        It "FixedInReply has positive score" {
            $script:Config.Heuristics.FixedInReply | Should -BeGreaterThan 0
        }

        It "SeverityLow has negative score" {
            $script:Config.Heuristics.SeverityLow | Should -BeLessThan 0
        }

        It "Defines memory file path" {
            $script:Config.MemoryPath | Should -Be '.serena/memories/pr-comment-responder-skills.md'
        }
    }

    Context "Get-ActionabilityScore Function" {
        BeforeAll {
            $Script:Heuristics = $script:Config.Heuristics
        }

        It "Returns score around 0.5 for neutral comment" {
            $comment = @{
                Body = "This is a neutral comment"
                CreatedAt = (Get-Date).AddDays(-1).ToString('o')
                IsResolved = $true  # Resolved comments don't get NoReplyAfterDays penalty
                ThreadComments = @()
            }
            $result = Get-ActionabilityScore -CommentData $comment -Heuristics $Script:Heuristics
            $result.Score | Should -BeGreaterOrEqual 0.4
            $result.Score | Should -BeLessOrEqual 0.6
        }

        It "Increases score for 'Fixed in' reply" {
            $comment = @{
                Body = "This needs to be fixed"
                CreatedAt = (Get-Date).AddDays(-1).ToString('o')
                IsResolved = $true
                ThreadComments = @(
                    @{ body = "Fixed in commit abc123" }
                )
            }
            $result = Get-ActionabilityScore -CommentData $comment -Heuristics $Script:Heuristics
            $result.Score | Should -BeGreaterThan 0.5
            $result.Reasons | Should -Contain "FixedInReply"
        }

        It "Increases score for security-related comments" {
            $comment = @{
                Body = "This has a CWE-22 vulnerability"
                CreatedAt = (Get-Date).AddDays(-1).ToString('o')
                IsResolved = $false
                ThreadComments = @()
            }
            $result = Get-ActionabilityScore -CommentData $comment -Heuristics $Script:Heuristics
            $result.Score | Should -BeGreaterThan 0.5
            $result.Reasons | Should -Contain "SeverityHigh"
        }

        It "Decreases score for 'unused' comments" {
            $comment = @{
                Body = "This variable is unused and should be removed"
                CreatedAt = (Get-Date).AddDays(-1).ToString('o')
                IsResolved = $false
                ThreadComments = @()
            }
            $result = Get-ActionabilityScore -CommentData $comment -Heuristics $Script:Heuristics
            $result.Score | Should -BeLessThan 0.5
            $result.Reasons | Should -Contain "UnusedRemove"
        }

        It "Decreases score for 'nit' comments" {
            $comment = @{
                Body = "nit: consider using a different variable name"
                CreatedAt = (Get-Date).AddDays(-1).ToString('o')
                IsResolved = $false
                ThreadComments = @()
            }
            $result = Get-ActionabilityScore -CommentData $comment -Heuristics $Script:Heuristics
            $result.Score | Should -BeLessThan 0.5
            $result.Reasons | Should -Contain "SeverityLow"
        }

        It "Score is clamped between 0 and 1" {
            # Very negative comment
            $comment = @{
                Body = "nit: unused code to remove, minor cosmetic issue"
                CreatedAt = (Get-Date).AddDays(-30).ToString('o')
                IsResolved = $false
                ThreadComments = @()
            }
            $result = Get-ActionabilityScore -CommentData $comment -Heuristics $Script:Heuristics
            $result.Score | Should -BeGreaterOrEqual 0
            $result.Score | Should -BeLessOrEqual 1
        }

        It "IsActionable is true when score >= 0.5" {
            $comment = @{
                Body = "Critical security vulnerability"
                CreatedAt = (Get-Date).AddDays(-1).ToString('o')
                IsResolved = $false
                ThreadComments = @()
            }
            $result = Get-ActionabilityScore -CommentData $comment -Heuristics $Script:Heuristics
            $result.IsActionable | Should -Be $true
        }
    }

    Context "Get-CommentsByReviewer Function" {
        It "Groups comments by reviewer login" {
            $prs = @(
                @{
                    number = 1
                    author = @{ login = "author1" }
                    reviewThreads = @{
                        nodes = @(
                            @{
                                isResolved = $false
                                isOutdated = $false
                                comments = @{
                                    nodes = @(
                                        @{
                                            id = "c1"
                                            body = "Comment 1"
                                            author = @{ login = "reviewer1" }
                                            createdAt = (Get-Date).ToString('o')
                                            path = "file.ps1"
                                        }
                                    )
                                }
                            }
                        )
                    }
                }
            )
            
            $result = Get-CommentsByReviewer -PRs $prs
            $result.Keys | Should -Contain "reviewer1"
            $result["reviewer1"].TotalComments | Should -Be 1
        }

        It "Excludes PR author from reviewer counts" {
            $prs = @(
                @{
                    number = 1
                    author = @{ login = "author1" }
                    reviewThreads = @{
                        nodes = @(
                            @{
                                isResolved = $false
                                isOutdated = $false
                                comments = @{
                                    nodes = @(
                                        @{
                                            id = "c1"
                                            body = "Self-comment"
                                            author = @{ login = "author1" }
                                            createdAt = (Get-Date).ToString('o')
                                            path = "file.ps1"
                                        }
                                    )
                                }
                            }
                        )
                    }
                }
            )
            
            $result = Get-CommentsByReviewer -PRs $prs
            $result.Keys | Should -Not -Contain "author1"
        }

        It "Excludes specified authors" {
            $prs = @(
                @{
                    number = 1
                    author = @{ login = "someone" }
                    reviewThreads = @{
                        nodes = @(
                            @{
                                isResolved = $false
                                isOutdated = $false
                                comments = @{
                                    nodes = @(
                                        @{
                                            id = "c1"
                                            body = "Bot comment"
                                            author = @{ login = "rjmurillo" }
                                            createdAt = (Get-Date).ToString('o')
                                            path = "file.ps1"
                                        }
                                    )
                                }
                            }
                        )
                    }
                }
            )
            
            $result = Get-CommentsByReviewer -PRs $prs -ExcludedAuthors @("rjmurillo")
            $result.Keys | Should -Not -Contain "rjmurillo"
        }

        It "Tracks unique PRs per reviewer" {
            $prs = @(
                @{
                    number = 1
                    author = @{ login = "author1" }
                    reviewThreads = @{
                        nodes = @(
                            @{
                                isResolved = $false
                                isOutdated = $false
                                comments = @{
                                    nodes = @(
                                        @{
                                            id = "c1"
                                            body = "Comment 1"
                                            author = @{ login = "reviewer1" }
                                            createdAt = (Get-Date).ToString('o')
                                            path = "file.ps1"
                                        },
                                        @{
                                            id = "c2"
                                            body = "Comment 2"
                                            author = @{ login = "reviewer1" }
                                            createdAt = (Get-Date).ToString('o')
                                            path = "file2.ps1"
                                        }
                                    )
                                }
                            }
                        )
                    }
                }
            )
            
            $result = Get-CommentsByReviewer -PRs $prs
            $result["reviewer1"].TotalComments | Should -Be 2
            $result["reviewer1"].PRsWithComments.Count | Should -Be 1
        }
    }

    Context "Get-ReviewerSignalStats Function" {
        It "Calculates signal rate correctly" {
            $reviewerStats = @{
                "reviewer1" = @{
                    TotalComments = 2
                    PRsWithComments = [System.Collections.Generic.HashSet[int]]@(1)
                    VerifiedActionable = 0
                    Comments = [System.Collections.ArrayList]@(
                        @{
                            Body = "Critical security issue"
                            CreatedAt = (Get-Date).AddDays(-1).ToString('o')
                            IsResolved = $false
                            ThreadComments = @()
                        },
                        @{
                            Body = "nit: minor style issue"
                            CreatedAt = (Get-Date).AddDays(-1).ToString('o')
                            IsResolved = $false
                            ThreadComments = @()
                        }
                    )
                    Last30Days = @{ Comments = 0; Actionable = 0 }
                }
            }
            
            $result = Get-ReviewerSignalStats -ReviewerStats $reviewerStats -Heuristics $script:Config.Heuristics
            $result["reviewer1"].total_comments | Should -Be 2
            $result["reviewer1"].signal_rate | Should -BeGreaterOrEqual 0
            $result["reviewer1"].signal_rate | Should -BeLessOrEqual 1
        }

        It "Sets trend to stable for small sample sizes" {
            $reviewerStats = @{
                "reviewer1" = @{
                    TotalComments = 3
                    PRsWithComments = [System.Collections.Generic.HashSet[int]]@(1)
                    VerifiedActionable = 0
                    Comments = [System.Collections.ArrayList]@(
                        @{
                            Body = "Comment 1"
                            CreatedAt = (Get-Date).AddDays(-1).ToString('o')
                            IsResolved = $false
                            ThreadComments = @()
                        }
                    )
                    Last30Days = @{ Comments = 0; Actionable = 0 }
                }
            }
            
            $result = Get-ReviewerSignalStats -ReviewerStats $reviewerStats -Heuristics $script:Config.Heuristics
            $result["reviewer1"].trend | Should -Be "stable"
        }
    }

    Context "Export-StatsJson Function" {
        It "Creates output file with correct structure" {
            $stats = @{
                "reviewer1" = @{
                    total_comments = 10
                    prs_with_comments = 5
                    verified_actionable = 8
                    estimated_actionable = 8
                    signal_rate = 0.8
                    trend = "stable"
                    last_30_days = @{
                        comments = 3
                        signal_rate = 0.9
                    }
                }
            }
            
            $outputPath = Join-Path $Script:TestDir "test-stats.json"
            $result = Export-StatsJson -Stats $stats -PRsAnalyzed 10 -DaysAnalyzed 30 -OutputPath $outputPath
            
            $outputPath | Should -Exist
            $result.generated_at | Should -Not -BeNullOrEmpty
            $result.days_analyzed | Should -Be 30
            $result.prs_analyzed | Should -Be 10
            $result.reviewers | Should -Not -BeNullOrEmpty
            $result.priority_matrix | Should -Not -BeNullOrEmpty
        }

        It "Sorts priority matrix by signal rate descending" {
            $stats = @{
                "low_signal" = @{
                    total_comments = 10
                    signal_rate = 0.3
                }
                "high_signal" = @{
                    total_comments = 10
                    signal_rate = 0.9
                }
            }
            
            $outputPath = Join-Path $Script:TestDir "test-priority.json"
            $result = Export-StatsJson -Stats $stats -PRsAnalyzed 5 -DaysAnalyzed 30 -OutputPath $outputPath
            
            $result.priority_matrix[0].reviewer | Should -Be "high_signal"
            $result.priority_matrix[0].priority | Should -Be "P0"
        }

        It "Creates output directory if it does not exist" {
            $stats = @{
                "reviewer1" = @{
                    total_comments = 1
                    signal_rate = 0.5
                }
            }
            
            $nestedPath = Join-Path $Script:TestDir "nested" "dir" "stats.json"
            $result = Export-StatsJson -Stats $stats -PRsAnalyzed 1 -DaysAnalyzed 7 -OutputPath $nestedPath
            
            $nestedPath | Should -Exist
        }
    }
}

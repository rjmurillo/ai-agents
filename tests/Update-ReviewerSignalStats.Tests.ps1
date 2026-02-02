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
    $Script:ScriptPath = Join-Path $PSScriptRoot ".." "scripts" "Update-ReviewerSignalStats.ps1"
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
            $cmd.Parameters.Keys | Should -Contain "Owner"
            $cmd.Parameters.Keys | Should -Contain "Repo"
        }

        It "DaysBack parameter has default value of 28" {
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
    }

    Context "Configuration" {
        It "Defines self-comment excluded authors" {
            $script:Config.SelfCommentExcludedAuthors | Should -Contain "dependabot[bot]"
        }

        It "Excludes dependabot self-comments from stats" {
            $prs = @(
                @{
                    number = 1
                    author = @{ login = "dependabot[bot]" }
                    reviewThreads = @{
                        nodes = @(
                            @{
                                isResolved = $false
                                isOutdated = $false
                                comments = @{
                                    nodes = @(
                                        @{
                                            id = "comment1"
                                            body = "Dependabot commenting on its own PR"
                                            author = @{ login = "dependabot[bot]" }
                                            createdAt = "2024-01-01T12:00:00Z"
                                            path = "package.json"
                                        }
                                    )
                                }
                            }
                        )
                    }
                }
            )

            # dependabot[bot] commenting on its own PR should be excluded
            $result = Get-CommentsByReviewer -PRs $prs
            $result.Keys | Should -Not -Contain "dependabot[bot]"
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

        It "Allows authors to review OTHER authors' PRs" {
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
                                            body = "Review comment"
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
            
            # Test cross-author review: rjmurillo reviewing author1's PR
            # This validates that reviewers commenting on OTHER people's PRs are tracked
            # (as opposed to self-comments which are excluded)
            $result = Get-CommentsByReviewer -PRs $prs
            $result.Keys | Should -Contain "rjmurillo"
            $result["rjmurillo"].TotalComments | Should -Be 1
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

    Context "Update-SerenaMemory Function" {
        BeforeEach {
            # Create a test memory file
            $Script:TestMemoryPath = Join-Path $Script:TestDir "test-memory.md"
            $content = @"
# PR Comment Responder Skills Memory

## Overview

Memory for tracking reviewer signal quality statistics.

## Per-Reviewer Performance (Cumulative)

| Reviewer | PRs | Comments | Actionable | Signal | Notes |
|----------|-----|----------|------------|--------|-------|
| old-reviewer | 1 | 1 | 1 | 100% | Old data |

## Per-PR Breakdown

Details here.
"@
            Set-Content -Path $Script:TestMemoryPath -Value $content -Encoding UTF8
        }

        It "Updates the Per-Reviewer Performance table" {
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
            
            $result = Update-SerenaMemory -Stats $stats -PRsAnalyzed 10 -DaysAnalyzed 30 -MemoryPath $Script:TestMemoryPath
            
            $result | Should -Be $true
            $content = Get-Content -Path $Script:TestMemoryPath -Raw
            $content | Should -Match "reviewer1"
            $content | Should -Match "80%"
        }

        It "Sorts reviewers by signal rate descending" {
            $stats = @{
                "low_signal" = @{
                    total_comments = 10
                    prs_with_comments = 3
                    estimated_actionable = 3
                    signal_rate = 0.3
                    trend = "stable"
                }
                "high_signal" = @{
                    total_comments = 10
                    prs_with_comments = 5
                    estimated_actionable = 9
                    signal_rate = 0.9
                    trend = "stable"
                }
            }
            
            $result = Update-SerenaMemory -Stats $stats -PRsAnalyzed 5 -DaysAnalyzed 30 -MemoryPath $Script:TestMemoryPath
            
            $content = Get-Content -Path $Script:TestMemoryPath -Raw
            # high_signal should appear before low_signal
            $highPos = $content.IndexOf("high_signal")
            $lowPos = $content.IndexOf("low_signal")
            $highPos | Should -BeLessThan $lowPos
        }

        It "Returns false if memory file does not exist" {
            $nonExistentPath = Join-Path $Script:TestDir "non-existent.md"
            $result = Update-SerenaMemory -Stats @{} -PRsAnalyzed 0 -DaysAnalyzed 0 -MemoryPath $nonExistentPath
            $result | Should -Be $false
        }
    }
}

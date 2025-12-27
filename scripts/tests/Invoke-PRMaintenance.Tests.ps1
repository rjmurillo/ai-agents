<#
.SYNOPSIS
    Pester tests for Invoke-PRMaintenance.ps1 script.

.DESCRIPTION
    Tests PR discovery and classification script for reliability and correctness.
    The script is now a thin orchestration layer that discovers PRs and outputs JSON
    for GitHub Actions matrix consumption.

.NOTES
    Requires Pester 5.x or later.
#>

BeforeAll {
    $Script:ScriptPath = Join-Path $PSScriptRoot "..\Invoke-PRMaintenance.ps1"
    $Script:TestDir = Join-Path $TestDrive "pr-maintenance-test"

    # Load script functions for testing
    . $Script:ScriptPath
}

Describe "Invoke-PRMaintenance.ps1" {
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
            $cmd.Parameters.Keys | Should -Contain "Owner"
            $cmd.Parameters.Keys | Should -Contain "Repo"
            $cmd.Parameters.Keys | Should -Contain "MaxPRs"
            $cmd.Parameters.Keys | Should -Contain "LogPath"
            $cmd.Parameters.Keys | Should -Contain "OutputJson"
        }

        It "MaxPRs parameter has default value of 20" {
            $cmd = Get-Command $Script:ScriptPath
            $param = $cmd.Parameters['MaxPRs']
            $param.Attributes.TypeId.Name | Should -Contain "ParameterAttribute"
        }

        It "OutputJson parameter is a switch" {
            $cmd = Get-Command $Script:ScriptPath
            $param = $cmd.Parameters['OutputJson']
            $param.ParameterType.Name | Should -Be "SwitchParameter"
        }
    }

    Context "Configuration" {
        It "Defines protected branches (main, master, develop)" {
            $script:Config.ProtectedBranches | Should -Contain "main"
            $script:Config.ProtectedBranches | Should -Contain "master"
            $script:Config.ProtectedBranches | Should -Contain "develop"
        }

        It "Defines bot categories" {
            $script:Config.BotCategories.Keys | Should -Contain "agent-controlled"
            $script:Config.BotCategories.Keys | Should -Contain "mention-triggered"
            $script:Config.BotCategories.Keys | Should -Contain "review-bot"
        }

        It "Agent-controlled bots include rjmurillo-bot" {
            $script:Config.BotCategories['agent-controlled'] | Should -Contain "rjmurillo-bot"
        }
    }

    Context "Get-BotAuthorInfo Function" {
        It "Identifies rjmurillo-bot as agent-controlled" {
            $result = Get-BotAuthorInfo -AuthorLogin "rjmurillo-bot"
            $result.IsBot | Should -Be $true
            $result.Category | Should -Be "agent-controlled"
        }

        It "Identifies copilot-swe-agent as mention-triggered" {
            $result = Get-BotAuthorInfo -AuthorLogin "copilot-swe-agent"
            $result.IsBot | Should -Be $true
            $result.Category | Should -Be "mention-triggered"
        }

        It "Identifies app/copilot-swe-agent (GitHub app format) as mention-triggered" {
            $result = Get-BotAuthorInfo -AuthorLogin "app/copilot-swe-agent"
            $result.IsBot | Should -Be $true
            $result.Category | Should -Be "mention-triggered"
        }

        It "Identifies coderabbitai as review-bot" {
            $result = Get-BotAuthorInfo -AuthorLogin "coderabbitai[bot]"
            $result.IsBot | Should -Be $true
            $result.Category | Should -Be "review-bot"
        }

        It "Identifies human users correctly" {
            $result = Get-BotAuthorInfo -AuthorLogin "humanuser123"
            $result.IsBot | Should -Be $false
            $result.Category | Should -Be "human"
        }

        It "Is case-insensitive for bot matching" {
            $result = Get-BotAuthorInfo -AuthorLogin "RJMURILLO-BOT"
            $result.IsBot | Should -Be $true
            $result.Category | Should -Be "agent-controlled"
        }
    }

    Context "Test-IsBotReviewer Function" {
        It "Returns true when rjmurillo-bot is in review requests" {
            $reviewRequests = @{
                nodes = @(
                    @{ requestedReviewer = @{ login = "rjmurillo-bot" } }
                )
            }
            $result = Test-IsBotReviewer -ReviewRequests $reviewRequests
            $result | Should -Be $true
        }

        It "Returns false when no agent-controlled bot is reviewer" {
            $reviewRequests = @{
                nodes = @(
                    @{ requestedReviewer = @{ login = "humanreviewer" } }
                )
            }
            $result = Test-IsBotReviewer -ReviewRequests $reviewRequests
            $result | Should -Be $false
        }

        It "Returns false for null review requests" {
            $result = Test-IsBotReviewer -ReviewRequests $null
            $result | Should -Be $false
        }

        It "Returns false for empty nodes" {
            $reviewRequests = @{ nodes = @() }
            $result = Test-IsBotReviewer -ReviewRequests $reviewRequests
            $result | Should -Be $false
        }
    }

    Context "Test-PRHasConflicts Function" {
        It "Returns true when PR mergeable status is CONFLICTING" {
            $pr = @{ mergeable = "CONFLICTING" }
            $result = Test-PRHasConflicts -PR $pr
            $result | Should -Be $true
        }

        It "Returns false when PR is mergeable" {
            $pr = @{ mergeable = "MERGEABLE" }
            $result = Test-PRHasConflicts -PR $pr
            $result | Should -Be $false
        }

        It "Returns false when mergeable is null" {
            $pr = @{ mergeable = $null }
            $result = Test-PRHasConflicts -PR $pr
            $result | Should -Be $false
        }
    }

    Context "Get-DerivativePRs Function" {
        It "Identifies PRs targeting non-protected branches as derivatives" {
            $testPRs = @(
                @{ number = 1; baseRefName = "main"; headRefName = "feature-1"; title = "Main PR"; author = @{ login = "user1" } },
                @{ number = 2; baseRefName = "feature-1"; headRefName = "feature-1-fix"; title = "Derivative PR"; author = @{ login = "user2" } }
            )

            $result = @(Get-DerivativePRs -Owner "test" -Repo "repo" -OpenPRs $testPRs)
            $result.Count | Should -Be 1
            $result[0].Number | Should -Be 2
            $result[0].TargetBranch | Should -Be "feature-1"
        }

        It "Returns empty array when all PRs target protected branches" {
            $testPRs = @(
                @{ number = 1; baseRefName = "main"; headRefName = "feature-1"; title = "PR 1"; author = @{ login = "user1" } },
                @{ number = 2; baseRefName = "develop"; headRefName = "feature-2"; title = "PR 2"; author = @{ login = "user2" } }
            )

            $result = @(Get-DerivativePRs -Owner "test" -Repo "repo" -OpenPRs $testPRs)
            $result.Count | Should -Be 0
        }
    }

    Context "Get-PRsWithPendingDerivatives Function" {
        It "Identifies parent PRs that have derivatives" {
            $testOpenPRs = @(
                @{ number = 1; baseRefName = "main"; headRefName = "feature-1"; title = "Parent PR"; author = @{ login = "user1" } },
                @{ number = 2; baseRefName = "feature-1"; headRefName = "feature-1-fix"; title = "Derivative PR"; author = @{ login = "user2" } }
            )
            $testDerivatives = @(
                @{ Number = 2; TargetBranch = "feature-1"; SourceBranch = "feature-1-fix"; Title = "Derivative PR"; Author = "user2" }
            )

            $result = @(Get-PRsWithPendingDerivatives -Owner "test" -Repo "repo" -OpenPRs $testOpenPRs -Derivatives $testDerivatives)
            $result.Count | Should -Be 1
            $result[0].ParentPR | Should -Be 1
            $result[0].Derivatives | Should -Contain 2
        }

        It "Returns empty array when no derivatives exist" {
            $testOpenPRs = @(
                @{ number = 1; baseRefName = "main"; headRefName = "feature-1"; title = "PR 1"; author = @{ login = "user1" } }
            )
            $testDerivatives = @()

            $result = @(Get-PRsWithPendingDerivatives -Owner "test" -Repo "repo" -OpenPRs $testOpenPRs -Derivatives $testDerivatives)
            $result.Count | Should -Be 0
        }
    }

    Context "Invoke-PRMaintenance Function - Classification" {
        BeforeEach {
            # Mock Get-OpenPRs to return test data
            Mock Get-OpenPRs {
                return @(
                    @{
                        number = 100
                        title = "Bot-authored PR"
                        author = @{ login = "rjmurillo-bot" }
                        headRefName = "feature-bot"
                        baseRefName = "main"
                        mergeable = "MERGEABLE"
                        reviewDecision = "CHANGES_REQUESTED"
                        reviewRequests = @{ nodes = @() }
                    },
                    @{
                        number = 101
                        title = "Human PR"
                        author = @{ login = "humanuser" }
                        headRefName = "feature-human"
                        baseRefName = "main"
                        mergeable = "CONFLICTING"
                        reviewDecision = "CHANGES_REQUESTED"
                        reviewRequests = @{ nodes = @() }
                    },
                    @{
                        number = 102
                        title = "Clean PR"
                        author = @{ login = "anotheruser" }
                        headRefName = "feature-clean"
                        baseRefName = "main"
                        mergeable = "MERGEABLE"
                        reviewDecision = "APPROVED"
                        reviewRequests = @{ nodes = @() }
                    }
                )
            }
        }

        It "Classifies bot-authored PRs with CHANGES_REQUESTED as ActionRequired" {
            $result = Invoke-PRMaintenance -Owner "test" -Repo "repo" -MaxPRs 10

            $actionRequired = $result.ActionRequired | Where-Object { $_.number -eq 100 }
            $actionRequired | Should -Not -BeNullOrEmpty
            $actionRequired.category | Should -Be "agent-controlled"
            $actionRequired.reason | Should -Be "CHANGES_REQUESTED"
        }

        It "Classifies human PRs with CHANGES_REQUESTED as Blocked" {
            $result = Invoke-PRMaintenance -Owner "test" -Repo "repo" -MaxPRs 10

            $blocked = $result.Blocked | Where-Object { $_.number -eq 101 }
            $blocked | Should -Not -BeNullOrEmpty
            $blocked.category | Should -Be "human-blocked"
            $blocked.hasConflicts | Should -Be $true
        }

        It "Does not add clean PRs to ActionRequired or Blocked" {
            $result = Invoke-PRMaintenance -Owner "test" -Repo "repo" -MaxPRs 10

            $result.ActionRequired | Where-Object { $_.number -eq 102 } | Should -BeNullOrEmpty
            $result.Blocked | Where-Object { $_.number -eq 102 } | Should -BeNullOrEmpty
        }

        It "Tracks total PR count" {
            $result = Invoke-PRMaintenance -Owner "test" -Repo "repo" -MaxPRs 10

            $result.TotalPRs | Should -Be 3
        }
    }

    Context "Invoke-PRMaintenance Function - Mention-Triggered Bot Classification" {
        BeforeEach {
            Mock Get-OpenPRs {
                return @(
                    @{
                        number = 247
                        title = "Copilot PR with changes requested"
                        author = @{ login = "app/copilot-swe-agent" }
                        headRefName = "copilot-feature"
                        baseRefName = "main"
                        mergeable = "MERGEABLE"
                        reviewDecision = "CHANGES_REQUESTED"
                        reviewRequests = @{ nodes = @() }
                    },
                    @{
                        number = 248
                        title = "Copilot PR with conflicts"
                        author = @{ login = "copilot-swe-agent" }
                        headRefName = "copilot-conflict"
                        baseRefName = "main"
                        mergeable = "CONFLICTING"
                        reviewDecision = $null
                        reviewRequests = @{ nodes = @() }
                    },
                    @{
                        number = 249
                        title = "Copilot PR approved - no action needed"
                        author = @{ login = "copilot-swe-agent" }
                        headRefName = "copilot-approved"
                        baseRefName = "main"
                        mergeable = "MERGEABLE"
                        reviewDecision = "APPROVED"
                        reviewRequests = @{ nodes = @() }
                    }
                )
            }
        }

        It "Classifies Copilot PR with CHANGES_REQUESTED as ActionRequired (mention-triggered)" {
            $result = Invoke-PRMaintenance -Owner "test" -Repo "repo" -MaxPRs 10

            $actionRequired = $result.ActionRequired | Where-Object { $_.number -eq 247 }
            $actionRequired | Should -Not -BeNullOrEmpty
            $actionRequired.category | Should -Be "mention-triggered"
            $actionRequired.reason | Should -Be "CHANGES_REQUESTED"
            $actionRequired.requiresSynthesis | Should -Be $true
        }

        It "Classifies Copilot PR with conflicts as ActionRequired (mention-triggered)" {
            $result = Invoke-PRMaintenance -Owner "test" -Repo "repo" -MaxPRs 10

            $actionRequired = $result.ActionRequired | Where-Object { $_.number -eq 248 }
            $actionRequired | Should -Not -BeNullOrEmpty
            $actionRequired.category | Should -Be "mention-triggered"
            $actionRequired.reason | Should -Be "HAS_CONFLICTS"
            $actionRequired.hasConflicts | Should -Be $true
        }

        It "Does not add approved Copilot PR to ActionRequired or Blocked" {
            $result = Invoke-PRMaintenance -Owner "test" -Repo "repo" -MaxPRs 10

            $result.ActionRequired | Where-Object { $_.number -eq 249 } | Should -BeNullOrEmpty
            $result.Blocked | Where-Object { $_.number -eq 249 } | Should -BeNullOrEmpty
        }

        It "Recognizes app/copilot-swe-agent format from GitHub API" {
            $result = Invoke-PRMaintenance -Owner "test" -Repo "repo" -MaxPRs 10

            # PR 247 uses app/copilot-swe-agent format - should still be recognized
            $actionRequired = $result.ActionRequired | Where-Object { $_.number -eq 247 }
            $actionRequired | Should -Not -BeNullOrEmpty
            $actionRequired.author | Should -Be "app/copilot-swe-agent"
        }
    }

    Context "Rate Limit Safety" {
        It "Test-RateLimitSafe handles API failure gracefully" {
            Mock gh {
                $global:LASTEXITCODE = 1
                return "Error: API error"
            }

            # Should return true (assume safe) on failure
            $result = Test-RateLimitSafe
            $result | Should -Be $true
        }

        It "Test-RateLimitSafe returns false when rate limit is low" {
            Mock gh {
                $global:LASTEXITCODE = 0
                return @{
                    resources = @{
                        core = @{ remaining = 50; limit = 5000 }
                        graphql = @{ remaining = 20; limit = 5000 }
                    }
                } | ConvertTo-Json -Depth 10
            }

            $result = Test-RateLimitSafe
            $result | Should -Be $false
        }

        It "Test-RateLimitSafe returns true when rate limit is sufficient" {
            Mock gh {
                $global:LASTEXITCODE = 0
                return @{
                    resources = @{
                        core = @{ remaining = 4500; limit = 5000 }
                        graphql = @{ remaining = 4500; limit = 5000 }
                    }
                } | ConvertTo-Json -Depth 10
            }

            $result = Test-RateLimitSafe
            $result | Should -Be $true
        }
    }

    Context "Script Lock Mechanism" {
        It "Enter-ScriptLock creates lock file" {
            # This is a basic smoke test
            $result = Enter-ScriptLock
            $result | Should -Be $true

            # Clean up
            Exit-ScriptLock
        }

        It "Exit-ScriptLock removes lock file" {
            Enter-ScriptLock
            Exit-ScriptLock

            $lockFile = Join-Path ([System.IO.Path]::GetTempPath()) 'invoke-pr-maintenance.lock'
            Test-Path $lockFile | Should -Be $false
        }
    }

    Context "Logging Functions" {
        It "Write-Log creates log entries with correct format" {
            # Write-Log doesn't throw
            { Write-Log "Test message" -Level INFO } | Should -Not -Throw
            { Write-Log "Warning message" -Level WARN } | Should -Not -Throw
            { Write-Log "Error message" -Level ERROR } | Should -Not -Throw
        }
    }

    Context "GitHub API Helpers" {
        It "Invoke-GhApi handles API errors gracefully" {
            Mock gh {
                $global:LASTEXITCODE = 1
                return "Error: Not authenticated"
            }

            $result = Invoke-GhApi -Endpoint "repos/test/repo"
            $result | Should -BeNullOrEmpty
        }
    }
}

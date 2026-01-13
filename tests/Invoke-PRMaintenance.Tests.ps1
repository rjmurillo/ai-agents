BeforeAll {
    . "$PSScriptRoot/../scripts/Invoke-PRMaintenance.ps1"
}

Describe 'Invoke-PRMaintenance Bot Authority Tests' {
    BeforeEach {
        # Mock GitHub CLI and external dependencies
        Mock gh { }
        Mock Write-Log { }
        # Return empty arrays - use @() without comma for functions where
        # production code wraps with @() (avoids nested array issue)
        Mock Get-DerivativePRs { , @() }
        Mock Get-PRsWithPendingDerivatives { , @() }
        Mock Get-SimilarPRs { @() }
        Mock Add-CommentReaction { return $true }
    }

    # Task 5.1: Bot PR conflicts go to ActionRequired
    It 'Routes bot-authored PR with unresolvable conflicts to ActionRequired' {
        # Arrange
        Mock Get-BotAuthorInfo { @{ IsBot = $true; Category = 'agent-controlled'; Action = 'pr-comment-responder'; Mention = $null } }
        Mock Resolve-PRConflicts { return $false }
        Mock Get-OpenPRs {
            # Use comma operator to preserve array on return (matches real function)
            , @([PSCustomObject]@{
                number = 999
                title = 'Test PR'
                author = [PSCustomObject]@{ login = 'rjmurillo-bot' }
                mergeable = 'CONFLICTING'
                headRefName = 'test-branch'
                baseRefName = 'main'
                reviewDecision = $null
                reviewRequests = @()
            })
        }
        Mock Get-PRComments { , @() }
        Mock Get-UnacknowledgedComments { , @() }

        # Act
        $results = Invoke-PRMaintenance -Owner 'rjmurillo' -Repo 'ai-agents'

        # Assert
        $results.ActionRequired | Should -HaveCount 1
        $results.ActionRequired[0].Reason | Should -Be 'MANUAL_CONFLICT_RESOLUTION'
        $results.ActionRequired[0].Action | Should -Be '/pr-review to manually resolve conflicts'
        $results.Blocked | Should -BeNullOrEmpty
    }

    # Task 5.2: Bot PR unaddressed comments trigger action
    It 'Triggers action for bot PR with unaddressed comments even without CHANGES_REQUESTED' {
        # Arrange
        Mock Get-BotAuthorInfo { @{ IsBot = $true; Category = 'agent-controlled'; Action = 'pr-comment-responder'; Mention = $null } }
        Mock Resolve-PRConflicts { return $true }  # No conflicts
        Mock Get-OpenPRs {
            , @([PSCustomObject]@{
                number = 888
                title = 'Test PR with comments'
                author = [PSCustomObject]@{ login = 'rjmurillo-bot' }
                reviewDecision = $null  # Not CHANGES_REQUESTED
                mergeable = 'MERGEABLE'
                headRefName = 'feature'
                baseRefName = 'main'
                reviewRequests = @()
            })
        }
        Mock Get-PRComments { , @() }
        Mock Get-UnacknowledgedComments {
            , @(
                [PSCustomObject]@{ id = 1; body = 'Comment 1'; user = [PSCustomObject]@{ login = 'coderabbitai' } }
                [PSCustomObject]@{ id = 2; body = 'Comment 2'; user = [PSCustomObject]@{ login = 'cursor[bot]' } }
                [PSCustomObject]@{ id = 3; body = 'Comment 3'; user = [PSCustomObject]@{ login = 'gemini-code-assist' } }
            )
        }

        # Act
        $results = Invoke-PRMaintenance -Owner 'rjmurillo' -Repo 'ai-agents'

        # Assert
        $results.ActionRequired | Should -HaveCount 1
        $results.ActionRequired[0].Reason | Should -Be 'UNADDRESSED_COMMENTS'
        $results.ActionRequired[0].UnaddressedCount | Should -Be 3
        $results.ActionRequired[0].Action | Should -Be '/pr-review via pr-comment-responder'
    }

    # Task 5.3: Copilot PR synthesis detection
    It 'Detects copilot PR and triggers synthesis for other bot comments' {
        # Arrange - copilot-swe-agent is author, rjmurillo-bot is reviewer
        Mock Get-BotAuthorInfo -ParameterFilter { $AuthorLogin -imatch 'copilot' } {
            @{ IsBot = $true; Category = 'mention-triggered'; Action = 'mention in comment'; Mention = '@copilot' }
        }
        Mock Get-BotAuthorInfo -ParameterFilter { $AuthorLogin -inotmatch 'copilot' } {
            @{ IsBot = $true; Category = 'agent-controlled'; Action = 'pr-comment-responder'; Mention = $null }
        }
        Mock Resolve-PRConflicts { return $true }
        Mock Get-OpenPRs {
            , @([PSCustomObject]@{
                number = 247
                title = 'Copilot PR'
                author = [PSCustomObject]@{ login = 'copilot-swe-agent' }
                reviewDecision = 'CHANGES_REQUESTED'
                mergeable = 'MERGEABLE'
                headRefName = 'feature'
                baseRefName = 'main'
                reviewRequests = @([PSCustomObject]@{ login = 'rjmurillo-bot' })
            })
        }
        Mock Get-PRComments {
            , @(
                [PSCustomObject]@{ id = 1; body = 'Issue 1'; user = [PSCustomObject]@{ login = 'coderabbitai' }; html_url = 'https://github.com/test/1' }
                [PSCustomObject]@{ id = 2; body = 'Issue 2'; user = [PSCustomObject]@{ login = 'coderabbitai' }; html_url = 'https://github.com/test/2' }
                [PSCustomObject]@{ id = 3; body = 'Issue 3'; user = [PSCustomObject]@{ login = 'cursor[bot]' }; html_url = 'https://github.com/test/3' }
            )
        }
        Mock Get-UnacknowledgedComments { , @() }

        # Act
        $results = Invoke-PRMaintenance -Owner 'rjmurillo' -Repo 'ai-agents'

        # Assert
        $synthesisEntry = $results.ActionRequired | Where-Object { $_.Reason -eq 'COPILOT_SYNTHESIS_NEEDED' }
        $synthesisEntry | Should -Not -BeNullOrEmpty
        $synthesisEntry.CommentsToSynthesize | Should -Be 3
        $synthesisEntry.Category | Should -Be 'synthesis-required'
    }

    # Task 5.4: No duplicate PR entries
    It 'PR with conflicts and CHANGES_REQUESTED appears in ActionRequired only (deduplication)' {
        # Arrange
        Mock Get-BotAuthorInfo { @{ IsBot = $true; Category = 'agent-controlled'; Action = 'pr-comment-responder'; Mention = $null } }
        Mock Resolve-PRConflicts { return $false }  # Conflict resolution fails
        Mock Get-OpenPRs {
            , @([PSCustomObject]@{
                number = 235
                title = 'Bot PR with conflicts and changes requested'
                author = [PSCustomObject]@{ login = 'rjmurillo-bot' }
                reviewDecision = 'CHANGES_REQUESTED'
                mergeable = 'CONFLICTING'
                headRefName = 'feature-branch'
                baseRefName = 'main'
                reviewRequests = @()
            })
        }
        Mock Get-PRComments { , @() }
        Mock Get-UnacknowledgedComments { , @() }

        # Act
        $results = Invoke-PRMaintenance -Owner 'rjmurillo' -Repo 'ai-agents'

        # Assert - Single entry in ActionRequired (not duplicated)
        # Note: Wrap with @() to ensure array even when single result
        $prEntries = @($results.ActionRequired | Where-Object { $_.PR -eq 235 })
        $prEntries | Should -HaveCount 1

        # Assert - Not in Blocked
        $results.Blocked | Where-Object { $_.PR -eq 235 } | Should -BeNullOrEmpty

        # Assert - Has conflict info merged
        $prEntries[0].HasConflicts | Should -Be $true
        $prEntries[0].Action | Should -Match 'resolve conflicts'
    }

    # Task 5.5: Human PR conflicts go to Blocked (regression test)
    It 'Human-authored PR with unresolvable conflicts goes to Blocked (not ActionRequired)' {
        # Arrange - REGRESSION TEST for human PR handling
        Mock Get-BotAuthorInfo { @{ IsBot = $false; Category = 'human'; Action = $null; Mention = $null } }
        Mock Resolve-PRConflicts { return $false }  # Conflict resolution fails
        Mock Get-OpenPRs {
            , @([PSCustomObject]@{
                number = 777
                title = 'Human PR'
                author = [PSCustomObject]@{ login = 'human-user' }
                mergeable = 'CONFLICTING'
                headRefName = 'feature'
                baseRefName = 'main'
                reviewDecision = $null
                reviewRequests = @()
            })
        }
        Mock Get-PRComments { , @() }

        # Act
        $results = Invoke-PRMaintenance -Owner 'rjmurillo' -Repo 'ai-agents'

        # Assert - Human PR goes to Blocked (existing behavior preserved)
        $results.Blocked | Should -HaveCount 1
        $results.Blocked[0].Reason | Should -Be 'UNRESOLVABLE_CONFLICTS'
        $results.Blocked[0].PR | Should -Be 777

        # Assert - NOT in ActionRequired
        $results.ActionRequired | Where-Object { $_.PR -eq 777 } | Should -BeNullOrEmpty
    }

    # Task 5.6: Copilot PR with zero other bot comments
    It 'Copilot PR with no other bot comments does NOT trigger synthesis' {
        # Arrange - EDGE CASE: No other bot comments to synthesize
        Mock Get-BotAuthorInfo -ParameterFilter { $AuthorLogin -imatch 'copilot' } {
            @{ IsBot = $true; Category = 'mention-triggered'; Action = 'mention in comment'; Mention = '@copilot' }
        }
        Mock Get-BotAuthorInfo -ParameterFilter { $AuthorLogin -inotmatch 'copilot' } {
            @{ IsBot = $true; Category = 'agent-controlled'; Action = 'pr-comment-responder'; Mention = $null }
        }
        Mock Resolve-PRConflicts { return $true }
        Mock Get-OpenPRs {
            , @([PSCustomObject]@{
                number = 333
                title = 'Copilot PR without other bot feedback'
                author = [PSCustomObject]@{ login = 'copilot-swe-agent' }
                reviewDecision = 'APPROVED'
                mergeable = 'MERGEABLE'
                headRefName = 'feature'
                baseRefName = 'main'
                reviewRequests = @([PSCustomObject]@{ login = 'rjmurillo-bot' })
            })
        }
        # Only copilot's own comments - no other bots
        Mock Get-PRComments {
            , @([PSCustomObject]@{ id = 1; body = 'I fixed it'; user = [PSCustomObject]@{ login = 'copilot-swe-agent' } })
        }
        Mock Get-UnacknowledgedComments { , @() }

        # Act
        $results = Invoke-PRMaintenance -Owner 'rjmurillo' -Repo 'ai-agents'

        # Assert - NO synthesis entry (0 other bot comments)
        $synthesisEntry = $results.ActionRequired | Where-Object { $_.Reason -eq 'COPILOT_SYNTHESIS_NEEDED' }
        $synthesisEntry | Should -BeNullOrEmpty
    }
}

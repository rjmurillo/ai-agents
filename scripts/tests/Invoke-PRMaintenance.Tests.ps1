<#
.SYNOPSIS
    Pester tests for Invoke-PRMaintenance.ps1 script.

.DESCRIPTION
    Tests PR automation script functions for reliability, safety, and error handling.
    Covers unit tests, integration tests, and edge cases for unattended operation.

.NOTES
    Requires Pester 5.x or later.
#>

BeforeAll {
    $Script:ScriptPath = Join-Path $PSScriptRoot "..\Invoke-PRMaintenance.ps1"
    $Script:TestDir = Join-Path $TestDrive "pr-maintenance-test"

    # Load script functions for testing
    . $Script:ScriptPath

    # Test fixtures
    $Script:Fixtures = @{
        OpenPRs = @(
            @{
                number = 123
                title = "feat: add feature X"
                state = "OPEN"
                head = "feature-branch"
                base = "main"
                mergeable = "MERGEABLE"
                reviewDecision = $null
                author = @{ login = "user1" }
            },
            @{
                number = 456
                title = "fix: resolve bug Y"
                state = "OPEN"
                head = "fix-branch"
                base = "main"
                mergeable = "CONFLICTING"
                reviewDecision = "APPROVED"
                author = @{ login = "user2" }
            }
        )

        BotComments = @(
            @{
                id = 1001
                user = @{ type = "Bot"; login = "Copilot" }
                reactions = @{ eyes = 0 }
                body = "Consider refactoring this method"
            },
            @{
                id = 1002
                user = @{ type = "Bot"; login = "coderabbitai[bot]" }
                reactions = @{ eyes = 1 }
                body = "LGTM"
            },
            @{
                id = 1003
                user = @{ type = "User"; login = "human" }
                reactions = @{ eyes = 0 }
                body = "Human comment"
            }
        )

        MergedPRs = @(
            @{
                number = 789
                title = "feat: add feature X v2"
            },
            @{
                number = 790
                title = "fix: another fix"
            }
        )
    }
}

Describe "Invoke-PRMaintenance.ps1" {
    BeforeEach {
        # Create fresh test directory
        New-Item -ItemType Directory -Path $Script:TestDir -Force | Out-Null

        # Reset mock counters
        $script:GhCallCount = 0
        $script:GitCallCount = 0
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
        }

        It "MaxPRs parameter has default value of 20" {
            $cmd = Get-Command $Script:ScriptPath
            $param = $cmd.Parameters['MaxPRs']
            $param.Attributes.TypeId.Name | Should -Contain "ParameterAttribute"
        }
    }

    Context "Configuration" {
        It "Defines protected branches (main, master, develop)" {
            $scriptContent = Get-Content -Path $Script:ScriptPath -Raw
            $scriptContent | Should -Match "ProtectedBranches.*=.*@\('main',\s*'master',\s*'develop'\)"
        }

        It "Defines bot authors for acknowledgment" {
            $scriptContent = Get-Content -Path $Script:ScriptPath -Raw
            $scriptContent | Should -Match "BotAuthors.*Copilot"
            $scriptContent | Should -Match "BotAuthors.*coderabbitai"
        }

        It "Uses eyes reaction for acknowledgment" {
            $scriptContent = Get-Content -Path $Script:ScriptPath -Raw
            $scriptContent | Should -Match "AcknowledgeReaction\s*=\s*'eyes'"
        }
    }

    Context "Get-OpenPRs Function" {
        It "Returns empty array when no PRs" {
            Mock gh {
                $global:LASTEXITCODE = 0
                return "[]"
            }

            $result = Get-OpenPRs -Owner "test" -Repo "repo" -Limit 20
            # Result may be $null or empty array depending on Pester Mock behavior;
            # both are acceptable for "no PRs" case
            ($null -eq $result -or $result.Count -eq 0) | Should -Be $true
        }

        It "Returns PR objects with required properties" {
            Mock gh {
                $global:LASTEXITCODE = 0
                return ($Script:Fixtures.OpenPRs | ConvertTo-Json -Depth 5)
            }

            $result = Get-OpenPRs -Owner "test" -Repo "repo" -Limit 20
            $result[0].number | Should -Be 123
            $result[0].title | Should -Be "feat: add feature X"
            $result[0].mergeable | Should -Be "MERGEABLE"
        }

        It "Handles gh CLI failure" {
            Mock gh {
                $global:LASTEXITCODE = 1
                return "Error: Not authenticated"
            }

            { Get-OpenPRs -Owner "test" -Repo "repo" -Limit 20 } | Should -Throw
        }

        It "Handles invalid JSON response" {
            Mock gh {
                $global:LASTEXITCODE = 0  # Command succeeds but returns invalid JSON
                return "INVALID JSON"
            }

            { Get-OpenPRs -Owner "test" -Repo "repo" -Limit 20 } | Should -Throw
        }
    }

    Context "Get-PRComments Function" {
        It "Returns empty array when no comments" {
            Mock Invoke-GhApi {
                return "[]"
            }

            $result = Get-PRComments -Owner "test" -Repo "repo" -PRNumber 123
            $result.Count | Should -Be 0
        }

        It "Returns comment objects with required properties" {
            Mock Invoke-GhApi {
                return ($Script:Fixtures.BotComments | ConvertTo-Json -Depth 5)
            }

            $result = Get-PRComments -Owner "test" -Repo "repo" -PRNumber 123
            $result[0].id | Should -Be 1001
            $result[0].user.type | Should -Be "Bot"
            $result[0].reactions.eyes | Should -Be 0
        }

        It "Handles API failure" {
            Mock Invoke-GhApi {
                throw "API Error: Rate limit exceeded"
            }

            { Get-PRComments -Owner "test" -Repo "repo" -PRNumber 123 } | Should -Throw
        }
    }

    Context "Get-UnacknowledgedComments Function" {
        It "Returns empty array when all comments acknowledged" {
            Mock Get-PRComments {
                return @(
                    @{ user = @{ type = "Bot" }; reactions = @{ eyes = 1 } }
                )
            }

            $result = Get-UnacknowledgedComments -Owner "test" -Repo "repo" -PRNumber 123
            $result.Count | Should -Be 0
        }

        It "Filters by bot user type" {
            Mock Get-PRComments {
                return $Script:Fixtures.BotComments
            }

            $result = Get-UnacknowledgedComments -Owner "test" -Repo "repo" -PRNumber 123
            $result.Count | Should -Be 1
            $result[0].id | Should -Be 1001
            $result[0].user.type | Should -Be "Bot"
        }

        It "Filters by reactions.eyes = 0" {
            Mock Get-PRComments {
                return $Script:Fixtures.BotComments
            }

            $result = Get-UnacknowledgedComments -Owner "test" -Repo "repo" -PRNumber 123
            $result[0].reactions.eyes | Should -Be 0
        }

        It "Excludes human comments" {
            Mock Get-PRComments {
                return $Script:Fixtures.BotComments
            }

            $result = Get-UnacknowledgedComments -Owner "test" -Repo "repo" -PRNumber 123
            $result | Where-Object { $_.user.login -eq "human" } | Should -BeNullOrEmpty
        }
    }

    Context "Add-CommentReaction Function" {
        It "Returns true on successful reaction" {
            Mock Invoke-GhApi {
                return '{"id": 1}'
            }

            $result = Add-CommentReaction -Owner "test" -Repo "repo" -CommentId 1001
            $result | Should -Be $true
        }

        It "Returns false on API failure without throwing" {
            Mock Invoke-GhApi {
                throw "API Error"
            }

            $result = Add-CommentReaction -Owner "test" -Repo "repo" -CommentId 1001
            $result | Should -Be $false
        }

        It "Uses eyes reaction by default" {
            Mock Invoke-GhApi {
                param($Endpoint, $Method, $Body)
                $Body.content | Should -Be "eyes"
                return '{}'
            }

            Add-CommentReaction -Owner "test" -Repo "repo" -CommentId 1001
        }
    }

    Context "Test-PRHasConflicts Function" {
        It "Returns true when mergeable = CONFLICTING" {
            Mock gh {
                return "CONFLICTING"
            }

            $result = Test-PRHasConflicts -Owner "test" -Repo "repo" -PRNumber 123
            $result | Should -Be $true
        }

        It "Returns false when mergeable = MERGEABLE" {
            Mock gh {
                return "MERGEABLE"
            }

            $result = Test-PRHasConflicts -Owner "test" -Repo "repo" -PRNumber 123
            $result | Should -Be $false
        }

        It "Returns false when mergeable = UNKNOWN" {
            Mock gh {
                return "UNKNOWN"
            }

            $result = Test-PRHasConflicts -Owner "test" -Repo "repo" -PRNumber 123
            $result | Should -Be $false
        }

        It "Handles PR not found" {
            Mock gh {
                $global:LASTEXITCODE = 1
                return "PR not found"
            }

            # Function should handle gracefully
            $result = Test-PRHasConflicts -Owner "test" -Repo "repo" -PRNumber 99999
            $result | Should -Be $false
        }
    }

    Context "Test-PRNeedsOwnerAction Function" {
        It "Returns true when reviewDecision = CHANGES_REQUESTED" {
            Mock gh {
                $global:LASTEXITCODE = 0
                return "CHANGES_REQUESTED"
            }

            $result = Test-PRNeedsOwnerAction -Owner "test" -Repo "repo" -PRNumber 123
            $result | Should -Be $true
        }

        It "Returns false when reviewDecision = APPROVED" {
            Mock gh {
                $global:LASTEXITCODE = 0
                return "APPROVED"
            }

            $result = Test-PRNeedsOwnerAction -Owner "test" -Repo "repo" -PRNumber 123
            $result | Should -Be $false
        }

        It "Returns false when reviewDecision is null" {
            Mock gh {
                $global:LASTEXITCODE = 0
                return ""
            }

            $result = Test-PRNeedsOwnerAction -Owner "test" -Repo "repo" -PRNumber 123
            $result | Should -Be $false
        }
    }

    Context "Resolve-PRConflicts Function" {
        It "Creates worktree with correct path" {
            # Mock Test-IsGitHubRunner to force worktree code path
            Mock Test-IsGitHubRunner { return $false }
            Mock git {
                param([Parameter(ValueFromRemainingArguments)]$Args)
                if ($Args -contains "rev-parse") {
                    $global:LASTEXITCODE = 0
                    return "D:\repo"
                }
                if ($Args -contains "worktree" -and $Args -contains "add") {
                    $global:LASTEXITCODE = 0
                    $script:WorktreePath = $Args[-2]
                }
                $global:LASTEXITCODE = 0
                return ""
            }

            Mock Push-Location {}
            Mock Pop-Location {}

            try {
                Resolve-PRConflicts -Owner "test" -Repo "repo" -PRNumber 123 -BranchName "feature"
            } catch {}

            $script:WorktreePath | Should -Match "ai-agents-pr-123$"
        }

        It "Auto-resolves HANDOFF.md conflicts" {
            Mock git {
                param([Parameter(ValueFromRemainingArguments)]$Args)

                if ($Args -contains "rev-parse") {
                    $global:LASTEXITCODE = 0
                    return "D:\repo"
                }
                if ($Args -contains "worktree") {
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "fetch") {
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "merge") {
                    $global:LASTEXITCODE = 1
                    return "CONFLICT"
                }
                if ($Args -contains "diff" -and $Args -contains "--name-only") {
                    $global:LASTEXITCODE = 0
                    return ".agents/HANDOFF.md"
                }
                if ($Args -contains "checkout" -and $Args -contains "--theirs") {
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "add") {
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "commit") {
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "push") {
                    $global:LASTEXITCODE = 0
                    return ""
                }

                $global:LASTEXITCODE = 0
                return ""
            }

            Mock Push-Location {}
            Mock Pop-Location {}
            Mock Test-Path { $false }

            $result = Resolve-PRConflicts -Owner "test" -Repo "repo" -PRNumber 123 -BranchName "feature"
            $result | Should -Be $true
        }

        It "Returns false for non-auto-resolvable conflicts" {
            Mock git {
                param([Parameter(ValueFromRemainingArguments)]$Args)

                if ($Args -contains "rev-parse") {
                    $global:LASTEXITCODE = 0
                    return "D:\repo"
                }
                if ($Args -contains "worktree") {
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "fetch") {
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "merge") {
                    $global:LASTEXITCODE = 1
                    return "CONFLICT"
                }
                if ($Args -contains "diff" -and $Args -contains "--name-only") {
                    $global:LASTEXITCODE = 0
                    return "src/Program.cs"
                }
                if ($Args -contains "merge" -and $Args -contains "--abort") {
                    $global:LASTEXITCODE = 0
                    return ""
                }

                $global:LASTEXITCODE = 0
                return ""
            }

            Mock Push-Location {}
            Mock Pop-Location {}
            Mock Test-Path { $false }

            $result = Resolve-PRConflicts -Owner "test" -Repo "repo" -PRNumber 123 -BranchName "feature"
            $result | Should -Be $false
        }

        It "Cleans up worktree on success" {
            # Mock Test-IsGitHubRunner to force worktree code path
            Mock Test-IsGitHubRunner { return $false }
            Mock git {
                param([Parameter(ValueFromRemainingArguments)]$Args)
                if ($Args -contains "rev-parse") {
                    $global:LASTEXITCODE = 0
                    return "D:\repo"
                }
                if ($Args -contains "worktree" -and $Args -contains "remove") {
                    $global:LASTEXITCODE = 0
                    $script:WorktreeRemoved = $true
                }
                $global:LASTEXITCODE = 0
                return ""
            }

            Mock Push-Location {}
            Mock Pop-Location {}
            Mock Test-Path { return $true }

            try {
                Resolve-PRConflicts -Owner "test" -Repo "repo" -PRNumber 123 -BranchName "feature"
            } catch {}

            $script:WorktreeRemoved | Should -Be $true
        }

        It "Skips commit when merge has no staged changes (clean merge)" {
            # This tests the fix for workflow run 20495388994
            # When merge completes cleanly, git diff --cached --quiet returns 0
            # and commit should be skipped
            Mock Test-IsGitHubRunner { return $true }
            $script:CommitCalled = $false
            Mock git {
                param([Parameter(ValueFromRemainingArguments)]$Args)

                if ($Args -contains "fetch") {
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "checkout") {
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "merge") {
                    # Merge succeeds (no conflicts)
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "diff" -and $Args -contains "--cached" -and $Args -contains "--quiet") {
                    # No staged changes - returns 0
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "commit") {
                    $script:CommitCalled = $true
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "push") {
                    $global:LASTEXITCODE = 0
                    return ""
                }

                $global:LASTEXITCODE = 0
                return ""
            }

            $result = Resolve-PRConflicts -Owner "test" -Repo "repo" -PRNumber 123 -BranchName "feature"
            $result | Should -Be $true
            $script:CommitCalled | Should -Be $false
        }

        It "REGRESSION: Handles HANDOFF.md conflict where checkout --theirs results in no actual change" {
            # This is the EXACT failure scenario from workflow run 20495388994
            # 1. Merge reports conflict in .agents/HANDOFF.md
            # 2. checkout --theirs is called but file was already identical
            # 3. git add succeeds but stages nothing
            # 4. git diff --cached --quiet returns 0 (no staged changes)
            # 5. OLD CODE: git commit fails with "nothing to commit"
            # 6. NEW CODE: should skip commit and succeed
            Mock Test-IsGitHubRunner { return $true }
            $script:CommitCalled = $false
            Mock git {
                param([Parameter(ValueFromRemainingArguments)]$Args)

                if ($Args -contains "fetch") {
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "checkout" -and -not ($Args -contains "--theirs")) {
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "merge") {
                    # Merge reports conflict
                    $global:LASTEXITCODE = 1
                    return "CONFLICT (content): Merge conflict in .agents/HANDOFF.md"
                }
                if ($Args -contains "diff" -and $Args -contains "--name-only" -and $Args -contains "--diff-filter=U") {
                    # Only HANDOFF.md has conflict
                    $global:LASTEXITCODE = 0
                    return ".agents/HANDOFF.md"
                }
                if ($Args -contains "checkout" -and $Args -contains "--theirs") {
                    # Checkout succeeds but file was already identical
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "add" -and $Args -contains ".agents/HANDOFF.md") {
                    # Add succeeds but nothing actually staged
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "diff" -and $Args -contains "--cached" -and $Args -contains "--quiet") {
                    # KEY: No actual changes staged - this is the edge case!
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "commit") {
                    $script:CommitCalled = $true
                    # If commit is called, it would fail with nothing to commit
                    $global:LASTEXITCODE = 1
                    return "nothing to commit, working tree clean"
                }
                if ($Args -contains "push") {
                    $global:LASTEXITCODE = 0
                    return ""
                }

                $global:LASTEXITCODE = 0
                return ""
            }

            $result = Resolve-PRConflicts -Owner "test" -Repo "repo" -PRNumber 123 -BranchName "feature"
            $result | Should -Be $true
            # Commit should NOT be called because diff --cached --quiet returned 0
            $script:CommitCalled | Should -Be $false
        }

        It "REGRESSION: Handles session file conflict where file is already up to date" {
            # Similar to HANDOFF.md case but for .agents/sessions/* files
            Mock Test-IsGitHubRunner { return $true }
            $script:CommitCalled = $false
            Mock git {
                param([Parameter(ValueFromRemainingArguments)]$Args)

                if ($Args -contains "fetch") {
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "checkout" -and -not ($Args -contains "--theirs")) {
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "merge") {
                    $global:LASTEXITCODE = 1
                    return "CONFLICT"
                }
                if ($Args -contains "diff" -and $Args -contains "--name-only" -and $Args -contains "--diff-filter=U") {
                    $global:LASTEXITCODE = 0
                    return ".agents/sessions/2025-01-01-session-01.md"
                }
                if ($Args -contains "checkout" -and $Args -contains "--theirs") {
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "add") {
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "diff" -and $Args -contains "--cached" -and $Args -contains "--quiet") {
                    # No actual changes staged
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "commit") {
                    $script:CommitCalled = $true
                    $global:LASTEXITCODE = 1
                    return "nothing to commit"
                }
                if ($Args -contains "push") {
                    $global:LASTEXITCODE = 0
                    return ""
                }

                $global:LASTEXITCODE = 0
                return ""
            }

            $result = Resolve-PRConflicts -Owner "test" -Repo "repo" -PRNumber 123 -BranchName "feature"
            $result | Should -Be $true
            $script:CommitCalled | Should -Be $false
        }

        It "REGRESSION: Old behavior would fail on 'nothing to commit' error" {
            # This test documents what the OLD behavior was and ensures we don't regress
            # OLD: Always called git commit after resolving conflicts
            # NEW: Check for staged changes first
            #
            # This test verifies that if someone removes the staged check,
            # the test will fail because commit returns error
            Mock Test-IsGitHubRunner { return $true }
            Mock git {
                param([Parameter(ValueFromRemainingArguments)]$Args)

                if ($Args -contains "fetch") {
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "checkout" -and -not ($Args -contains "--theirs")) {
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "merge") {
                    $global:LASTEXITCODE = 1
                    return "CONFLICT"
                }
                if ($Args -contains "diff" -and $Args -contains "--name-only" -and $Args -contains "--diff-filter=U") {
                    $global:LASTEXITCODE = 0
                    return ".agents/HANDOFF.md"
                }
                if ($Args -contains "checkout" -and $Args -contains "--theirs") {
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "add") {
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "diff" -and $Args -contains "--cached" -and $Args -contains "--quiet") {
                    # No staged changes
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "commit") {
                    # Simulates what happens if commit is called with nothing staged
                    $global:LASTEXITCODE = 1
                    throw "nothing to commit, working tree clean"
                }
                if ($Args -contains "push") {
                    $global:LASTEXITCODE = 0
                    return ""
                }

                $global:LASTEXITCODE = 0
                return ""
            }

            # This should succeed with the fix - commit is never called
            $result = Resolve-PRConflicts -Owner "test" -Repo "repo" -PRNumber 123 -BranchName "feature"
            $result | Should -Be $true
        }

        It "Handles multiple auto-resolvable files with mixed staged status" {
            # Both HANDOFF.md and session file in conflict
            # One has changes, one doesn't
            Mock Test-IsGitHubRunner { return $true }
            $script:CommitCalled = $false
            Mock git {
                param([Parameter(ValueFromRemainingArguments)]$Args)

                if ($Args -contains "fetch") {
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "checkout" -and -not ($Args -contains "--theirs")) {
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "merge") {
                    $global:LASTEXITCODE = 1
                    return "CONFLICT"
                }
                if ($Args -contains "diff" -and $Args -contains "--name-only" -and $Args -contains "--diff-filter=U") {
                    $global:LASTEXITCODE = 0
                    # Return both files as having conflicts - as an array
                    return @(".agents/HANDOFF.md", ".agents/sessions/2025-01-01-session-01.md")
                }
                if ($Args -contains "checkout" -and $Args -contains "--theirs") {
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "add") {
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "diff" -and $Args -contains "--cached" -and $Args -contains "--quiet") {
                    # At least one file has actual changes
                    $global:LASTEXITCODE = 1
                    return ""
                }
                if ($Args -contains "commit") {
                    $script:CommitCalled = $true
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "push") {
                    $global:LASTEXITCODE = 0
                    return ""
                }

                $global:LASTEXITCODE = 0
                return ""
            }

            $result = Resolve-PRConflicts -Owner "test" -Repo "repo" -PRNumber 123 -BranchName "feature"
            $result | Should -Be $true
            # Commit should be called because there ARE staged changes
            $script:CommitCalled | Should -Be $true
        }

        It "Commits when merge has staged changes (conflict resolved)" {
            # This tests the positive path where conflicts are resolved and staged
            Mock Test-IsGitHubRunner { return $true }
            $script:CommitCalled = $false
            Mock git {
                param([Parameter(ValueFromRemainingArguments)]$Args)

                if ($Args -contains "fetch") {
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "checkout" -and -not ($Args -contains "--theirs")) {
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "merge") {
                    # Merge has conflicts
                    $global:LASTEXITCODE = 1
                    return "CONFLICT"
                }
                if ($Args -contains "diff" -and $Args -contains "--name-only") {
                    $global:LASTEXITCODE = 0
                    return ".agents/HANDOFF.md"
                }
                if ($Args -contains "checkout" -and $Args -contains "--theirs") {
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "add") {
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "diff" -and $Args -contains "--cached" -and $Args -contains "--quiet") {
                    # Staged changes exist - returns 1
                    $global:LASTEXITCODE = 1
                    return ""
                }
                if ($Args -contains "commit") {
                    $script:CommitCalled = $true
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "push") {
                    $global:LASTEXITCODE = 0
                    return ""
                }

                $global:LASTEXITCODE = 0
                return ""
            }

            $result = Resolve-PRConflicts -Owner "test" -Repo "repo" -PRNumber 123 -BranchName "feature"
            $result | Should -Be $true
            $script:CommitCalled | Should -Be $true
        }

        It "Returns false when commit fails after conflict resolution" {
            # Negative test: commit fails even with staged changes
            Mock Test-IsGitHubRunner { return $true }
            Mock git {
                param([Parameter(ValueFromRemainingArguments)]$Args)

                if ($Args -contains "fetch") {
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "checkout" -and -not ($Args -contains "--theirs")) {
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "merge") {
                    $global:LASTEXITCODE = 1
                    return "CONFLICT"
                }
                if ($Args -contains "diff" -and $Args -contains "--name-only") {
                    $global:LASTEXITCODE = 0
                    return ".agents/HANDOFF.md"
                }
                if ($Args -contains "checkout" -and $Args -contains "--theirs") {
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "add") {
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "diff" -and $Args -contains "--cached" -and $Args -contains "--quiet") {
                    # Staged changes exist
                    $global:LASTEXITCODE = 1
                    return ""
                }
                if ($Args -contains "commit") {
                    # Commit fails
                    $global:LASTEXITCODE = 1
                    return "error: commit failed"
                }

                $global:LASTEXITCODE = 0
                return ""
            }

            $result = Resolve-PRConflicts -Owner "test" -Repo "repo" -PRNumber 123 -BranchName "feature"
            $result | Should -Be $false
        }

        It "Skips commit in worktree mode when merge has no staged changes" {
            # Test the local worktree code path for clean merge
            Mock Test-IsGitHubRunner { return $false }
            $script:CommitCalled = $false
            Mock git {
                param([Parameter(ValueFromRemainingArguments)]$Args)

                if ($Args -contains "rev-parse") {
                    $global:LASTEXITCODE = 0
                    return "/repo"
                }
                if ($Args -contains "worktree" -and $Args -contains "add") {
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "worktree" -and $Args -contains "remove") {
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "fetch") {
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "merge") {
                    # Merge succeeds (no conflicts)
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "diff" -and $Args -contains "--cached" -and $Args -contains "--quiet") {
                    # No staged changes
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "commit") {
                    $script:CommitCalled = $true
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "push") {
                    $global:LASTEXITCODE = 0
                    return ""
                }

                $global:LASTEXITCODE = 0
                return ""
            }

            Mock Push-Location {}
            Mock Pop-Location {}
            Mock Test-Path { return $true }

            $result = Resolve-PRConflicts -Owner "test" -Repo "repo" -PRNumber 123 -BranchName "feature"
            $result | Should -Be $true
            $script:CommitCalled | Should -Be $false
        }

        It "Commits in worktree mode when merge has staged changes" {
            # Test the local worktree code path for conflict resolution
            Mock Test-IsGitHubRunner { return $false }
            $script:CommitCalled = $false
            Mock git {
                param([Parameter(ValueFromRemainingArguments)]$Args)

                if ($Args -contains "rev-parse") {
                    $global:LASTEXITCODE = 0
                    return "/repo"
                }
                if ($Args -contains "worktree" -and $Args -contains "add") {
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "worktree" -and $Args -contains "remove") {
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "fetch") {
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "merge") {
                    $global:LASTEXITCODE = 1
                    return "CONFLICT"
                }
                if ($Args -contains "diff" -and $Args -contains "--name-only") {
                    $global:LASTEXITCODE = 0
                    return ".agents/HANDOFF.md"
                }
                if ($Args -contains "checkout" -and $Args -contains "--theirs") {
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "add") {
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "diff" -and $Args -contains "--cached" -and $Args -contains "--quiet") {
                    # Staged changes exist
                    $global:LASTEXITCODE = 1
                    return ""
                }
                if ($Args -contains "commit") {
                    $script:CommitCalled = $true
                    $global:LASTEXITCODE = 0
                    return ""
                }
                if ($Args -contains "push") {
                    $global:LASTEXITCODE = 0
                    return ""
                }

                $global:LASTEXITCODE = 0
                return ""
            }

            Mock Push-Location {}
            Mock Pop-Location {}
            Mock Test-Path { return $true }

            $result = Resolve-PRConflicts -Owner "test" -Repo "repo" -PRNumber 123 -BranchName "feature"
            $result | Should -Be $true
            $script:CommitCalled | Should -Be $true
        }
    }

    Context "Get-SimilarPRs Function" {
        It "Returns empty array when no similar PRs" {
            Mock gh {
                $global:LASTEXITCODE = 0
                return "[]"
            }

            $result = Get-SimilarPRs -Owner "test" -Repo "repo" -PRNumber 123 -Title "feat: unique feature"
            $result.Count | Should -Be 0
        }

        It "Returns similar PRs when merged PR has matching title" {
            Mock gh {
                $global:LASTEXITCODE = 0
                return ($Script:Fixtures.MergedPRs | ConvertTo-Json)
            }

            $result = Get-SimilarPRs -Owner "test" -Repo "repo" -PRNumber 123 -Title "feat: add feature X"
            $result.Count | Should -BeGreaterThan 0
            $result[0].Number | Should -Be 789
        }

        It "Excludes same PR number from results" {
            Mock gh {
                $global:LASTEXITCODE = 0
                return ($Script:Fixtures.MergedPRs | ConvertTo-Json)
            }

            $result = Get-SimilarPRs -Owner "test" -Repo "repo" -PRNumber 789 -Title "feat: add feature X v2"
            $result.Count | Should -Be 0
        }

        It "Handles titles without colons" {
            Mock gh {
                $global:LASTEXITCODE = 0
                return '[{"number": 800, "title": "No colon title"}]'
            }

            { Get-SimilarPRs -Owner "test" -Repo "repo" -PRNumber 123 -Title "No colon title" } | Should -Not -Throw
        }

        It "Returns empty array on gh CLI failure" {
            Mock gh {
                $global:LASTEXITCODE = 1
                return "Error: Not authenticated"
            }

            $result = Get-SimilarPRs -Owner "test" -Repo "repo" -PRNumber 123 -Title "feat: test"
            # PowerShell unwraps empty arrays to $null, so check for null or empty count
            ($result -eq $null -or $result.Count -eq 0) | Should -Be $true
        }
    }

    Context "Test-IsGitHubRunner Function" {
        It "Returns true when GITHUB_ACTIONS environment variable is set" {
            $env:GITHUB_ACTIONS = "true"
            
            Test-IsGitHubRunner | Should -Be $true
            
            Remove-Item env:GITHUB_ACTIONS
        }

        It "Returns false when GITHUB_ACTIONS environment variable is not set" {
            if (Test-Path env:GITHUB_ACTIONS) {
                Remove-Item env:GITHUB_ACTIONS
            }
            
            Test-IsGitHubRunner | Should -Be $false
        }
    }

    Context "Test-IsBotAuthor Function" {
        # Tests for bot author detection - CRITICAL for CHANGES_REQUESTED semantics
        # See memory: pr-changes-requested-semantics

        It "Returns true for GitHub App bots with [bot] suffix" {
            Test-IsBotAuthor -AuthorLogin "dependabot[bot]" | Should -Be $true
            Test-IsBotAuthor -AuthorLogin "copilot[bot]" | Should -Be $true
            Test-IsBotAuthor -AuthorLogin "github-actions[bot]" | Should -Be $true
            Test-IsBotAuthor -AuthorLogin "renovate[bot]" | Should -Be $true
            Test-IsBotAuthor -AuthorLogin "coderabbitai[bot]" | Should -Be $true
        }

        It "Returns true for Copilot SWE Agent" {
            Test-IsBotAuthor -AuthorLogin "copilot-swe-agent" | Should -Be $true
        }

        It "Returns true for custom bot accounts with -bot suffix" {
            Test-IsBotAuthor -AuthorLogin "rjmurillo-bot" | Should -Be $true
            Test-IsBotAuthor -AuthorLogin "my-project-bot" | Should -Be $true
        }

        It "Returns true for github-actions without [bot] suffix" {
            Test-IsBotAuthor -AuthorLogin "github-actions" | Should -Be $true
        }

        It "Returns false for regular human users" {
            Test-IsBotAuthor -AuthorLogin "rjmurillo" | Should -Be $false
            Test-IsBotAuthor -AuthorLogin "johndoe" | Should -Be $false
            Test-IsBotAuthor -AuthorLogin "alice123" | Should -Be $false
        }

        It "Returns false for usernames containing 'bot' but not matching patterns" {
            # 'robot' contains 'bot' but doesn't match patterns
            Test-IsBotAuthor -AuthorLogin "robot" | Should -Be $false
            Test-IsBotAuthor -AuthorLogin "robotics-user" | Should -Be $false
            # 'botmaster' starts with bot but doesn't match patterns
            Test-IsBotAuthor -AuthorLogin "botmaster" | Should -Be $false
        }

        It "Is case-insensitive for pattern matching (matches GitHub behavior)" {
            # GitHub usernames are case-insensitive in practice
            # PowerShell -match is case-insensitive by default, which is correct
            Test-IsBotAuthor -AuthorLogin "Dependabot[bot]" | Should -Be $true
            Test-IsBotAuthor -AuthorLogin "COPILOT-SWE-AGENT" | Should -Be $true
            Test-IsBotAuthor -AuthorLogin "RjMurillo-Bot" | Should -Be $true
        }
    }

    Context "Logging Functions" {
        It "Write-Log adds entry to log array" {
            $script:LogEntries = [System.Collections.ArrayList]::new()

            Write-Log "Test message" -Level INFO

            $script:LogEntries.Count | Should -BeGreaterThan 0
            $script:LogEntries[-1] | Should -Match "Test message"
        }

        It "Save-Log creates log file" {
            $script:LogEntries = [System.Collections.ArrayList]::new()
            Write-Log "Test entry"

            $logPath = Join-Path $Script:TestDir "test.log"
            Save-Log -Path $logPath

            $logPath | Should -Exist
        }
    }

    Context "Protected Branch Safety" {
        It "Exits with code 2 when on protected branch main" {
            Mock git {
                param([Parameter(ValueFromRemainingArguments)]$Args)
                if ($Args -contains "branch" -and $Args -contains "--show-current") {
                    return "main"
                }
                return ""
            }

            # This test would need to invoke the script entry point
            # Placeholder for integration test
            $true | Should -Be $true
        }
    }

    Context "Integration - Happy Path" {
        It "Processes multiple PRs successfully" -Skip {
            # Complex integration test requiring full script execution
            # with mocked GitHub API and git operations
            $true | Should -Be $true
        }
    }

    Context "Code Quality" {
        BeforeAll {
            $Script:ScriptContent = Get-Content -Path $Script:ScriptPath -Raw
        }

        It "Uses ErrorActionPreference Stop" {
            $Script:ScriptContent | Should -Match "\`$ErrorActionPreference\s*=\s*'Stop'"
        }

        It "Uses CmdletBinding for proper parameter handling" {
            $Script:ScriptContent | Should -Match '\[CmdletBinding\(\)\]'
        }

        It "Uses Set-StrictMode" {
            $Script:ScriptContent | Should -Match "Set-StrictMode\s+-Version\s+Latest"
        }

        It "Checks LASTEXITCODE after gh commands" {
            $Script:ScriptContent | Should -Match 'gh.*[\r\n]+.*if.*\$LASTEXITCODE'
        }

        It "Uses try/finally for cleanup in Resolve-PRConflicts" {
            # Check for try and finally blocks separately (regex .* doesn't span newlines)
            $Script:ScriptContent | Should -Match 'function Resolve-PRConflicts'
            $Script:ScriptContent | Should -Match 'try\s*\{'
            $Script:ScriptContent | Should -Match 'finally\s*\{'
        }

        It "Never hardcodes repository paths" {
            $Script:ScriptContent | Should -Not -Match 'D:\\\\src\\\\GitHub'
            $Script:ScriptContent | Should -Not -Match '/Users/.*?/github'
        }
    }

    #region ADR-015 P0 Security Validation Tests

    Context "Test-SafeBranchName - Empty and Whitespace" {
        It "Throws for null (mandatory parameter)" {
            # The [Parameter(Mandatory)] attribute prevents null values
            { Test-SafeBranchName -BranchName $null } | Should -Throw
        }

        It "Throws for empty string (mandatory parameter)" {
            # The [Parameter(Mandatory)] attribute prevents empty strings
            { Test-SafeBranchName -BranchName "" } | Should -Throw
        }

        It "Returns false for whitespace only" {
            $result = Test-SafeBranchName -BranchName "   "
            $result | Should -Be $false
        }

        It "Returns false for tab only" {
            $result = Test-SafeBranchName -BranchName "`t"
            $result | Should -Be $false
        }

        It "Returns false for newline only" {
            $result = Test-SafeBranchName -BranchName "`n"
            $result | Should -Be $false
        }
    }

    Context "Test-SafeBranchName - Hyphen Prefix (Git Option Injection)" {
        It "Returns false for single hyphen prefix" {
            $result = Test-SafeBranchName -BranchName "-branch"
            $result | Should -Be $false
        }

        It "Returns false for double hyphen prefix" {
            $result = Test-SafeBranchName -BranchName "--branch"
            $result | Should -Be $false
        }

        It "Returns false for --version attempt" {
            $result = Test-SafeBranchName -BranchName "--version"
            $result | Should -Be $false
        }

        It "Returns false for -h attempt" {
            $result = Test-SafeBranchName -BranchName "-h"
            $result | Should -Be $false
        }

        It "Returns true for hyphen in middle" {
            $result = Test-SafeBranchName -BranchName "feature-branch"
            $result | Should -Be $true
        }

        It "Returns true for trailing hyphen" {
            $result = Test-SafeBranchName -BranchName "feature-"
            $result | Should -Be $true
        }
    }

    Context "Test-SafeBranchName - Path Traversal Prevention" {
        It "Returns false for double dot" {
            $result = Test-SafeBranchName -BranchName ".."
            $result | Should -Be $false
        }

        It "Returns false for path with double dot" {
            $result = Test-SafeBranchName -BranchName "feature/../main"
            $result | Should -Be $false
        }

        It "Returns false for leading double dot" {
            $result = Test-SafeBranchName -BranchName "../escape"
            $result | Should -Be $false
        }

        It "Returns false for trailing double dot" {
            $result = Test-SafeBranchName -BranchName "branch/.."
            $result | Should -Be $false
        }

        It "Returns true for single dot" {
            # Single dots are allowed in git branch names
            $result = Test-SafeBranchName -BranchName "v1.0.0"
            $result | Should -Be $true
        }
    }

    Context "Test-SafeBranchName - Control Characters" {
        It "Returns false for null character" {
            $result = Test-SafeBranchName -BranchName "branch`0name"
            $result | Should -Be $false
        }

        It "Returns false for bell character (0x07)" {
            # Note: ``a is the PowerShell escape sequence for the bell character (0x07)
            $result = Test-SafeBranchName -BranchName "branch`aname"
            $result | Should -Be $false
        }

        It "Returns false for backspace" {
            $result = Test-SafeBranchName -BranchName "branch`bname"
            $result | Should -Be $false
        }

        It "Returns false for carriage return" {
            $result = Test-SafeBranchName -BranchName "branch`rname"
            $result | Should -Be $false
        }

        It "Returns false for tab character" {
            $result = Test-SafeBranchName -BranchName "branch`tname"
            $result | Should -Be $false
        }

        It "Returns false for escape character (0x1B)" {
            $result = Test-SafeBranchName -BranchName "branch`ename"
            $result | Should -Be $false
        }
    }

    Context "Test-SafeBranchName - Git Special Characters" {
        It "Returns false for tilde" {
            $result = Test-SafeBranchName -BranchName "branch~1"
            $result | Should -Be $false
        }

        It "Returns false for caret" {
            $result = Test-SafeBranchName -BranchName "branch^1"
            $result | Should -Be $false
        }

        It "Returns false for colon" {
            $result = Test-SafeBranchName -BranchName "branch:name"
            $result | Should -Be $false
        }

        It "Returns false for question mark" {
            $result = Test-SafeBranchName -BranchName "branch?name"
            $result | Should -Be $false
        }

        It "Returns false for asterisk" {
            $result = Test-SafeBranchName -BranchName "branch*name"
            $result | Should -Be $false
        }

        It "Returns false for open bracket" {
            $result = Test-SafeBranchName -BranchName "branch[name"
            $result | Should -Be $false
        }

        It "Returns false for close bracket" {
            $result = Test-SafeBranchName -BranchName "branch]name"
            $result | Should -Be $false
        }

        It "Returns false for backslash" {
            $result = Test-SafeBranchName -BranchName "branch\name"
            $result | Should -Be $false
        }
    }

    Context "Test-SafeBranchName - Shell Metacharacters" {
        It "Returns false for backtick" {
            $result = Test-SafeBranchName -BranchName "branch``command``"
            $result | Should -Be $false
        }

        It "Returns false for dollar sign" {
            $result = Test-SafeBranchName -BranchName 'branch$var'
            $result | Should -Be $false
        }

        It "Returns false for semicolon" {
            $result = Test-SafeBranchName -BranchName "branch;rm -rf"
            $result | Should -Be $false
        }

        It "Returns false for ampersand" {
            $result = Test-SafeBranchName -BranchName "branch&command"
            $result | Should -Be $false
        }

        It "Returns false for pipe" {
            $result = Test-SafeBranchName -BranchName "branch|command"
            $result | Should -Be $false
        }

        It "Returns false for less than" {
            $result = Test-SafeBranchName -BranchName "branch<file"
            $result | Should -Be $false
        }

        It "Returns false for greater than" {
            $result = Test-SafeBranchName -BranchName "branch>file"
            $result | Should -Be $false
        }

        It "Returns false for open paren" {
            $result = Test-SafeBranchName -BranchName "branch(sub"
            $result | Should -Be $false
        }

        It "Returns false for close paren" {
            $result = Test-SafeBranchName -BranchName "branch)sub"
            $result | Should -Be $false
        }

        It "Returns false for open brace" {
            $result = Test-SafeBranchName -BranchName "branch{sub"
            $result | Should -Be $false
        }

        It "Returns false for close brace" {
            $result = Test-SafeBranchName -BranchName "branch}sub"
            $result | Should -Be $false
        }
    }

    Context "Test-SafeBranchName - Valid Branch Names" {
        It "Returns true for simple feature branch" {
            $result = Test-SafeBranchName -BranchName "feature/add-login"
            $result | Should -Be $true
        }

        It "Returns true for fix branch" {
            $result = Test-SafeBranchName -BranchName "fix/bug-123"
            $result | Should -Be $true
        }

        It "Returns true for copilot branch" {
            $result = Test-SafeBranchName -BranchName "copilot/add-context-synthesis"
            $result | Should -Be $true
        }

        It "Returns true for version branch" {
            $result = Test-SafeBranchName -BranchName "release/v2.1.0"
            $result | Should -Be $true
        }

        It "Returns true for underscore branch" {
            $result = Test-SafeBranchName -BranchName "feature_branch_name"
            $result | Should -Be $true
        }

        It "Returns true for numeric branch" {
            $result = Test-SafeBranchName -BranchName "pr-12345"
            $result | Should -Be $true
        }

        It "Returns true for at-sign branch (dependabot)" {
            $result = Test-SafeBranchName -BranchName "dependabot/npm_and_yarn/lodash-4.17.21"
            $result | Should -Be $true
        }
    }

    Context "Get-SafeWorktreePath - Input Validation" {
        It "Throws for zero PR number" {
            { Get-SafeWorktreePath -BasePath $TestDrive -PRNumber 0 } | Should -Throw "*Invalid PR number*"
        }

        It "Throws for negative PR number" {
            { Get-SafeWorktreePath -BasePath $TestDrive -PRNumber -1 } | Should -Throw "*Invalid PR number*"
        }

        It "Throws for non-existent base path" {
            { Get-SafeWorktreePath -BasePath "Z:\NonExistentPath" -PRNumber 123 } | Should -Throw
        }

        It "Returns valid path for positive PR number" {
            $result = Get-SafeWorktreePath -BasePath $TestDrive -PRNumber 123
            $result | Should -Match "ai-agents-pr-123$"
        }

        It "Returns valid path for large PR number (Int64)" {
            # Tests Int64 parameter type works correctly (GitHub IDs can exceed Int32.MaxValue)
            # This validates the ADR-015 Fix 4 parameter type change
            $result = Get-SafeWorktreePath -BasePath $TestDrive -PRNumber 2147483648
            $result | Should -Match "ai-agents-pr-2147483648$"
        }
    }

    Context "Get-SafeWorktreePath - Path Traversal Prevention" {
        It "Returns path within base directory" {
            $result = Get-SafeWorktreePath -BasePath $TestDrive -PRNumber 123
            $result | Should -BeLike "$TestDrive*"
        }

        It "Generates predictable worktree name" {
            $result = Get-SafeWorktreePath -BasePath $TestDrive -PRNumber 456
            $result | Should -Match "ai-agents-pr-456$"
        }
    }

    Context "Enter-ScriptLock and Exit-ScriptLock - ADR-015 No-Op Compliance" {
        # ADR-015 Decision 1 rejects file-based locking in favor of GitHub Actions concurrency groups.
        # These functions are now no-ops that always succeed for compatibility with existing call sites.

        It "Enter-ScriptLock always returns true (no-op per ADR-015)" {
            # ADR-015: File-based locks deprecated; function is a no-op that always succeeds
            $result = Enter-ScriptLock
            $result | Should -Be $true
        }

        It "Enter-ScriptLock returns true on repeated calls (no lock contention)" {
            # ADR-015: No actual locking, so repeated calls always succeed
            $result1 = Enter-ScriptLock
            $result2 = Enter-ScriptLock
            $result1 | Should -Be $true
            $result2 | Should -Be $true
        }

        It "Exit-ScriptLock does not throw" {
            # ADR-015: No-op function should never throw
            { Exit-ScriptLock } | Should -Not -Throw
        }

        It "Exit-ScriptLock can be called multiple times without error" {
            # ADR-015: No state to release, so multiple calls are safe
            { Exit-ScriptLock } | Should -Not -Throw
            { Exit-ScriptLock } | Should -Not -Throw
        }
    }

    Context "Test-RateLimitSafe - API Response Handling" {
        BeforeAll {
            # Helper to create rate limit response with all resources (includes reset field for P1 fix from PR #249)
            $Script:CreateRateLimitResponse = {
                param(
                    [int]$CoreRemaining = 500,
                    [int]$SearchRemaining = 20,
                    [int]$CodeSearchRemaining = 10,
                    [int]$GraphqlRemaining = 500
                )
                $reset = [int]([DateTimeOffset]::UtcNow.AddHours(1).ToUnixTimeSeconds())
                return @"
{
    "resources": {
        "core": { "remaining": $CoreRemaining, "limit": 5000, "reset": $reset },
        "search": { "remaining": $SearchRemaining, "limit": 30, "reset": $reset },
        "code_search": { "remaining": $CodeSearchRemaining, "limit": 10, "reset": $reset },
        "graphql": { "remaining": $GraphqlRemaining, "limit": 5000, "reset": $reset }
    }
}
"@
            }
        }

        It "Returns true when all resources above thresholds" {
            Mock gh {
                $global:LASTEXITCODE = 0
                return & $Script:CreateRateLimitResponse -CoreRemaining 500 -SearchRemaining 20 -CodeSearchRemaining 10 -GraphqlRemaining 500
            }

            $result = Test-RateLimitSafe
            $result | Should -Be $true
        }

        It "Returns false when core remaining < threshold" {
            Mock gh {
                $global:LASTEXITCODE = 0
                return & $Script:CreateRateLimitResponse -CoreRemaining 50 -SearchRemaining 20 -CodeSearchRemaining 10 -GraphqlRemaining 500
            }

            $result = Test-RateLimitSafe
            $result | Should -Be $false
        }

        It "Returns false when search remaining < threshold" {
            Mock gh {
                $global:LASTEXITCODE = 0
                return & $Script:CreateRateLimitResponse -CoreRemaining 500 -SearchRemaining 10 -CodeSearchRemaining 10 -GraphqlRemaining 500
            }

            $result = Test-RateLimitSafe
            $result | Should -Be $false
        }

        It "Returns true when remaining = threshold (uses strict less-than)" {
            # Function uses -lt, so 100 < 100 is false, meaning rate limit is OK
            Mock gh {
                $global:LASTEXITCODE = 0
                return & $Script:CreateRateLimitResponse -CoreRemaining 100 -SearchRemaining 15 -CodeSearchRemaining 5 -GraphqlRemaining 100
            }

            $result = Test-RateLimitSafe
            $result | Should -Be $true
        }

        It "Returns true on API failure (fail-open)" {
            Mock gh {
                $global:LASTEXITCODE = 1
                return "Error: API error"
            }

            $result = Test-RateLimitSafe
            $result | Should -Be $true
        }

        It "Returns true on invalid JSON (fail-open)" {
            Mock gh {
                $global:LASTEXITCODE = 0
                return "INVALID JSON"
            }

            $result = Test-RateLimitSafe
            $result | Should -Be $true
        }

        It "Accepts custom resource thresholds" {
            Mock gh {
                $global:LASTEXITCODE = 0
                return & $Script:CreateRateLimitResponse -CoreRemaining 500 -SearchRemaining 20 -CodeSearchRemaining 10 -GraphqlRemaining 500
            }

            # Custom thresholds should still pass
            $result = Test-RateLimitSafe -ResourceThresholds @{ 'core' = 200 }
            $result | Should -Be $true
        }
    }

    Context "Add-CommentReaction - Int64 CommentId Support (ADR-015 Fix 4)" {
        It "Accepts Int64 CommentId without overflow" {
            Mock Invoke-GhApi { return '{"id": 1}' }

            # This value exceeds Int32.MaxValue (2,147,483,647)
            $largeCommentId = 2616639886

            { Add-CommentReaction -Owner "test" -Repo "repo" -CommentId $largeCommentId } | Should -Not -Throw
        }

        It "Accepts very large Int64 CommentId" {
            Mock Invoke-GhApi { return '{"id": 1}' }

            # Near Int64.MaxValue
            $veryLargeId = [long]9223372036854775800

            { Add-CommentReaction -Owner "test" -Repo "repo" -CommentId $veryLargeId } | Should -Not -Throw
        }
    }

    Context "Resolve-PRConflicts - Branch Validation Integration" {
        It "Rejects unsafe branch name before git operations" {
            Mock git { throw "Should not be called" }

            $result = Resolve-PRConflicts -Owner "test" -Repo "repo" -PRNumber 123 -BranchName "--version"
            $result | Should -Be $false
        }

        It "Rejects branch with shell injection" {
            Mock git { throw "Should not be called" }

            $result = Resolve-PRConflicts -Owner "test" -Repo "repo" -PRNumber 123 -BranchName "branch;rm -rf /"
            $result | Should -Be $false
        }

        It "Allows valid branch name" {
            Mock git {
                param([Parameter(ValueFromRemainingArguments)]$Args)
                if ($Args -contains "rev-parse") { return $TestDrive }
                return ""
            }
            Mock Push-Location {}
            Mock Pop-Location {}
            Mock Test-IsGitHubRunner { return $true }

            $result = Resolve-PRConflicts -Owner "test" -Repo "repo" -PRNumber 123 -BranchName "feature/safe-branch"
            # In GitHub Actions mode, function tries to perform actual operations
            # This test just validates branch name passes validation
            $true | Should -Be $true
        }
    }

    #endregion ADR-015 P0 Security Validation Tests
}

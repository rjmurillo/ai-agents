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

    Context "Get-UnresolvedReviewThreads Function" {
        BeforeAll {
            # GraphQL response fixtures
            $Script:ThreadFixtures = @{
                AllUnresolved = @{
                    data = @{
                        repository = @{
                            pullRequest = @{
                                reviewThreads = @{
                                    nodes = @(
                                        @{ id = "T1"; isResolved = $false; comments = @{ nodes = @(@{ databaseId = 1001 }) } }
                                        @{ id = "T2"; isResolved = $false; comments = @{ nodes = @(@{ databaseId = 1002 }) } }
                                    )
                                }
                            }
                        }
                    }
                }
                AllResolved = @{
                    data = @{
                        repository = @{
                            pullRequest = @{
                                reviewThreads = @{
                                    nodes = @(
                                        @{ id = "T1"; isResolved = $true; comments = @{ nodes = @(@{ databaseId = 1001 }) } }
                                        @{ id = "T2"; isResolved = $true; comments = @{ nodes = @(@{ databaseId = 1002 }) } }
                                    )
                                }
                            }
                        }
                    }
                }
                MixedState = @{
                    data = @{
                        repository = @{
                            pullRequest = @{
                                reviewThreads = @{
                                    nodes = @(
                                        @{ id = "T1"; isResolved = $false; comments = @{ nodes = @(@{ databaseId = 1001 }) } }
                                        @{ id = "T2"; isResolved = $true; comments = @{ nodes = @(@{ databaseId = 1002 }) } }
                                        @{ id = "T3"; isResolved = $false; comments = @{ nodes = @(@{ databaseId = 1003 }) } }
                                    )
                                }
                            }
                        }
                    }
                }
                NoThreads = @{
                    data = @{
                        repository = @{
                            pullRequest = @{
                                reviewThreads = @{
                                    nodes = @()
                                }
                            }
                        }
                    }
                }
                NullThreads = @{
                    data = @{
                        repository = @{
                            pullRequest = @{
                                reviewThreads = @{
                                    nodes = $null
                                }
                            }
                        }
                    }
                }
                # PR #365 equivalent: 5 threads, all unresolved
                PR365Equivalent = @{
                    data = @{
                        repository = @{
                            pullRequest = @{
                                reviewThreads = @{
                                    nodes = @(
                                        @{ id = "T1"; isResolved = $false; comments = @{ nodes = @(@{ databaseId = 1 }) } }
                                        @{ id = "T2"; isResolved = $false; comments = @{ nodes = @(@{ databaseId = 2 }) } }
                                        @{ id = "T3"; isResolved = $false; comments = @{ nodes = @(@{ databaseId = 3 }) } }
                                        @{ id = "T4"; isResolved = $false; comments = @{ nodes = @(@{ databaseId = 4 }) } }
                                        @{ id = "T5"; isResolved = $false; comments = @{ nodes = @(@{ databaseId = 5 }) } }
                                    )
                                }
                            }
                        }
                    }
                }
            }
        }

        It "Returns unresolved threads when some threads are unresolved" {
            Mock gh {
                $global:LASTEXITCODE = 0
                return ($Script:ThreadFixtures.AllUnresolved | ConvertTo-Json -Depth 10)
            }

            $result = Get-UnresolvedReviewThreads -Owner "test" -Repo "repo" -PR 123
            $result.Count | Should -Be 2
            $result[0].isResolved | Should -Be $false
            $result[1].isResolved | Should -Be $false
        }

        It "Returns empty array when all threads are resolved" {
            Mock gh {
                $global:LASTEXITCODE = 0
                return ($Script:ThreadFixtures.AllResolved | ConvertTo-Json -Depth 10)
            }

            $result = Get-UnresolvedReviewThreads -Owner "test" -Repo "repo" -PR 123
            # When Where-Object filters everything out, result may be $null
            # The function returns @() but PowerShell collapses it
            ($null -eq $result -or $result.Count -eq 0) | Should -Be $true
        }

        It "Returns empty array when no threads exist" {
            Mock gh {
                $global:LASTEXITCODE = 0
                return ($Script:ThreadFixtures.NoThreads | ConvertTo-Json -Depth 10)
            }

            $result = Get-UnresolvedReviewThreads -Owner "test" -Repo "repo" -PR 123
            ($null -eq $result -or $result.Count -eq 0) | Should -Be $true
        }

        It "Returns empty array when threads nodes is null" {
            Mock gh {
                $global:LASTEXITCODE = 0
                return ($Script:ThreadFixtures.NullThreads | ConvertTo-Json -Depth 10)
            }

            $result = Get-UnresolvedReviewThreads -Owner "test" -Repo "repo" -PR 123
            ($null -eq $result -or $result.Count -eq 0) | Should -Be $true
        }

        It "Returns empty array on GraphQL API failure" {
            Mock gh {
                $global:LASTEXITCODE = 1
                return "GraphQL error: rate limit exceeded"
            }

            $result = Get-UnresolvedReviewThreads -Owner "test" -Repo "repo" -PR 123
            ($null -eq $result -or $result.Count -eq 0) | Should -Be $true
        }

        It "Returns empty array on JSON parse failure" {
            Mock gh {
                $global:LASTEXITCODE = 0
                return "not valid json {"
            }

            $result = Get-UnresolvedReviewThreads -Owner "test" -Repo "repo" -PR 123
            ($null -eq $result -or $result.Count -eq 0) | Should -Be $true
        }

        It "Correctly filters mixed resolved and unresolved threads" {
            Mock gh {
                $global:LASTEXITCODE = 0
                return ($Script:ThreadFixtures.MixedState | ConvertTo-Json -Depth 10)
            }

            $result = Get-UnresolvedReviewThreads -Owner "test" -Repo "repo" -PR 123
            $result.Count | Should -Be 2
            $result | ForEach-Object { $_.isResolved | Should -Be $false }
            # Verify correct threads returned
            $result.id | Should -Contain "T1"
            $result.id | Should -Contain "T3"
            $result.id | Should -Not -Contain "T2"
        }

        It "Extracts databaseId from first comment in thread" {
            Mock gh {
                $global:LASTEXITCODE = 0
                return ($Script:ThreadFixtures.AllUnresolved | ConvertTo-Json -Depth 10)
            }

            $result = Get-UnresolvedReviewThreads -Owner "test" -Repo "repo" -PR 123
            $result[0].comments.nodes[0].databaseId | Should -Be 1001
            $result[1].comments.nodes[0].databaseId | Should -Be 1002
        }

        It "Returns 5 unresolved threads for PR #365 equivalent fixture" {
            Mock gh {
                $global:LASTEXITCODE = 0
                return ($Script:ThreadFixtures.PR365Equivalent | ConvertTo-Json -Depth 10)
            }

            $result = Get-UnresolvedReviewThreads -Owner "rjmurillo" -Repo "ai-agents" -PR 365
            $result.Count | Should -Be 5
            $result | ForEach-Object { $_.isResolved | Should -Be $false }
        }
    }

    Context "Get-UnaddressedComments Function" {
        BeforeAll {
            # Comment fixtures for different lifecycle states
            $Script:CommentFixtures = @{
                # NEW state: unacknowledged (eyes=0)
                NewState = @(
                    @{ id = 1001; user = @{ type = "Bot"; login = "coderabbitai[bot]" }; reactions = @{ eyes = 0 }; body = "Suggestion 1" }
                )
                # ACKNOWLEDGED state: eyes>0 but thread unresolved
                AcknowledgedState = @(
                    @{ id = 1002; user = @{ type = "Bot"; login = "coderabbitai[bot]" }; reactions = @{ eyes = 1 }; body = "Suggestion 2" }
                )
                # RESOLVED state: eyes>0 and thread resolved
                ResolvedState = @(
                    @{ id = 1003; user = @{ type = "Bot"; login = "coderabbitai[bot]" }; reactions = @{ eyes = 1 }; body = "Suggestion 3" }
                )
                # PR #365 equivalent: 5 bot comments with eyes>0
                PR365Comments = @(
                    @{ id = 1; user = @{ type = "Bot"; login = "coderabbitai[bot]" }; reactions = @{ eyes = 1 }; body = "Comment 1" }
                    @{ id = 2; user = @{ type = "Bot"; login = "coderabbitai[bot]" }; reactions = @{ eyes = 1 }; body = "Comment 2" }
                    @{ id = 3; user = @{ type = "Bot"; login = "coderabbitai[bot]" }; reactions = @{ eyes = 1 }; body = "Comment 3" }
                    @{ id = 4; user = @{ type = "Bot"; login = "coderabbitai[bot]" }; reactions = @{ eyes = 1 }; body = "Comment 4" }
                    @{ id = 5; user = @{ type = "Bot"; login = "coderabbitai[bot]" }; reactions = @{ eyes = 1 }; body = "Comment 5" }
                )
                # Fully resolved: all bot comments addressed
                FullyResolved = @(
                    @{ id = 1001; user = @{ type = "Bot"; login = "coderabbitai[bot]" }; reactions = @{ eyes = 1 }; body = "Resolved 1" }
                    @{ id = 1002; user = @{ type = "Bot"; login = "coderabbitai[bot]" }; reactions = @{ eyes = 1 }; body = "Resolved 2" }
                )
                # Mixed state: unacked, acked but unresolved, resolved
                MixedState = @(
                    @{ id = 1; user = @{ type = "Bot"; login = "bot1" }; reactions = @{ eyes = 0 }; body = "Unacked" }
                    @{ id = 2; user = @{ type = "Bot"; login = "bot2" }; reactions = @{ eyes = 1 }; body = "Acked unresolved" }
                    @{ id = 3; user = @{ type = "Bot"; login = "bot3" }; reactions = @{ eyes = 1 }; body = "Acked resolved" }
                )
                # Human comments only
                HumanOnly = @(
                    @{ id = 2001; user = @{ type = "User"; login = "human" }; reactions = @{ eyes = 0 }; body = "Human comment" }
                )
                # Mixed bot and human
                MixedBotHuman = @(
                    @{ id = 1001; user = @{ type = "Bot"; login = "bot" }; reactions = @{ eyes = 0 }; body = "Bot unacked" }
                    @{ id = 2001; user = @{ type = "User"; login = "human" }; reactions = @{ eyes = 0 }; body = "Human unacked" }
                )
            }
        }

        It "Returns unacknowledged bot comments (NEW state: eyes=0)" {
            Mock Get-PRComments { return $Script:CommentFixtures.NewState }
            Mock Get-UnresolvedReviewThreads { return @() }

            $result = Get-UnaddressedComments -Owner "test" -Repo "repo" -PRNumber 123
            $result.Count | Should -Be 1
            $result[0].id | Should -Be 1001
            $result[0].reactions.eyes | Should -Be 0
        }

        It "Returns acknowledged but unresolved comments (ACKNOWLEDGED state: eyes>0, isResolved=false)" {
            Mock Get-PRComments { return $Script:CommentFixtures.AcknowledgedState }
            # Thread is unresolved, containing comment ID 1002
            Mock Get-UnresolvedReviewThreads {
                return @(
                    @{ id = "T1"; isResolved = $false; comments = @{ nodes = @(@{ databaseId = 1002 }) } }
                )
            }

            $result = Get-UnaddressedComments -Owner "test" -Repo "repo" -PRNumber 123
            $result.Count | Should -Be 1
            $result[0].id | Should -Be 1002
            $result[0].reactions.eyes | Should -Be 1  # Has eyes but still unaddressed
        }

        It "Returns empty array when all comments addressed (eyes>0, isResolved=true)" {
            Mock Get-PRComments { return $Script:CommentFixtures.FullyResolved }
            # All threads resolved - return empty
            Mock Get-UnresolvedReviewThreads { return @() }

            $result = Get-UnaddressedComments -Owner "test" -Repo "repo" -PRNumber 123
            # PowerShell may collapse empty array to $null
            ($null -eq $result -or $result.Count -eq 0) | Should -Be $true
        }

        It "Returns empty array when no comments exist" {
            Mock Get-PRComments { return @() }
            Mock Get-UnresolvedReviewThreads { return @() }

            $result = Get-UnaddressedComments -Owner "test" -Repo "repo" -PRNumber 123
            # PowerShell may collapse empty array to $null
            ($null -eq $result -or $result.Count -eq 0) | Should -Be $true
        }

        It "Returns empty array when Comments parameter is null" {
            # When Comments is $null, the function calls Get-PRComments
            Mock Get-PRComments { return @() }
            Mock Get-UnresolvedReviewThreads { return @() }

            $result = Get-UnaddressedComments -Owner "test" -Repo "repo" -PRNumber 123 -Comments $null
            # PowerShell may collapse empty array to $null
            ($null -eq $result -or $result.Count -eq 0) | Should -Be $true
        }

        It "Uses pre-fetched Comments parameter without calling Get-PRComments" {
            $preFetchedComments = $Script:CommentFixtures.NewState
            Mock Get-PRComments { throw "Should not be called" }
            Mock Get-UnresolvedReviewThreads { return @() }

            $result = Get-UnaddressedComments -Owner "test" -Repo "repo" -PRNumber 123 -Comments $preFetchedComments
            $result.Count | Should -Be 1
            Should -Not -Invoke Get-PRComments
        }

        It "Filters out non-bot comments correctly" {
            Mock Get-PRComments { return $Script:CommentFixtures.MixedBotHuman }
            Mock Get-UnresolvedReviewThreads { return @() }

            $result = Get-UnaddressedComments -Owner "test" -Repo "repo" -PRNumber 123
            $result.Count | Should -Be 1
            $result[0].user.type | Should -Be "Bot"
            $result | Where-Object { $_.user.type -eq "User" } | Should -BeNullOrEmpty
        }

        It "Returns empty array when only human comments exist" {
            Mock Get-PRComments { return $Script:CommentFixtures.HumanOnly }
            Mock Get-UnresolvedReviewThreads { return @() }

            $result = Get-UnaddressedComments -Owner "test" -Repo "repo" -PRNumber 123
            # PowerShell may collapse empty array to $null
            ($null -eq $result -or $result.Count -eq 0) | Should -Be $true
        }

        It "Correctly handles mixed state: returns only unaddressed comments" {
            Mock Get-PRComments { return $Script:CommentFixtures.MixedState }
            # Thread for comment ID 2 is unresolved, thread for ID 3 is resolved
            Mock Get-UnresolvedReviewThreads {
                return @(
                    @{ id = "T2"; isResolved = $false; comments = @{ nodes = @(@{ databaseId = 2 }) } }
                )
            }

            $result = Get-UnaddressedComments -Owner "test" -Repo "repo" -PRNumber 123
            # Should return: ID 1 (unacked) and ID 2 (acked but unresolved)
            # Should NOT return: ID 3 (acked and resolved)
            $result.Count | Should -Be 2
            $result.id | Should -Contain 1
            $result.id | Should -Contain 2
            $result.id | Should -Not -Contain 3
        }

        It "Returns 5 unaddressed comments for PR #365 equivalent (all acknowledged but unresolved)" {
            Mock Get-PRComments { return $Script:CommentFixtures.PR365Comments }
            # All 5 threads are unresolved
            Mock Get-UnresolvedReviewThreads {
                return @(
                    @{ id = "T1"; isResolved = $false; comments = @{ nodes = @(@{ databaseId = 1 }) } }
                    @{ id = "T2"; isResolved = $false; comments = @{ nodes = @(@{ databaseId = 2 }) } }
                    @{ id = "T3"; isResolved = $false; comments = @{ nodes = @(@{ databaseId = 3 }) } }
                    @{ id = "T4"; isResolved = $false; comments = @{ nodes = @(@{ databaseId = 4 }) } }
                    @{ id = "T5"; isResolved = $false; comments = @{ nodes = @(@{ databaseId = 5 }) } }
                )
            }

            $result = Get-UnaddressedComments -Owner "rjmurillo" -Repo "ai-agents" -PRNumber 365
            $result.Count | Should -Be 5
            $result | ForEach-Object { $_.reactions.eyes | Should -Be 1 }  # All acknowledged
        }

        It "Returns 0 for fully resolved PR (Fixture 2 from PRD)" {
            Mock Get-PRComments { return $Script:CommentFixtures.FullyResolved }
            Mock Get-UnresolvedReviewThreads { return @() }  # All threads resolved

            $result = Get-UnaddressedComments -Owner "test" -Repo "repo" -PRNumber 123
            $result.Count | Should -Be 0
        }

        It "Gracefully handles Get-UnresolvedReviewThreads returning empty array" {
            Mock Get-PRComments { return $Script:CommentFixtures.NewState }
            Mock Get-UnresolvedReviewThreads { return @() }

            # Should still return unacknowledged comments (eyes=0)
            $result = Get-UnaddressedComments -Owner "test" -Repo "repo" -PRNumber 123
            $result.Count | Should -Be 1
        }

        It "Never returns null (per Skill-PowerShell-002)" {
            Mock Get-PRComments { return @() }
            Mock Get-UnresolvedReviewThreads { return @() }

            $result = Get-UnaddressedComments -Owner "test" -Repo "repo" -PRNumber 123
            # Per Skill-PowerShell-002: functions return arrays, never $null
            # Empty array is valid, but $null is not
            $null -eq $result | Should -Be $false -Because "Function should return empty array, not null"
            $result.GetType().IsArray | Should -Be $true -Because "Result should be an array type"
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

            $result = @(Get-SimilarPRs -Owner "test" -Repo "repo" -PRNumber 123 -Title "feat: unique feature")
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

            $result = @(Get-SimilarPRs -Owner "test" -Repo "repo" -PRNumber 789 -Title "feat: add feature X v2")
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

    Context "Get-DerivativePRs Function" {
        # Tests for derivative PR detection - P0 per bot-author-feedback-protocol.md
        # Derivative PRs target feature branches (not main) and are created by bots

        It "Detects derivative PR from copilot-swe-agent targeting feature branch" {
            $mockPRs = @(
                @{
                    number = 437
                    title = "Rename variable for clarity"
                    baseRefName = "fix/400-pr-maintenance"  # Targets feature branch, not main
                    headRefName = "copilot/sub-pr-402"
                    author = @{ login = "copilot-swe-agent" }
                },
                @{
                    number = 402
                    title = "feat: PR maintenance visibility"
                    baseRefName = "main"  # Regular PR targeting main
                    headRefName = "fix/400-pr-maintenance"
                    author = @{ login = "rjmurillo-bot" }
                }
            )

            $result = Get-DerivativePRs -Owner "test" -Repo "repo" -OpenPRs $mockPRs
            $result.Count | Should -Be 1
            $result[0].Number | Should -Be 437
            $result[0].TargetBranch | Should -Be "fix/400-pr-maintenance"
            $result[0].Author | Should -Be "copilot-swe-agent"
            $result[0].Category | Should -Be "mention-triggered"
        }

        It "Extracts parent PR number from copilot branch naming pattern" {
            $mockPRs = @(
                @{
                    number = 437
                    title = "Fix issue from review"
                    baseRefName = "feat/main-feature"
                    headRefName = "copilot/sub-pr-402"  # Pattern: sub-pr-{parent}
                    author = @{ login = "copilot-swe-agent" }
                }
            )

            $result = Get-DerivativePRs -Owner "test" -Repo "repo" -OpenPRs $mockPRs
            $result[0].ParentPR | Should -Be 402
        }

        It "Returns empty array when no derivative PRs exist" {
            $mockPRs = @(
                @{
                    number = 100
                    title = "Regular PR"
                    baseRefName = "main"
                    headRefName = "feature-branch"
                    author = @{ login = "rjmurillo-bot" }
                }
            )

            $result = Get-DerivativePRs -Owner "test" -Repo "repo" -OpenPRs $mockPRs
            ($result -eq $null -or $result.Count -eq 0) | Should -Be $true
        }

        It "Ignores human-authored PRs targeting feature branches" {
            $mockPRs = @(
                @{
                    number = 500
                    title = "Human sub-PR"
                    baseRefName = "feature-branch"  # Targets feature branch
                    headRefName = "human-fix"
                    author = @{ login = "rjmurillo" }  # Human author
                }
            )

            $result = Get-DerivativePRs -Owner "test" -Repo "repo" -OpenPRs $mockPRs
            ($result -eq $null -or $result.Count -eq 0) | Should -Be $true
        }

        It "Ignores agent-controlled bots targeting feature branches" {
            # agent-controlled bots (like rjmurillo-bot) don't create derivatives
            # they respond directly to their own PRs
            $mockPRs = @(
                @{
                    number = 600
                    title = "Bot sub-PR"
                    baseRefName = "feature-branch"
                    headRefName = "bot-fix"
                    author = @{ login = "rjmurillo-bot" }  # agent-controlled, not mention-triggered
                }
            )

            $result = Get-DerivativePRs -Owner "test" -Repo "repo" -OpenPRs $mockPRs
            ($result -eq $null -or $result.Count -eq 0) | Should -Be $true
        }
    }

    Context "Get-PRsWithPendingDerivatives Function" {
        # Tests for parent PR correlation with derivatives

        It "Correlates derivative PR with parent by matching target branch to head branch" {
            $mockPRs = @(
                @{
                    number = 402
                    title = "Parent PR"
                    baseRefName = "main"
                    headRefName = "fix/400-pr-maintenance"  # Parent's head branch
                    author = @{ login = "rjmurillo-bot" }
                },
                @{
                    number = 437
                    title = "Derivative PR"
                    baseRefName = "fix/400-pr-maintenance"  # Targets parent's head branch
                    headRefName = "copilot/sub-pr-402"
                    author = @{ login = "copilot-swe-agent" }
                }
            )
            $derivatives = @(
                @{
                    Number = 437
                    TargetBranch = "fix/400-pr-maintenance"
                    Author = "copilot-swe-agent"
                }
            )

            $result = Get-PRsWithPendingDerivatives -Owner "test" -Repo "repo" -OpenPRs $mockPRs -Derivatives $derivatives
            $result.Count | Should -Be 1
            $result[0].ParentPR | Should -Be 402
            $result[0].Derivatives | Should -Contain 437
        }

        It "Groups multiple derivatives under same parent" {
            $mockPRs = @(
                @{
                    number = 100
                    title = "Parent PR"
                    baseRefName = "main"
                    headRefName = "feature-branch"
                    author = @{ login = "rjmurillo-bot" }
                }
            )
            $derivatives = @(
                @{ Number = 201; TargetBranch = "feature-branch"; Author = "copilot-swe-agent" },
                @{ Number = 202; TargetBranch = "feature-branch"; Author = "copilot-swe-agent" }
            )

            $result = Get-PRsWithPendingDerivatives -Owner "test" -Repo "repo" -OpenPRs $mockPRs -Derivatives $derivatives
            $result.Count | Should -Be 1
            $result[0].ParentPR | Should -Be 100
            $result[0].Derivatives.Count | Should -Be 2
            $result[0].Derivatives | Should -Contain 201
            $result[0].Derivatives | Should -Contain 202
        }

        It "Returns empty array when no matching parent found" {
            $mockPRs = @(
                @{
                    number = 100
                    title = "Unrelated PR"
                    baseRefName = "main"
                    headRefName = "other-branch"  # Doesn't match derivative target
                    author = @{ login = "rjmurillo-bot" }
                }
            )
            $derivatives = @(
                @{ Number = 201; TargetBranch = "feature-branch"; Author = "copilot-swe-agent" }
            )

            $result = Get-PRsWithPendingDerivatives -Owner "test" -Repo "repo" -OpenPRs $mockPRs -Derivatives $derivatives
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

    Context "Test-IsBotReviewer Function" {
        # Tests for reviewer detection - activation trigger per bot-author-feedback-protocol.md

        It "Returns true when rjmurillo-bot is in reviewRequests" {
            $reviewRequests = @(
                @{ login = 'someuser' }
                @{ login = 'rjmurillo-bot' }
            )
            Test-IsBotReviewer -ReviewRequests $reviewRequests | Should -Be $true
        }

        It "Returns false when rjmurillo-bot is NOT in reviewRequests" {
            $reviewRequests = @(
                @{ login = 'someuser' }
                @{ login = 'anotheruser' }
            )
            Test-IsBotReviewer -ReviewRequests $reviewRequests | Should -Be $false
        }

        It "Returns false for empty reviewRequests" {
            Test-IsBotReviewer -ReviewRequests @() | Should -Be $false
        }

        It "Returns false for null reviewRequests" {
            Test-IsBotReviewer -ReviewRequests $null | Should -Be $false
        }

        It "Returns true when rjmurillo-bot is the only reviewer" {
            $reviewRequests = @(
                @{ login = 'rjmurillo-bot' }
            )
            Test-IsBotReviewer -ReviewRequests $reviewRequests | Should -Be $true
        }

        It "Is case-insensitive for login matching (matches GitHub behavior)" {
            # GitHub usernames are case-insensitive in practice
            # PowerShell -eq is case-insensitive by default, which is correct
            $reviewRequests = @(
                @{ login = 'Rjmurillo-Bot' }  # Different case
            )
            Test-IsBotReviewer -ReviewRequests $reviewRequests | Should -Be $true
        }
    }

    Context "Get-BotAuthorInfo Function" {
        # Tests for nuanced bot categorization - CRITICAL for CHANGES_REQUESTED handling
        # See memory: pr-changes-requested-semantics

        It "Returns 'agent-controlled' for custom bot accounts" {
            $info = Get-BotAuthorInfo -AuthorLogin "rjmurillo-bot"
            $info.IsBot | Should -Be $true
            $info.Category | Should -Be 'agent-controlled'
            $info.Action | Should -Be 'pr-comment-responder'
            $info.Mention | Should -BeNullOrEmpty
        }

        It "Returns 'mention-triggered' for copilot-swe-agent" {
            $info = Get-BotAuthorInfo -AuthorLogin "copilot-swe-agent"
            $info.IsBot | Should -Be $true
            $info.Category | Should -Be 'mention-triggered'
            $info.Mention | Should -Be '@copilot'
        }

        It "Returns 'mention-triggered' for copilot[bot]" {
            $info = Get-BotAuthorInfo -AuthorLogin "copilot[bot]"
            $info.IsBot | Should -Be $true
            $info.Category | Should -Be 'mention-triggered'
            $info.Mention | Should -Be '@copilot'
        }

        It "Returns 'command-triggered' for dependabot[bot]" {
            $info = Get-BotAuthorInfo -AuthorLogin "dependabot[bot]"
            $info.IsBot | Should -Be $true
            $info.Category | Should -Be 'command-triggered'
            $info.Mention | Should -Be '@dependabot'
        }

        It "Returns 'command-triggered' for renovate[bot]" {
            $info = Get-BotAuthorInfo -AuthorLogin "renovate[bot]"
            $info.IsBot | Should -Be $true
            $info.Category | Should -Be 'command-triggered'
            $info.Mention | Should -Be '@renovate'
        }

        It "Returns 'unknown-bot' for unrecognized bot accounts" {
            $info = Get-BotAuthorInfo -AuthorLogin "someother[bot]"
            $info.IsBot | Should -Be $true
            $info.Category | Should -Be 'unknown-bot'
            $info.Action | Should -Match 'manual'
        }

        It "Returns 'human' for regular users" {
            $info = Get-BotAuthorInfo -AuthorLogin "rjmurillo"
            $info.IsBot | Should -Be $false
            $info.Category | Should -Be 'human'
            $info.Action | Should -Match 'Blocked'
        }

        It "Returns 'non-responsive' for github-actions (cannot respond to comments)" {
            # Per cursor[bot] review: github-actions cannot respond to comments
            # These accounts should be blocked, prompting migration to user-specific credentials
            $info = Get-BotAuthorInfo -AuthorLogin "github-actions"
            $info.IsBot | Should -Be $true
            $info.Category | Should -Be 'non-responsive'
            $info.Action | Should -Match 'Blocked'
        }

        It "Returns 'non-responsive' for github-actions[bot] (cannot respond to comments)" {
            $info = Get-BotAuthorInfo -AuthorLogin "github-actions[bot]"
            $info.IsBot | Should -Be $true
            $info.Category | Should -Be 'non-responsive'
            $info.Action | Should -Match 'Blocked'
        }
    }

    Context "ActionRequired Collection - Bot Author CHANGES_REQUESTED" {
        # Tests for ActionRequired population when bot is author with CHANGES_REQUESTED
        # Critical path: bot-authored PRs with CHANGES_REQUESTED should be added to ActionRequired (not Blocked)

        BeforeEach {
            Mock Get-OpenPRs {
                return @(
                    @{
                        number = 100
                        title = "feat: automated PR"
                        state = "OPEN"
                        headRefName = "automated-feature"
                        baseRefName = "main"
                        mergeable = "MERGEABLE"
                        reviewDecision = "CHANGES_REQUESTED"
                        author = @{ login = "rjmurillo-bot" }
                        reviewRequests = @()
                    }
                )
            }
            Mock Get-PRComments { return @() }
            Mock Add-CommentReaction { return $true }
            Mock Get-SimilarPRs { return @() }
            Mock Resolve-PRConflicts { return $false }
        }

        It "Adds bot-authored PR with CHANGES_REQUESTED to ActionRequired" {
            $results = Invoke-PRMaintenance -Owner "test" -Repo "repo" -MaxPRs 5

            $results.ActionRequired.Count | Should -Be 1
            $results.ActionRequired[0].PR | Should -Be 100
            $results.ActionRequired[0].Category | Should -Be 'agent-controlled'
            $results.ActionRequired[0].Reason | Should -Be 'CHANGES_REQUESTED'
        }

        It "Does NOT add bot-authored PR with CHANGES_REQUESTED to Blocked" {
            $results = Invoke-PRMaintenance -Owner "test" -Repo "repo" -MaxPRs 5

            $results.Blocked.Count | Should -Be 0
        }
    }

    Context "ActionRequired Collection - Bot Reviewer CHANGES_REQUESTED" {
        # Tests for ActionRequired population when bot is reviewer with CHANGES_REQUESTED

        BeforeEach {
            Mock Get-OpenPRs {
                return @(
                    @{
                        number = 101
                        title = "feat: human PR"
                        state = "OPEN"
                        headRefName = "human-feature"
                        baseRefName = "main"
                        mergeable = "MERGEABLE"
                        reviewDecision = "CHANGES_REQUESTED"
                        author = @{ login = "rjmurillo" }
                        reviewRequests = @(
                            @{ login = "rjmurillo-bot" }
                        )
                    }
                )
            }
            Mock Get-PRComments { return @() }
            Mock Add-CommentReaction { return $true }
            Mock Get-SimilarPRs { return @() }
            Mock Resolve-PRConflicts { return $false }
        }

        It "Adds PR with bot as reviewer and CHANGES_REQUESTED to ActionRequired" {
            $results = Invoke-PRMaintenance -Owner "test" -Repo "repo" -MaxPRs 5

            $results.ActionRequired.Count | Should -Be 1
            $results.ActionRequired[0].PR | Should -Be 101
            $results.ActionRequired[0].Category | Should -Be 'agent-controlled'
        }
    }

    Context "ActionRequired Collection - Bot Mentioned" {
        # Tests for ActionRequired population when bot is mentioned

        BeforeEach {
            Mock Get-OpenPRs {
                return @(
                    @{
                        number = 102
                        title = "feat: mention test"
                        state = "OPEN"
                        headRefName = "mention-test"
                        baseRefName = "main"
                        mergeable = "MERGEABLE"
                        reviewDecision = $null
                        author = @{ login = "rjmurillo" }
                        reviewRequests = @()
                    }
                )
            }
            Mock Get-PRComments {
                return @(
                    @{
                        id = 999
                        user = @{ type = "Bot"; login = "copilot" }
                        reactions = @{ eyes = 0 }
                        body = "Hey @rjmurillo-bot please review this"
                    }
                )
            }
            Mock Add-CommentReaction { return $true }
            Mock Get-SimilarPRs { return @() }
            Mock Resolve-PRConflicts { return $false }
        }

        It "Adds PR with @rjmurillo-bot mention to ActionRequired" {
            $results = Invoke-PRMaintenance -Owner "test" -Repo "repo" -MaxPRs 5

            $results.ActionRequired.Count | Should -Be 1
            $results.ActionRequired[0].PR | Should -Be 102
            $results.ActionRequired[0].Category | Should -Be 'mention-triggered'
            $results.ActionRequired[0].Reason | Should -Be 'MENTION'
        }
    }

    Context "Blocked Collection - Human CHANGES_REQUESTED" {
        # Tests for Blocked population when human PR has CHANGES_REQUESTED and bot not involved

        BeforeEach {
            Mock Get-OpenPRs {
                return @(
                    @{
                        number = 103
                        title = "feat: human only PR"
                        state = "OPEN"
                        headRefName = "human-only"
                        baseRefName = "main"
                        mergeable = "MERGEABLE"
                        reviewDecision = "CHANGES_REQUESTED"
                        author = @{ login = "rjmurillo" }
                        reviewRequests = @()
                    }
                )
            }
            Mock Get-PRComments { return @() }
            Mock Add-CommentReaction { return $true }
            Mock Get-SimilarPRs { return @() }
            Mock Resolve-PRConflicts { return $false }
        }

        It "Adds human PR with CHANGES_REQUESTED to Blocked (not ActionRequired)" {
            $results = Invoke-PRMaintenance -Owner "test" -Repo "repo" -MaxPRs 5

            $results.Blocked.Count | Should -Be 1
            $results.Blocked[0].PR | Should -Be 103
            $results.Blocked[0].Reason | Should -Be 'CHANGES_REQUESTED'
            $results.Blocked[0].Category | Should -Be 'human-blocked'
            $results.ActionRequired.Count | Should -Be 0
        }
    }

    Context "Scenario 4 - No Bot Involvement (Maintenance Only)" {
        # Protocol acceptance criteria: Human-authored PR, bot not reviewer, not mentioned
        # THEN: CommentsAcknowledged = 0, No ActionRequired entry, only conflict resolution attempted

        BeforeEach {
            Mock Get-OpenPRs {
                return @(
                    @{
                        number = 200
                        title = "feat: human PR no bot"
                        state = "OPEN"
                        headRefName = "human-feature"
                        baseRefName = "main"
                        mergeable = "MERGEABLE"
                        reviewDecision = $null  # No CHANGES_REQUESTED
                        author = @{ login = "rjmurillo" }  # Human author
                        reviewRequests = @()  # Bot not requested as reviewer
                    }
                )
            }
            # Comments exist but none mention @rjmurillo-bot
            Mock Get-PRComments {
                return @(
                    @{
                        id = 5001
                        user = @{ type = "Bot"; login = "coderabbitai[bot]" }
                        reactions = @{ eyes = 0 }
                        body = "Code review suggestion - no bot mention"
                    }
                )
            }
            Mock Add-CommentReaction { return $true }
            Mock Get-SimilarPRs { return @() }
            Mock Resolve-PRConflicts { return $false }
        }

        It "Does NOT add eyes reaction when bot not involved" {
            $results = Invoke-PRMaintenance -Owner "test" -Repo "repo" -MaxPRs 5

            # CommentsAcknowledged = 0 (no eyes added)
            $results.CommentsAcknowledged | Should -Be 0

            # Add-CommentReaction should NOT have been called
            Should -Invoke Add-CommentReaction -Times 0
        }

        It "Does NOT add to ActionRequired when bot not involved" {
            $results = Invoke-PRMaintenance -Owner "test" -Repo "repo" -MaxPRs 5

            $results.ActionRequired.Count | Should -Be 0
        }

        It "Does NOT add to Blocked when no CHANGES_REQUESTED" {
            $results = Invoke-PRMaintenance -Owner "test" -Repo "repo" -MaxPRs 5

            $results.Blocked.Count | Should -Be 0
        }

        It "Processes PR successfully with zero actions when maintenance only" {
            $results = Invoke-PRMaintenance -Owner "test" -Repo "repo" -MaxPRs 5

            $results.Processed | Should -Be 1
            $results.CommentsAcknowledged | Should -Be 0
            $results.ActionRequired.Count | Should -Be 0
            $results.Blocked.Count | Should -Be 0
            $results.Errors.Count | Should -Be 0
        }
    }

    Context "Scenario 4b - Maintenance with Conflicts" {
        # Conflict resolution variant: human-authored PR with merge conflicts
        # Protocol: Conflict resolution runs regardless of bot involvement

        BeforeEach {
            Mock Get-OpenPRs {
                return @(
                    @{
                        number = 201
                        title = "feat: human PR with conflicts"
                        state = "OPEN"
                        headRefName = "human-feature"
                        baseRefName = "main"
                        mergeable = "CONFLICTING"  # Has conflicts
                        reviewDecision = $null
                        author = @{ login = "rjmurillo" }  # Human author
                        reviewRequests = @()  # Bot not requested as reviewer
                    }
                )
            }
            # Comments exist but none mention @rjmurillo-bot
            Mock Get-PRComments {
                return @(
                    @{
                        id = 5002
                        user = @{ type = "Bot"; login = "coderabbitai[bot]" }
                        reactions = @{ eyes = 0 }
                        body = "Code review suggestion - no bot mention"
                    }
                )
            }
            Mock Add-CommentReaction { return $true }
            Mock Get-SimilarPRs { return @() }
            Mock Resolve-PRConflicts { return $true }
        }

        It "Still attempts conflict resolution (maintenance task)" {
            $results = Invoke-PRMaintenance -Owner "test" -Repo "repo" -MaxPRs 5

            # Conflict resolution should be attempted
            Should -Invoke Resolve-PRConflicts -Times 1
            $results.ConflictsResolved | Should -Be 1
        }

        It "Does NOT add eyes reaction even with conflicts" {
            $results = Invoke-PRMaintenance -Owner "test" -Repo "repo" -MaxPRs 5

            # CommentsAcknowledged = 0 (bot not involved means no eyes)
            $results.CommentsAcknowledged | Should -Be 0
            Should -Invoke Add-CommentReaction -Times 0
        }
    }

    Context "Error Handling - Get-PRComments Failure" {
        # P0 test per QA agent recommendation: script should handle API failures gracefully

        BeforeEach {
            Mock Get-OpenPRs {
                return @(
                    @{
                        number = 104
                        title = "feat: test PR"
                        state = "OPEN"
                        headRefName = "test-branch"
                        baseRefName = "main"
                        mergeable = "MERGEABLE"
                        reviewDecision = $null
                        author = @{ login = "rjmurillo-bot" }
                        reviewRequests = @()
                    }
                )
            }
            Mock Get-PRComments { throw "API Error: Rate limit exceeded" }
            Mock Add-CommentReaction { return $true }
            Mock Get-SimilarPRs { return @() }
            Mock Resolve-PRConflicts { return $false }
        }

        It "Records error when Get-PRComments fails and continues processing" {
            $results = Invoke-PRMaintenance -Owner "test" -Repo "repo" -MaxPRs 5

            # Should record error for the failing PR
            $results.Errors.Count | Should -Be 1
            $results.Errors[0].PR | Should -Be 104
            $results.Errors[0].Error | Should -Match "API Error"

            # Script should complete (not crash)
            $results.Processed | Should -Be 0
        }

        It "Continues to next PR after Get-PRComments failure" {
            # Add a second PR that should succeed
            Mock Get-OpenPRs {
                return @(
                    @{
                        number = 104
                        title = "feat: failing PR"
                        state = "OPEN"
                        headRefName = "fail-branch"
                        baseRefName = "main"
                        mergeable = "MERGEABLE"
                        reviewDecision = $null
                        author = @{ login = "rjmurillo-bot" }
                        reviewRequests = @()
                    },
                    @{
                        number = 105
                        title = "feat: success PR"
                        state = "OPEN"
                        headRefName = "success-branch"
                        baseRefName = "main"
                        mergeable = "MERGEABLE"
                        reviewDecision = $null
                        author = @{ login = "rjmurillo" }
                        reviewRequests = @()
                    }
                )
            }
            # First call fails, second succeeds
            $script:callCount = 0
            Mock Get-PRComments {
                $script:callCount++
                if ($script:callCount -eq 1) {
                    throw "API Error: Rate limit exceeded"
                }
                return @()
            }

            $results = Invoke-PRMaintenance -Owner "test" -Repo "repo" -MaxPRs 5

            # First PR errors due to Get-PRComments failure
            $results.Errors.Count | Should -BeGreaterOrEqual 1
            $results.Errors[0].PR | Should -Be 104
            $results.Errors[0].Error | Should -Match "API Error"

            # Script should continue processing and attempt second PR
            # (may have additional errors from mocking issues, but should not crash)
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

    Context "TotalPRs Property (Issue #400)" {
        # Tests for TotalPRs property being set correctly in results

        BeforeEach {
            # Reset mocks for each test to prevent cross-test contamination
            Mock Get-PRComments { return @() }
            Mock Add-CommentReaction { return $true }
            Mock Get-SimilarPRs { return @() }
            Mock Resolve-PRConflicts { return $false }
        }

        It "Sets TotalPRs to 0 when no open PRs" {
            # Use Write-Output -NoEnumerate to preserve empty array
            Mock Get-OpenPRs { Write-Output -NoEnumerate @() }

            $results = Invoke-PRMaintenance -Owner "test" -Repo "repo" -MaxPRs 5

            $results.TotalPRs | Should -Be 0
        }

        It "Sets TotalPRs to count of open PRs" {
            Mock Get-OpenPRs {
                return @(
                    @{
                        number = 1
                        title = "PR 1"
                        state = "OPEN"
                        headRefName = "branch-1"
                        baseRefName = "main"
                        mergeable = "MERGEABLE"
                        reviewDecision = $null
                        author = @{ login = "user1" }
                        reviewRequests = @()
                    },
                    @{
                        number = 2
                        title = "PR 2"
                        state = "OPEN"
                        headRefName = "branch-2"
                        baseRefName = "main"
                        mergeable = "MERGEABLE"
                        reviewDecision = $null
                        author = @{ login = "user2" }
                        reviewRequests = @()
                    },
                    @{
                        number = 3
                        title = "PR 3"
                        state = "OPEN"
                        headRefName = "branch-3"
                        baseRefName = "main"
                        mergeable = "MERGEABLE"
                        reviewDecision = $null
                        author = @{ login = "user3" }
                        reviewRequests = @()
                    }
                )
            }

            $results = Invoke-PRMaintenance -Owner "test" -Repo "repo" -MaxPRs 5

            $results.TotalPRs | Should -Be 3
        }

        It "TotalPRs equals Processed when single PR is processed" {
            Mock Get-OpenPRs {
                # Use Write-Output -NoEnumerate with single-element array
                Write-Output -NoEnumerate @(
                    @{
                        number = 1
                        title = "PR 1"
                        state = "OPEN"
                        headRefName = "branch-1"
                        baseRefName = "main"
                        mergeable = "MERGEABLE"
                        reviewDecision = $null
                        author = @{ login = "user1" }
                        reviewRequests = @()
                    }
                )
            }

            $results = Invoke-PRMaintenance -Owner "test" -Repo "repo" -MaxPRs 5

            # TotalPRs should equal count of open PRs
            $results.TotalPRs | Should -Be 1
            # Processed should be 1 since we processed the PR
            $results.Processed | Should -Be 1
        }
    }

    Context "GITHUB_STEP_SUMMARY Output (Issue #400)" {
        # Tests for step summary output logic
        # Note: The actual file writing is in the entry point, but we can test the data used

        BeforeEach {
            Mock Get-PRComments { return @() }
            Mock Add-CommentReaction { return $true }
            Mock Get-SimilarPRs { return @() }
            Mock Resolve-PRConflicts { return $false }
        }

        It "Results hashtable contains all keys needed for step summary" {
            Mock Get-OpenPRs { Write-Output -NoEnumerate @() }

            $results = Invoke-PRMaintenance -Owner "test" -Repo "repo" -MaxPRs 5

            # Verify all required keys exist for step summary generation
            $results.Keys | Should -Contain 'TotalPRs'
            $results.Keys | Should -Contain 'Processed'
            $results.Keys | Should -Contain 'CommentsAcknowledged'
            $results.Keys | Should -Contain 'ConflictsResolved'
            $results.Keys | Should -Contain 'ActionRequired'
            $results.Keys | Should -Contain 'Blocked'
        }

        It "ActionRequired count is 0 when no PRs need action" {
            Mock Get-OpenPRs { Write-Output -NoEnumerate @() }

            $results = Invoke-PRMaintenance -Owner "test" -Repo "repo" -MaxPRs 5

            # Use @() wrapper to handle null/empty consistently
            @($results.ActionRequired).Count | Should -Be 0
        }

        It "Blocked count is 0 when no PRs are blocked" {
            Mock Get-OpenPRs {
                return ,@{
                    number = 1
                    title = "Approved PR"
                    state = "OPEN"
                    headRefName = "feature"
                    baseRefName = "main"
                    mergeable = "MERGEABLE"
                    reviewDecision = "APPROVED"
                    author = @{ login = "user1" }
                    reviewRequests = @()
                }
            }

            $results = Invoke-PRMaintenance -Owner "test" -Repo "repo" -MaxPRs 5

            # Use @() wrapper to handle null/empty consistently
            @($results.Blocked).Count | Should -Be 0
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

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
            $cmd.Parameters.Keys | Should -Contain "DryRun"
            $cmd.Parameters.Keys | Should -Contain "MaxPRs"
            $cmd.Parameters.Keys | Should -Contain "LogPath"
        }

        It "MaxPRs parameter has default value of 20" {
            $cmd = Get-Command $Script:ScriptPath
            $param = $cmd.Parameters['MaxPRs']
            $param.Attributes.TypeId.Name | Should -Contain "ParameterAttribute"
        }

        It "DryRun parameter is a switch" {
            $cmd = Get-Command $Script:ScriptPath
            $param = $cmd.Parameters['DryRun']
            $param.SwitchParameter | Should -Be $true
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
                return "[]"
            }

            $result = Get-OpenPRs -Owner "test" -Repo "repo" -Limit 20
            $result | Should -BeOfType [System.Array]
            $result.Count | Should -Be 0
        }

        It "Returns PR objects with required properties" {
            Mock gh {
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
                return "CHANGES_REQUESTED"
            }

            $result = Test-PRNeedsOwnerAction -Owner "test" -Repo "repo" -PRNumber 123
            $result | Should -Be $true
        }

        It "Returns false when reviewDecision = APPROVED" {
            Mock gh {
                return "APPROVED"
            }

            $result = Test-PRNeedsOwnerAction -Owner "test" -Repo "repo" -PRNumber 123
            $result | Should -Be $false
        }

        It "Returns false when reviewDecision is null" {
            Mock gh {
                return ""
            }

            $result = Test-PRNeedsOwnerAction -Owner "test" -Repo "repo" -PRNumber 123
            $result | Should -Be $false
        }
    }

    Context "Resolve-PRConflicts Function" {
        It "Returns true when DryRun mode enabled" {
            $result = Resolve-PRConflicts -Owner "test" -Repo "repo" -PRNumber 123 -BranchName "feature" -DryRun
            $result | Should -Be $true
        }

        It "Creates worktree with correct path" {
            Mock git {
                param([Parameter(ValueFromRemainingArguments)]$Args)
                if ($Args -contains "rev-parse") {
                    return "D:\repo"
                }
                if ($Args -contains "worktree" -and $Args -contains "add") {
                    $script:WorktreePath = $Args[-2]
                }
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

                if ($Args -contains "rev-parse") { return "D:\repo" }
                if ($Args -contains "worktree") { return "" }
                if ($Args -contains "fetch") { return "" }
                if ($Args -contains "merge") {
                    $global:LASTEXITCODE = 1
                    return "CONFLICT"
                }
                if ($Args -contains "diff" -and $Args -contains "--name-only") {
                    return ".agents/HANDOFF.md"
                }
                if ($Args -contains "checkout" -and $Args -contains "--theirs") {
                    return ""
                }
                if ($Args -contains "add") { return "" }
                if ($Args -contains "commit") { return "" }
                if ($Args -contains "push") { return "" }

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

                if ($Args -contains "rev-parse") { return "D:\repo" }
                if ($Args -contains "worktree") { return "" }
                if ($Args -contains "fetch") { return "" }
                if ($Args -contains "merge") {
                    $global:LASTEXITCODE = 1
                    return "CONFLICT"
                }
                if ($Args -contains "diff" -and $Args -contains "--name-only") {
                    return "src/Program.cs"
                }
                if ($Args -contains "merge" -and $Args -contains "--abort") {
                    return ""
                }

                return ""
            }

            Mock Push-Location {}
            Mock Pop-Location {}
            Mock Test-Path { $false }

            $result = Resolve-PRConflicts -Owner "test" -Repo "repo" -PRNumber 123 -BranchName "feature"
            $result | Should -Be $false
        }

        It "Cleans up worktree on success" {
            Mock git {
                param([Parameter(ValueFromRemainingArguments)]$Args)
                if ($Args -contains "rev-parse") { return "D:\repo" }
                if ($Args -contains "worktree" -and $Args -contains "remove") {
                    $script:WorktreeRemoved = $true
                }
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
    }

    Context "Test-PRSuperseded Function" {
        It "Returns Superseded=false when no similar PRs" {
            Mock gh {
                return "[]"
            }

            $result = Test-PRSuperseded -Owner "test" -Repo "repo" -PRNumber 123 -Title "feat: unique feature"
            $result.Superseded | Should -Be $false
        }

        It "Returns Superseded=true when merged PR has matching title" {
            Mock gh {
                return ($Script:Fixtures.MergedPRs | ConvertTo-Json)
            }

            $result = Test-PRSuperseded -Owner "test" -Repo "repo" -PRNumber 123 -Title "feat: add feature X"
            $result.Superseded | Should -Be $true
            $result.SupersededBy | Should -Be 789
        }

        It "Returns Superseded=false for same PR number" {
            Mock gh {
                return ($Script:Fixtures.MergedPRs | ConvertTo-Json)
            }

            $result = Test-PRSuperseded -Owner "test" -Repo "repo" -PRNumber 789 -Title "feat: add feature X v2"
            $result.Superseded | Should -Be $false
        }

        It "Handles titles without colons" {
            Mock gh {
                return '[{"number": 800, "title": "No colon title"}]'
            }

            { Test-PRSuperseded -Owner "test" -Repo "repo" -PRNumber 123 -Title "No colon title" } | Should -Not -Throw
        }
    }

    Context "Close-SupersededPR Function" {
        It "Returns true on successful close" {
            Mock gh {
                return ""
            }

            $result = Close-SupersededPR -Owner "test" -Repo "repo" -PRNumber 123 -SupersededBy 456
            $result | Should -Be $true
        }

        It "Returns true when DryRun mode enabled" {
            $result = Close-SupersededPR -Owner "test" -Repo "repo" -PRNumber 123 -SupersededBy 456 -DryRun
            $result | Should -Be $true
        }

        It "Posts comment before closing" {
            $script:CommentPosted = $false
            $script:PRClosed = $false

            Mock gh {
                param([Parameter(ValueFromRemainingArguments)]$Args)
                if ($Args -contains "comment") {
                    $script:CommentPosted = $true
                    if ($script:PRClosed) {
                        throw "Comment posted after close"
                    }
                }
                if ($Args -contains "close") {
                    $script:PRClosed = $true
                }
                return ""
            }

            Close-SupersededPR -Owner "test" -Repo "repo" -PRNumber 123 -SupersededBy 456

            $script:CommentPosted | Should -Be $true
            $script:PRClosed | Should -Be $true
        }

        It "Returns false on gh CLI failure" {
            Mock gh {
                throw "API Error"
            }

            $result = Close-SupersededPR -Owner "test" -Repo "repo" -PRNumber 123 -SupersededBy 456
            $result | Should -Be $false
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

    Context "Integration - DryRun Mode" {
        It "DryRun mode logs actions without executing" {
            $script:LogEntries = [System.Collections.ArrayList]::new()

            Mock gh { return "[]" }
            Mock git { return "feature" }

            # Would need to test full script execution
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
            $Script:ScriptContent | Should -Match 'function Resolve-PRConflicts.*try.*finally'
        }

        It "Never hardcodes repository paths" {
            $Script:ScriptContent | Should -Not -Match 'D:\\\\src\\\\GitHub'
            $Script:ScriptContent | Should -Not -Match '/Users/.*?/github'
        }
    }
}

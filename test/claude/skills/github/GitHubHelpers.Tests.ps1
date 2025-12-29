#Requires -Modules Pester

<#
.SYNOPSIS
    Tests for GitHubHelpers.psm1 shared module
#>

BeforeAll {
    # Correct path: from .github/tests/skills/github -> .claude/skills/github/modules
    $ModulePath = Join-Path $PSScriptRoot ".." ".." ".." ".." ".claude" "skills" "github" "modules" "GitHubHelpers.psm1"
    Import-Module $ModulePath -Force
}

Describe "GitHubHelpers Module" {

    Context "Module Loading" {
        It "Exports Get-RepoInfo function" {
            Get-Command -Module GitHubHelpers -Name Get-RepoInfo | Should -Not -BeNullOrEmpty
        }

        It "Exports Resolve-RepoParams function" {
            Get-Command -Module GitHubHelpers -Name Resolve-RepoParams | Should -Not -BeNullOrEmpty
        }

        It "Exports Test-GhAuthenticated function" {
            Get-Command -Module GitHubHelpers -Name Test-GhAuthenticated | Should -Not -BeNullOrEmpty
        }

        It "Exports Assert-GhAuthenticated function" {
            Get-Command -Module GitHubHelpers -Name Assert-GhAuthenticated | Should -Not -BeNullOrEmpty
        }

        It "Exports Write-ErrorAndExit function" {
            Get-Command -Module GitHubHelpers -Name Write-ErrorAndExit | Should -Not -BeNullOrEmpty
        }

        It "Exports Invoke-GhApiPaginated function" {
            Get-Command -Module GitHubHelpers -Name Invoke-GhApiPaginated | Should -Not -BeNullOrEmpty
        }

        It "Exports Get-PriorityEmoji function" {
            Get-Command -Module GitHubHelpers -Name Get-PriorityEmoji | Should -Not -BeNullOrEmpty
        }

        It "Exports Get-ReactionEmoji function" {
            Get-Command -Module GitHubHelpers -Name Get-ReactionEmoji | Should -Not -BeNullOrEmpty
        }

        It "Exports Get-BotAuthorsConfig function" {
            Get-Command -Module GitHubHelpers -Name Get-BotAuthorsConfig | Should -Not -BeNullOrEmpty
        }

        It "Exports Get-BotAuthors function" {
            Get-Command -Module GitHubHelpers -Name Get-BotAuthors | Should -Not -BeNullOrEmpty
        }

        It "Exports Test-WorkflowRateLimit function" {
            Get-Command -Module GitHubHelpers -Name Test-WorkflowRateLimit | Should -Not -BeNullOrEmpty
        }
    }

    Context "Get-PriorityEmoji" {
        It "Returns fire emoji for P0" {
            Get-PriorityEmoji -Priority "P0" | Should -Be "🔥"
        }

        It "Returns exclamation for P1" {
            Get-PriorityEmoji -Priority "P1" | Should -Be "❗"
        }

        It "Returns dash for P2" {
            Get-PriorityEmoji -Priority "P2" | Should -Be "➖"
        }

        It "Returns down arrow for P3" {
            Get-PriorityEmoji -Priority "P3" | Should -Be "⬇️"
        }

        It "Returns question mark for unknown" {
            Get-PriorityEmoji -Priority "unknown" | Should -Be "❔"
        }
    }

    Context "Get-ReactionEmoji" {
        It "Returns thumbs up for +1" {
            Get-ReactionEmoji -Reaction "+1" | Should -Be "👍"
        }

        It "Returns thumbs down for -1" {
            Get-ReactionEmoji -Reaction "-1" | Should -Be "👎"
        }

        It "Returns laugh emoji" {
            Get-ReactionEmoji -Reaction "laugh" | Should -Be "😄"
        }

        It "Returns confused emoji" {
            Get-ReactionEmoji -Reaction "confused" | Should -Be "😕"
        }

        It "Returns heart emoji" {
            Get-ReactionEmoji -Reaction "heart" | Should -Be "❤️"
        }

        It "Returns hooray emoji" {
            Get-ReactionEmoji -Reaction "hooray" | Should -Be "🎉"
        }

        It "Returns rocket emoji" {
            Get-ReactionEmoji -Reaction "rocket" | Should -Be "🚀"
        }

        It "Returns eyes emoji" {
            Get-ReactionEmoji -Reaction "eyes" | Should -Be "👀"
        }
    }

    Context "Get-RepoInfo" {
        It "Returns null when not in git repo" {
            # This test depends on environment - mock if needed
            # For now, just verify it doesn't throw
            { Get-RepoInfo } | Should -Not -Throw
        }
    }

    Context "Test-GhAuthenticated" {
        It "Returns boolean" {
            $result = Test-GhAuthenticated
            $result | Should -BeOfType [bool]
        }
    }

    Context "Get-BotAuthorsConfig" {
        It "Returns hashtable with required keys" {
            $result = Get-BotAuthorsConfig
            $result | Should -BeOfType [hashtable]
            $result.Keys | Should -Contain 'reviewer'
            $result.Keys | Should -Contain 'automation'
            $result.Keys | Should -Contain 'repository'
        }

        It "Returns arrays for each category" {
            $result = Get-BotAuthorsConfig
            # Each category should contain at least one bot
            @($result['reviewer']).Count | Should -BeGreaterThan 0
            @($result['automation']).Count | Should -BeGreaterThan 0
            @($result['repository']).Count | Should -BeGreaterThan 0
        }

        It "Uses cached result on second call" {
            $result1 = Get-BotAuthorsConfig
            $result2 = Get-BotAuthorsConfig
            $result1 | Should -Be $result2
        }

        It "Reloads when Force is specified" {
            $result1 = Get-BotAuthorsConfig
            $result2 = Get-BotAuthorsConfig -Force
            $result2 | Should -Not -BeNullOrEmpty
        }

        It "Falls back to defaults when config file is missing" {
            $result = Get-BotAuthorsConfig -ConfigPath '/nonexistent/path/config.yml'
            $result | Should -BeOfType [hashtable]
            $result['reviewer'] | Should -Contain 'coderabbitai[bot]'
        }
    }

    Context "Get-BotAuthors" {
        It "Returns collection of strings" {
            $result = @(Get-BotAuthors)
            $result.Count | Should -BeGreaterThan 0
            $result | ForEach-Object { $_ | Should -BeOfType [string] }
        }

        It "Returns all bots by default" {
            $result = Get-BotAuthors
            $result | Should -Contain "coderabbitai[bot]"
            $result | Should -Contain "github-actions[bot]"
            $result | Should -Contain "rjmurillo-bot"
        }

        It "Returns only reviewer bots for Category 'reviewer'" {
            $result = Get-BotAuthors -Category 'reviewer'
            $result | Should -Contain "coderabbitai[bot]"
            $result | Should -Contain "github-copilot[bot]"
            $result | Should -Not -Contain "github-actions[bot]"
            $result | Should -Not -Contain "rjmurillo-bot"
        }

        It "Returns only automation bots for Category 'automation'" {
            $result = Get-BotAuthors -Category 'automation'
            $result | Should -Contain "github-actions[bot]"
            $result | Should -Contain "dependabot[bot]"
            $result | Should -Not -Contain "coderabbitai[bot]"
        }

        It "Returns only repository bots for Category 'repository'" {
            $result = Get-BotAuthors -Category 'repository'
            $result | Should -Contain "rjmurillo-bot"
            $result | Should -Contain "copilot-swe-agent[bot]"
            $result | Should -Not -Contain "github-actions[bot]"
        }

        It "Returns all bots for Category 'all'" {
            $result = Get-BotAuthors -Category 'all'
            $result | Should -Contain "coderabbitai[bot]"
            $result | Should -Contain "github-actions[bot]"
            $result | Should -Contain "rjmurillo-bot"
        }

        It "Returns sorted list" {
            $result = Get-BotAuthors
            $sorted = $result | Sort-Object
            $result | Should -Be $sorted
        }
    }

    Context "Test-WorkflowRateLimit" {
        It "Returns PSCustomObject with required properties" {
            Mock gh { '{"resources":{"core":{"remaining":5000,"limit":5000,"reset":1234567890},"search":{"remaining":30,"limit":30,"reset":1234567890},"code_search":{"remaining":10,"limit":10,"reset":1234567890},"graphql":{"remaining":5000,"limit":5000,"reset":1234567890}}}' }

            $result = Test-WorkflowRateLimit
            $result | Should -BeOfType [PSCustomObject]
            $result.Success | Should -BeOfType [bool]
            $result.Resources | Should -BeOfType [hashtable]
            $result.SummaryMarkdown | Should -BeOfType [string]
            $result.CoreRemaining | Should -BeOfType [int]
        }

        It "Returns Success=true when all resources above threshold" {
            Mock gh { '{"resources":{"core":{"remaining":5000,"limit":5000,"reset":1234567890},"search":{"remaining":30,"limit":30,"reset":1234567890},"code_search":{"remaining":10,"limit":10,"reset":1234567890},"graphql":{"remaining":5000,"limit":5000,"reset":1234567890}}}' }

            $result = Test-WorkflowRateLimit
            $result.Success | Should -Be $true
        }

        It "Returns Success=false when any resource below threshold" {
            Mock gh { '{"resources":{"core":{"remaining":50,"limit":5000,"reset":1234567890},"search":{"remaining":5,"limit":30,"reset":1234567890},"code_search":{"remaining":2,"limit":10,"reset":1234567890},"graphql":{"remaining":50,"limit":5000,"reset":1234567890}}}' }

            $result = Test-WorkflowRateLimit
            $result.Success | Should -Be $false
        }

        It "Handles missing resource with warning" {
            Mock gh { '{"resources":{"core":{"remaining":5000,"limit":5000,"reset":1234567890},"search":{"remaining":30,"limit":30,"reset":1234567890},"graphql":{"remaining":5000,"limit":5000,"reset":1234567890}}}' }
            Mock Write-Warning { }

            $result = Test-WorkflowRateLimit
            Should -Invoke Write-Warning -Times 1 -ParameterFilter { $Message -like "*code_search*" }
            $result.Success | Should -Be $false
        }

        It "Throws when gh api fails" {
            Mock gh { $global:LASTEXITCODE = 1; "API error" }

            { Test-WorkflowRateLimit } | Should -Throw "*Failed to fetch rate limits*"
        }

        It "Uses custom thresholds" {
            Mock gh { '{"resources":{"core":{"remaining":500,"limit":5000,"reset":1234567890}}}' }

            $result = Test-WorkflowRateLimit -ResourceThresholds @{ 'core' = 100 }
            $result.Success | Should -Be $true
        }

        It "Includes SummaryMarkdown with table" {
            Mock gh { '{"resources":{"core":{"remaining":5000,"limit":5000,"reset":1234567890}}}' }

            $result = Test-WorkflowRateLimit -ResourceThresholds @{ 'core' = 100 }
            $result.SummaryMarkdown | Should -Match '### API Rate Limit Status'
            $result.SummaryMarkdown | Should -Match '\| Resource \| Remaining \| Threshold \| Status \|'
            $result.SummaryMarkdown | Should -Match '\| core \| 5000 \| 100 \|'
        }
    }
}

Describe "Script Parameter Validation" {

    # Scripts with Import-Module can't be parsed with Get-Command directly
    # Use AST parsing instead to validate parameter definitions

    Context "Get-PRContext.ps1" {
        BeforeAll {
            $ScriptPath = Join-Path $PSScriptRoot ".." ".." ".." ".." ".claude" "skills" "github" "scripts" "pr" "Get-PRContext.ps1"
            $content = Get-Content $ScriptPath -Raw
        }

        It "Has PullRequest as mandatory parameter" {
            $content | Should -Match '\[Parameter\(Mandatory\)\].*\[int\]\$PullRequest'
        }

        It "Has optional Owner parameter" {
            $content | Should -Match '\[string\]\$Owner'
        }

        It "Has optional Repo parameter" {
            $content | Should -Match '\[string\]\$Repo'
        }

        It "Has IncludeDiff switch parameter" {
            $content | Should -Match '\[switch\]\$IncludeDiff'
        }

        It "Has IncludeChangedFiles switch parameter" {
            $content | Should -Match '\[switch\]\$IncludeChangedFiles'
        }

        It "Imports GitHubHelpers module" {
            $content | Should -Match 'Import-Module.*GitHubHelpers\.psm1'
        }
    }

    Context "Post-IssueComment.ps1" {
        BeforeAll {
            $ScriptPath = Join-Path $PSScriptRoot ".." ".." ".." ".." ".claude" "skills" "github" "scripts" "issue" "Post-IssueComment.ps1"
            $content = Get-Content $ScriptPath -Raw
        }

        It "Has Issue as mandatory parameter" {
            $content | Should -Match '\[Parameter\(Mandatory\)\].*\[int\]\$Issue'
        }

        It "Has Body and BodyFile in different parameter sets" {
            $content | Should -Match "ParameterSetName\s*=\s*'BodyText'"
            $content | Should -Match "ParameterSetName\s*=\s*'BodyFile'"
        }

        It "Has optional Marker parameter" {
            $content | Should -Match '\[string\]\$Marker'
        }

        It "Uses correct API endpoint" {
            $content | Should -Match 'repos/\$Owner/\$Repo/issues/\$Issue/comments'
        }
    }

    Context "Set-IssueLabels.ps1" {
        BeforeAll {
            $ScriptPath = Join-Path $PSScriptRoot ".." ".." ".." ".." ".claude" "skills" "github" "scripts" "issue" "Set-IssueLabels.ps1"
            $content = Get-Content $ScriptPath -Raw
        }

        It "Has Issue as mandatory parameter" {
            $content | Should -Match '\[Parameter\(Mandatory\)\].*\[int\]\$Issue'
        }

        It "Has Priority parameter with validation" {
            $content | Should -Match '\[ValidateSet\("P0",\s*"P1",\s*"P2",\s*"P3"'
        }

        It "Has Labels array parameter" {
            $content | Should -Match '\[string\[\]\]\$Labels'
        }
    }

    Context "Add-CommentReaction.ps1" {
        BeforeAll {
            $ScriptPath = Join-Path $PSScriptRoot ".." ".." ".." ".." ".claude" "skills" "github" "scripts" "reactions" "Add-CommentReaction.ps1"
            $content = Get-Content $ScriptPath -Raw
        }

        It "Has CommentId as mandatory parameter" {
            $content | Should -Match '\[Parameter\(Mandatory\)\].*\[long\]\$CommentId'
        }

        It "Has Reaction as mandatory parameter with validation" {
            $content | Should -Match '\[Parameter\(Mandatory\)\].*\[ValidateSet\('
            $content | Should -Match '"eyes"'
        }

        It "Has CommentType parameter with validation" {
            $content | Should -Match '\[ValidateSet\("review",\s*"issue"\)\]'
        }

        It "Uses correct API endpoints for reactions" {
            $content | Should -Match 'pulls/comments/\$CommentId/reactions'
            $content | Should -Match 'issues/comments/\$CommentId/reactions'
        }
    }

    Context "Post-PRCommentReply.ps1" {
        BeforeAll {
            $ScriptPath = Join-Path $PSScriptRoot ".." ".." ".." ".." ".claude" "skills" "github" "scripts" "pr" "Post-PRCommentReply.ps1"
            $content = Get-Content $ScriptPath -Raw
        }

        It "Has PullRequest as mandatory parameter" {
            $content | Should -Match '\[Parameter\(Mandatory\)\].*\[int\]\$PullRequest'
        }

        It "Uses dedicated /replies endpoint for thread replies" {
            $content | Should -Match 'pulls/\$PullRequest/comments/\$CommentId/replies'
        }

        It "Uses issues API for top-level comments" {
            $content | Should -Match 'issues/\$PullRequest/comments'
        }
    }
}

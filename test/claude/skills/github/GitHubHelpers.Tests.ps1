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

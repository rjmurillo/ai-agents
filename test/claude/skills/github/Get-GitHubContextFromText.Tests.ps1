#Requires -Modules Pester

<#
.SYNOPSIS
    Tests for Get-GitHubContextFromText.ps1 utility
#>

BeforeAll {
    # Path from test/claude/skills/github -> .claude/skills/github/scripts/utils
    $ScriptPath = Join-Path $PSScriptRoot ".." ".." ".." ".." ".claude" "skills" "github" "scripts" "utils" "Get-GitHubContextFromText.ps1"
    . $ScriptPath
}

Describe "Get-GitHubContextFromText" {

    Context "Full URL Extraction" {
        It "Extracts PR from full GitHub URL" {
            $result = Get-GitHubContextFromText -InputText "https://github.com/rjmurillo/ai-agents/pull/806"
            
            $result.Type | Should -Be 'PR'
            $result.Number | Should -Be 806
            $result.Owner | Should -Be 'rjmurillo'
            $result.Repo | Should -Be 'ai-agents'
            $result.Source | Should -Be 'FullURL'
        }

        It "Extracts Issue from full GitHub URL" {
            $result = Get-GitHubContextFromText -InputText "https://github.com/owner/repo/issues/123"
            
            $result.Type | Should -Be 'Issue'
            $result.Number | Should -Be 123
            $result.Owner | Should -Be 'owner'
            $result.Repo | Should -Be 'repo'
            $result.Source | Should -Be 'FullURL'
        }

        It "Extracts from URL with surrounding text" {
            $result = Get-GitHubContextFromText -InputText "Check out https://github.com/test/demo/pull/99 for details"
            
            $result.Type | Should -Be 'PR'
            $result.Number | Should -Be 99
            $result.Owner | Should -Be 'test'
            $result.Repo | Should -Be 'demo'
        }

        It "Validates owner name format" {
            $result = Get-GitHubContextFromText -InputText "https://github.com/invalid..name/repo/pull/1"
            
            $result.Type | Should -BeNullOrEmpty
            $result.Number | Should -BeNullOrEmpty
        }

        It "Validates repo name format" {
            $result = Get-GitHubContextFromText -InputText "https://github.com/owner/invalid@repo/pull/1"
            
            $result.Type | Should -BeNullOrEmpty
            $result.Number | Should -BeNullOrEmpty
        }
    }

    Context "Relative URL Extraction" {
        It "Extracts PR from relative URL with leading slash" {
            $result = Get-GitHubContextFromText -InputText "/pull/456"
            
            $result.Type | Should -Be 'PR'
            $result.Number | Should -Be 456
            $result.Owner | Should -BeNullOrEmpty
            $result.Repo | Should -BeNullOrEmpty
            $result.Source | Should -Be 'RelativeURL'
        }

        It "Extracts PR from relative URL without leading slash" {
            $result = Get-GitHubContextFromText -InputText "pull/789"
            
            $result.Type | Should -Be 'PR'
            $result.Number | Should -Be 789
            $result.Source | Should -Be 'RelativeURL'
        }

        It "Extracts Issue from relative URL with leading slash" {
            $result = Get-GitHubContextFromText -InputText "/issues/321"
            
            $result.Type | Should -Be 'Issue'
            $result.Number | Should -Be 321
            $result.Source | Should -Be 'RelativeURL'
        }

        It "Extracts Issue from relative URL without leading slash" {
            $result = Get-GitHubContextFromText -InputText "issues/654"
            
            $result.Type | Should -Be 'Issue'
            $result.Number | Should -Be 654
            $result.Source | Should -Be 'RelativeURL'
        }
    }

    Context "Text Pattern Extraction" {
        It "Extracts from 'PR #123' pattern" {
            $result = Get-GitHubContextFromText -InputText "Review PR #806 comments"
            
            $result.Type | Should -Be 'PR'
            $result.Number | Should -Be 806
            $result.Source | Should -Be 'TextPattern'
        }

        It "Extracts from 'PR 123' pattern without hash" {
            $result = Get-GitHubContextFromText -InputText "Review PR 806 comments"
            
            $result.Type | Should -Be 'PR'
            $result.Number | Should -Be 806
            $result.Source | Should -Be 'TextPattern'
        }

        It "Extracts from 'pull request #123' pattern" {
            $result = Get-GitHubContextFromText -InputText "Check pull request #999"
            
            $result.Type | Should -Be 'PR'
            $result.Number | Should -Be 999
            $result.Source | Should -Be 'TextPattern'
        }

        It "Extracts from 'Issue #123' pattern" {
            $result = Get-GitHubContextFromText -InputText "Fix Issue #456"
            
            $result.Type | Should -Be 'Issue'
            $result.Number | Should -Be 456
            $result.Source | Should -Be 'TextPattern'
        }

        It "Extracts from 'Issue 123' pattern without hash" {
            $result = Get-GitHubContextFromText -InputText "Close Issue 789"
            
            $result.Type | Should -Be 'Issue'
            $result.Number | Should -Be 789
            $result.Source | Should -Be 'TextPattern'
        }

        It "Is case-insensitive for keywords" {
            $result = Get-GitHubContextFromText -InputText "review pr #100"
            
            $result.Type | Should -Be 'PR'
            $result.Number | Should -Be 100
        }
    }

    Context "Hash Reference Extraction" {
        It "Extracts from #123 pattern (defaults to PR)" {
            $result = Get-GitHubContextFromText -InputText "Check #555"
            
            $result.Type | Should -Be 'PR'
            $result.Number | Should -Be 555
            $result.Source | Should -Be 'HashReference'
        }

        It "Extracts hash as PR when Type specified" {
            $result = Get-GitHubContextFromText -InputText "Check #555" -Type PR
            
            $result.Type | Should -Be 'PR'
            $result.Number | Should -Be 555
        }

        It "Extracts hash as Issue when Type specified" {
            $result = Get-GitHubContextFromText -InputText "Check #555" -Type Issue
            
            $result.Type | Should -Be 'Issue'
            $result.Number | Should -Be 555
        }

        It "Does not match hash within words" {
            $result = Get-GitHubContextFromText -InputText "Check variable#123"
            
            $result.Type | Should -BeNullOrEmpty
            $result.Number | Should -BeNullOrEmpty
        }
    }

    Context "Priority Order" {
        It "Prefers full URL over text pattern" {
            $result = Get-GitHubContextFromText -InputText "PR #100 at https://github.com/owner/repo/pull/200"
            
            $result.Number | Should -Be 200
            $result.Source | Should -Be 'FullURL'
        }

        It "Prefers relative URL over text pattern" {
            $result = Get-GitHubContextFromText -InputText "PR #100 or /pull/200"
            
            $result.Number | Should -Be 200
            $result.Source | Should -Be 'RelativeURL'
        }

        It "Prefers text pattern over hash reference" {
            $result = Get-GitHubContextFromText -InputText "#100 or PR #200"
            
            $result.Number | Should -Be 200
            $result.Source | Should -Be 'TextPattern'
        }

        It "Uses first match of same priority" {
            $result = Get-GitHubContextFromText -InputText "PR #100 and PR #200"
            
            $result.Number | Should -Be 100
        }
    }

    Context "Type Filter" {
        It "Returns only PR when Type=PR" {
            $result = Get-GitHubContextFromText -InputText "Issue #100" -Type PR
            
            $result.Type | Should -BeNullOrEmpty
            $result.Number | Should -BeNullOrEmpty
        }

        It "Returns only Issue when Type=Issue" {
            $result = Get-GitHubContextFromText -InputText "PR #100" -Type Issue
            
            $result.Type | Should -BeNullOrEmpty
            $result.Number | Should -BeNullOrEmpty
        }

        It "Returns any type when Type=Any" {
            $resultPR = Get-GitHubContextFromText -InputText "PR #100" -Type Any
            $resultIssue = Get-GitHubContextFromText -InputText "Issue #200" -Type Any
            
            $resultPR.Type | Should -Be 'PR'
            $resultIssue.Type | Should -Be 'Issue'
        }

        It "Filters URL extraction by type" {
            $result = Get-GitHubContextFromText -InputText "https://github.com/owner/repo/pull/100" -Type Issue
            
            $result.Type | Should -BeNullOrEmpty
        }
    }

    Context "Edge Cases" {
        It "Returns empty result for empty string" {
            $result = Get-GitHubContextFromText -InputText ""
            
            $result.Type | Should -BeNullOrEmpty
            $result.Number | Should -BeNullOrEmpty
            $result.Source | Should -Be 'None'
        }

        It "Returns empty result for whitespace only" {
            $result = Get-GitHubContextFromText -InputText "   "
            
            $result.Type | Should -BeNullOrEmpty
            $result.Number | Should -BeNullOrEmpty
            $result.Source | Should -Be 'None'
        }

        It "Returns empty result for text with no matches" {
            $result = Get-GitHubContextFromText -InputText "Just some random text"
            
            $result.Type | Should -BeNullOrEmpty
            $result.Number | Should -BeNullOrEmpty
            $result.Source | Should -Be 'None'
        }

        It "Handles multi-line input" {
            $inputText = @"
Review PR #806 comments
This is on multiple lines
https://github.com/owner/repo/pull/806
"@
            $result = Get-GitHubContextFromText -InputText $inputText

            $result.Type | Should -Be 'PR'
            $result.Number | Should -Be 806
        }

        It "Never returns null (Skill-PowerShell-002)" {
            $result = Get-GitHubContextFromText -InputText "no matches here"
            
            $result | Should -Not -BeNullOrEmpty
            $result | Should -BeOfType [PSCustomObject]
        }
    }

    Context "Pipeline Support" {
        It "Accepts input from pipeline" {
            $result = "Review PR #100" | Get-GitHubContextFromText
            
            $result.Type | Should -Be 'PR'
            $result.Number | Should -Be 100
        }

        It "Processes multiple pipeline inputs" {
            $results = "PR #100", "Issue #200", "#300" | Get-GitHubContextFromText
            
            $results.Count | Should -Be 3
            $results[0].Number | Should -Be 100
            $results[1].Number | Should -Be 200
            $results[2].Number | Should -Be 300
        }
    }

    Context "Security" {
        It "Does not execute commands in input" {
            $malicious = "PR #123; rm -rf /"
            $result = Get-GitHubContextFromText -InputText $malicious
            
            $result.Number | Should -Be 123
            # If command execution happened, test environment would be affected
        }

        It "Handles special regex characters safely" {
            $result = Get-GitHubContextFromText -InputText "PR #123 (.*)"
            
            $result.Number | Should -Be 123
        }

        It "Rejects invalid GitHub owner names" {
            # Owner with invalid characters
            $result = Get-GitHubContextFromText -InputText "https://github.com/owner@invalid/repo/pull/1"
            
            $result.Type | Should -BeNullOrEmpty
        }

        It "Rejects excessively long owner names" {
            # GitHub owner names are limited to 39 characters
            $longOwner = "a" * 50
            $result = Get-GitHubContextFromText -InputText "https://github.com/$longOwner/repo/pull/1"
            
            $result.Type | Should -BeNullOrEmpty
        }
    }

    Context "Real-World Examples" {
        It "Handles example from issue description" {
            $result = Get-GitHubContextFromText -InputText "Review PR 806 comments... https://github.com/rjmurillo/ai-agents/pull/806"
            
            $result.Type | Should -Be 'PR'
            $result.Number | Should -Be 806
            $result.Owner | Should -Be 'rjmurillo'
            $result.Repo | Should -Be 'ai-agents'
        }

        It "Handles conversational input" {
            $result = Get-GitHubContextFromText -InputText "Can you please review the comments on PR #806?"
            
            $result.Type | Should -Be 'PR'
            $result.Number | Should -Be 806
        }

        It "Handles URL with trailing path" {
            $result = Get-GitHubContextFromText -InputText "https://github.com/owner/repo/pull/123/files"
            
            $result.Type | Should -Be 'PR'
            $result.Number | Should -Be 123
            $result.Owner | Should -Be 'owner'
            $result.Repo | Should -Be 'repo'
        }
    }
}

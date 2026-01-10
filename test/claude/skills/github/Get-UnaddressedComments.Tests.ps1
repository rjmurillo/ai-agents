<#
.SYNOPSIS
    Tests for Get-UnaddressedComments.ps1

.DESCRIPTION
    Pester tests covering syntax validation, parameter handling, lifecycle detection,
    and error handling for the unaddressed comments detection script.
#>

BeforeAll {
    # Correct path: from test/claude/skills/github -> .claude/skills/github/scripts/pr
    $ScriptPath = Join-Path $PSScriptRoot '..' '..' '..' '..' '.claude' 'skills' 'github' 'scripts' 'pr' 'Get-UnaddressedComments.ps1'
    $ScriptContent = Get-Content -Path $ScriptPath -Raw
}

Describe 'Get-UnaddressedComments.ps1' {
    Context 'Script Syntax' {
        It 'Should be valid PowerShell' {
            $errors = $null
            [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]$errors)
            $errors | Should -BeNullOrEmpty
        }

        It 'Should have comment-based help' {
            $ScriptContent | Should -Match '\.SYNOPSIS'
            $ScriptContent | Should -Match '\.DESCRIPTION'
            $ScriptContent | Should -Match '\.PARAMETER'
            $ScriptContent | Should -Match '\.EXAMPLE'
        }

        It 'Should reference lifecycle model documentation' {
            $ScriptContent | Should -Match 'bot-author-feedback-protocol\.md'
        }

        It 'Should set strict mode' {
            $ScriptContent | Should -Match "Set-StrictMode\s+-Version\s+Latest"
        }
    }

    Context 'Parameter Definitions' {
        It 'Should define Owner parameter' {
            $ScriptContent | Should -Match '\[string\]\$Owner'
        }

        It 'Should define Repo parameter' {
            $ScriptContent | Should -Match '\[string\]\$Repo'
        }

        It 'Should define PullRequest as mandatory parameter' {
            $ScriptContent | Should -Match '\[Parameter\(Mandatory\)\][\s\S]*?\[int\]\$PullRequest'
        }

        It 'Should define Comments parameter for pre-fetched data' {
            $ScriptContent | Should -Match '\[array\]\$Comments'
        }
    }

    Context 'Lifecycle Model Compliance' {
        It 'Should document NEW -> ACKNOWLEDGED -> REPLIED -> RESOLVED lifecycle' {
            $ScriptContent | Should -Match 'NEW.*->.*ACKNOWLEDGED.*->.*REPLIED.*->.*RESOLVED'
        }

        It 'Should define addressed as acknowledged AND resolved' {
            $ScriptContent | Should -Match 'acknowledged.*AND[\s\S]*resolved|eyes\s*>\s*0.*AND[\s\S]*isResolved\s*=\s*true'
        }

        It 'Should define unaddressed as lacking acknowledgment OR unresolved' {
            $ScriptContent | Should -Match 'eyes\s*=\s*0.*OR|unacknowledged.*OR[\s\S]*unresolved'
        }

        It 'Should document semantic difference from Get-UnacknowledgedComments' {
            $ScriptContent | Should -Match 'Get-UnacknowledgedComments'
            $ScriptContent | Should -Match 'NEW\s+only|NEW\]'
        }
    }

    Context 'API Integration' {
        It 'Should query PR comments endpoint' {
            $ScriptContent | Should -Match 'repos/\$Owner/\$Repo/pulls/\$PR/comments'
        }

        It 'Should use gh api command' {
            $ScriptContent | Should -Match 'gh api'
        }

        It 'Should handle pre-fetched comments' {
            $ScriptContent | Should -Match 'if\s*\(\s*\$null\s*-eq\s*\$Comments\s*\)'
        }
    }

    Context 'Thread Resolution Integration' {
        It 'Should use GitHubCore module for Get-UnresolvedReviewThreads' {
            $ScriptContent | Should -Match 'GitHubCore\.psm1'
        }

        It 'Should import the module' {
            $ScriptContent | Should -Match 'Import-Module\s+\$modulePath'
        }

        It 'Should extract databaseId from thread comments' {
            $ScriptContent | Should -Match 'databaseId'
        }

        It 'Should fall back when module not found' {
            $ScriptContent | Should -Match 'if\s*\(\s*-not\s*\(\s*Test-Path\s+\$modulePath\s*\)'
        }
    }

    Context 'Comment Filtering Logic' {
        It 'Should filter for Bot user type' {
            $ScriptContent | Should -Match "user\.type\s*-eq\s*'Bot'"
        }

        It 'Should check eyes reactions for acknowledgment' {
            $ScriptContent | Should -Match 'reactions\.eyes\s*-eq\s*0'
        }

        It 'Should check unresolvedCommentIds for thread status' {
            $ScriptContent | Should -Match '\$unresolvedCommentIds\s*-contains'
        }

        It 'Should combine unacknowledged OR unresolved conditions' {
            $ScriptContent | Should -Match 'reactions\.eyes\s*-eq\s*0\s*-or'
        }
    }

    Context 'Error Handling' {
        It 'Should set ErrorActionPreference to Stop' {
            $ScriptContent | Should -Match "\`$ErrorActionPreference\s*=\s*'Stop'"
        }

        It 'Should check LASTEXITCODE after gh commands' {
            $ScriptContent | Should -Match '\$LASTEXITCODE\s*-ne\s*0'
        }

        It 'Should use Write-Warning for failures' {
            $ScriptContent | Should -Match 'Write-Warning'
        }

        It 'Should return empty array on failure' {
            $ScriptContent | Should -Match 'return\s+@\(\)'
        }
    }

    Context 'Function Definitions' {
        It 'Should define Get-UnaddressedComments function' {
            $ScriptContent | Should -Match 'function\s+Get-UnaddressedComments'
        }

        It 'Should define Get-PRComments helper function' {
            $ScriptContent | Should -Match 'function\s+Get-PRComments'
        }

        It 'Should define Get-RepoInfo function' {
            $ScriptContent | Should -Match 'function\s+Get-RepoInfo'
        }
    }

    Context 'Skill-PowerShell-002 Compliance' {
        It 'Should never return null - documents this requirement' {
            $ScriptContent | Should -Match 'Never\s+returns\s+\$null|never\s+\$null'
        }

        It 'Should wrap results in array' {
            $ScriptContent | Should -Match '@\(\$Comments\s*\||@\(\$parsed\)'
        }

        It 'Should return empty array for null/empty comments' {
            $ScriptContent | Should -Match '\$Comments\.Count\s*-eq\s*0[\s\S]*return\s+@\(\)'
        }
    }

    Context 'Entry Point Guard' {
        It 'Should have dot-source guard for testing' {
            $ScriptContent | Should -Match "if\s*\(\s*\`$MyInvocation\.InvocationName\s*-eq\s*'\.'\s*\)"
        }

        It 'Should auto-detect repo info' {
            $ScriptContent | Should -Match 'Get-RepoInfo'
        }

        It 'Should output JSON for machine consumption' {
            $ScriptContent | Should -Match 'ConvertTo-Json\s+-Depth\s+5'
        }
    }

    Context 'Pre-fetched Comments Optimization' {
        It 'Should accept pre-fetched comments to avoid duplicate API calls' {
            $ScriptContent | Should -Match '-Comments\s+\$comments|\$Comments\s+=\s+\$null'
        }

        It 'Should document API call avoidance in help' {
            $ScriptContent | Should -Match 'avoid\s+duplicate\s+API\s+calls|Pre-fetched\s+comments'
        }
    }
}

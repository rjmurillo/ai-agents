<#
.SYNOPSIS
    Tests for Get-UnresolvedReviewThreads.ps1

.DESCRIPTION
    Pester tests covering syntax validation, parameter handling, GraphQL operations,
    and error handling for the unresolved review threads query script.
#>

BeforeAll {
    # Correct path: from test/claude/skills/github -> .claude/skills/github/scripts/pr
    $ScriptPath = Join-Path $PSScriptRoot '..' '..' '..' '..' '.claude' 'skills' 'github' 'scripts' 'pr' 'Get-UnresolvedReviewThreads.ps1'
    $ScriptContent = Get-Content -Path $ScriptPath -Raw
}

Describe 'Get-UnresolvedReviewThreads.ps1' {
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
    }

    Context 'GraphQL Operations' {
        It 'Should query reviewThreads' {
            $ScriptContent | Should -Match 'reviewThreads\s*\(\s*first:\s*100\s*\)'
        }

        It 'Should query isResolved field' {
            $ScriptContent | Should -Match 'isResolved'
        }

        It 'Should query comments with databaseId' {
            $ScriptContent | Should -Match 'comments\s*\(\s*first:\s*1\s*\)'
            $ScriptContent | Should -Match 'databaseId'
        }

        It 'Should use gh api graphql command' {
            $ScriptContent | Should -Match 'gh api graphql'
        }

        It 'Should handle GraphQL response parsing' {
            $ScriptContent | Should -Match 'ConvertFrom-Json'
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

        It 'Should return empty array on API failure per FR2' {
            $ScriptContent | Should -Match 'return\s+@\(\)'
        }
    }

    Context 'Function Definitions' {
        It 'Should define Get-UnresolvedReviewThreads function' {
            $ScriptContent | Should -Match 'function\s+Get-UnresolvedReviewThreads'
        }

        It 'Should define Get-RepoInfo function' {
            $ScriptContent | Should -Match 'function\s+Get-RepoInfo'
        }

        It 'Should filter for unresolved threads' {
            $ScriptContent | Should -Match 'Where-Object\s*\{[\s\S]*?-not\s+\$_\.isResolved'
        }
    }

    Context 'Lifecycle Model Compliance' {
        It 'Should document NEW -> ACKNOWLEDGED -> REPLIED -> RESOLVED lifecycle' {
            $ScriptContent | Should -Match 'NEW\s*->\s*ACKNOWLEDGED'
        }

        It 'Should document that comment can be acknowledged but not resolved' {
            $ScriptContent | Should -Match 'acknowledged.*NOT\s+resolved|acknowledged\s+but\s+NOT\s+resolved'
        }
    }

    Context 'Skill-PowerShell-002 Compliance' {
        It 'Should never return null - documents this requirement' {
            $ScriptContent | Should -Match 'Never\s+returns\s+\$null|never\s+\$null'
        }

        It 'Should always return array type' {
            $ScriptContent | Should -Match '@\(\$threads\s*\|'
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

    Context 'Repository Info Retrieval' {
        It 'Should parse github.com remote URL' {
            $ScriptContent | Should -Match "github\\.com\[:/\]"
        }

        It 'Should extract Owner from regex match' {
            $ScriptContent | Should -Match '\$Matches\[1\]'
        }

        It 'Should extract Repo from regex match' {
            $ScriptContent | Should -Match '\$Matches\[2\]'
        }

        It 'Should strip .git suffix from repo name' {
            $ScriptContent | Should -Match "-replace\s+'\\.git\$'"
        }
    }

    Context 'Pagination Documentation' {
        It 'Should document 100-thread limit' {
            $ScriptContent | Should -Match 'first:\s*100'
        }

        It 'Should note pagination not implemented' {
            $ScriptContent | Should -Match 'Pagination\s+not\s+implemented|100\+\s+threads'
        }
    }
}

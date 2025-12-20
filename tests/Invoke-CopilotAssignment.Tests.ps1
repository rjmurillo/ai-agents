#Requires -Modules Pester

<#
.SYNOPSIS
    Pester tests for Invoke-CopilotAssignment.ps1

.DESCRIPTION
    Tests the Copilot context synthesis system including:
    - Configuration loading
    - Trusted source extraction
    - Synthesis comment generation
    - Idempotent marker detection
    - Update vs create logic
#>

BeforeAll {
    # tests/ is at repo root, script is at .claude/skills/github/scripts/issue/
    $repoRoot = Join-Path $PSScriptRoot ".."
    $scriptPath = Join-Path $repoRoot ".claude" "skills" "github" "scripts" "issue" "Invoke-CopilotAssignment.ps1"
    $modulePath = Join-Path $repoRoot ".claude" "skills" "github" "modules" "GitHubHelpers.psm1"
    $configPath = Join-Path $repoRoot ".claude" "skills" "github" "copilot-synthesis.yml"

    # Load script content for pattern-based testing
    $scriptContent = Get-Content $scriptPath -Raw
}

Describe "Invoke-CopilotAssignment Script Structure" {

    Context "Parameter Definitions" {
        It "Has IssueNumber as mandatory parameter" {
            $scriptContent | Should -Match '\[Parameter\(Mandatory\)\]\s*\[int\]\$IssueNumber'
        }

        It "Has optional Owner parameter" {
            $scriptContent | Should -Match '\[string\]\$Owner'
        }

        It "Has optional Repo parameter" {
            $scriptContent | Should -Match '\[string\]\$Repo'
        }

        It "Has optional ConfigPath parameter" {
            $scriptContent | Should -Match '\[string\]\$ConfigPath'
        }

        It "Supports ShouldProcess (WhatIf)" {
            $scriptContent | Should -Match '\[CmdletBinding\(SupportsShouldProcess\)\]'
        }
    }

    Context "Module Dependencies" {
        It "Imports GitHubHelpers module" {
            # Script defines module path and imports it
            $scriptContent | Should -Match 'GitHubHelpers\.psm1'
            $scriptContent | Should -Match 'Import-Module.*\$modulePath'
        }

        It "Uses Assert-GhAuthenticated" {
            $scriptContent | Should -Match 'Assert-GhAuthenticated'
        }

        It "Uses Resolve-RepoParams" {
            $scriptContent | Should -Match 'Resolve-RepoParams'
        }

        It "Uses Get-IssueComments from module" {
            $scriptContent | Should -Match 'Get-IssueComments'
        }

        It "Uses Get-TrustedSourceComments from module" {
            $scriptContent | Should -Match 'Get-TrustedSourceComments'
        }
    }

    Context "Idempotency Implementation" {
        It "Contains synthesis marker constant" {
            $scriptContent | Should -Match 'COPILOT-CONTEXT-SYNTHESIS'
        }

        It "Has Find-ExistingSynthesis function" {
            $scriptContent | Should -Match 'function Find-ExistingSynthesis'
        }

        It "Uses Update-IssueComment from module" {
            $scriptContent | Should -Match 'Update-IssueComment'
        }

        It "Uses New-IssueComment from module" {
            $scriptContent | Should -Match 'New-IssueComment'
        }

        It "Checks for existing synthesis before creating" {
            $scriptContent | Should -Match '\$existingSynthesis\s*=\s*Find-ExistingSynthesis'
        }

        It "Updates existing comment if found" {
            $scriptContent | Should -Match 'if\s*\(\$existingSynthesis\)'
            $scriptContent | Should -Match 'Update-IssueComment'
        }

        It "Creates new comment if not found" {
            $scriptContent | Should -Match 'New-IssueComment\s+-Owner'
        }
    }

    Context "Synthesis Template" {
        It "Includes @copilot mention" {
            $scriptContent | Should -Match '@copilot'
        }

        It "Has Maintainer Guidance section" {
            $scriptContent | Should -Match '## Maintainer Guidance'
        }

        It "Has AI Agent Recommendations section" {
            $scriptContent | Should -Match '## AI Agent Recommendations'
        }

        It "Includes timestamp footer" {
            $scriptContent | Should -Match 'Generated:'
        }
    }

    Context "Trusted Sources Extraction" {
        It "Uses Get-TrustedSourceComments from module" {
            $scriptContent | Should -Match 'Get-TrustedSourceComments'
        }

        It "Has Get-MaintainerGuidance function" {
            $scriptContent | Should -Match 'function Get-MaintainerGuidance'
        }

        It "Has Get-CodeRabbitPlan function" {
            $scriptContent | Should -Match 'function Get-CodeRabbitPlan'
        }

        It "Has Get-AITriageInfo function" {
            $scriptContent | Should -Match 'function Get-AITriageInfo'
        }

        It "Filters by trusted maintainers" {
            $scriptContent | Should -Match 'trusted_sources\.maintainers'
        }

        It "Filters by trusted AI agents" {
            $scriptContent | Should -Match 'trusted_sources\.ai_agents'
        }
    }

    Context "Copilot Assignment" {
        It "Has Set-CopilotAssignee function" {
            $scriptContent | Should -Match 'function Set-CopilotAssignee'
        }

        It "Assigns copilot-swe-agent" {
            $scriptContent | Should -Match 'copilot-swe-agent'
        }

        It "Uses gh issue edit for assignment" {
            $scriptContent | Should -Match 'gh issue edit.*--add-assignee'
        }
    }

    Context "Exit Codes Documentation" {
        It "Documents exit code 0 for success" {
            $scriptContent | Should -Match '0\s*=\s*Success'
        }

        It "Documents exit code 1 for invalid parameters" {
            $scriptContent | Should -Match '1\s*=\s*Invalid'
        }

        It "Documents exit code 2 for not found" {
            $scriptContent | Should -Match '2\s*=.*not found'
        }

        It "Documents exit code 3 for API error" {
            $scriptContent | Should -Match '3\s*=.*API'
        }

        It "Documents exit code 4 for auth error" {
            $scriptContent | Should -Match '4\s*=.*auth'
        }
    }
}

Describe "Configuration File" {

    BeforeAll {
        # Use the configPath from the top-level BeforeAll
        $repoRoot = Join-Path $PSScriptRoot ".."
        $configPath = Join-Path $repoRoot ".claude" "skills" "github" "copilot-synthesis.yml"
        $configContent = Get-Content $configPath -Raw
    }

    Context "File Structure" {
        It "Config file exists" {
            Test-Path $configPath | Should -Be $true
        }

        It "Contains trusted_sources section" {
            $configContent | Should -Match 'trusted_sources:'
        }

        It "Contains maintainers list" {
            $configContent | Should -Match 'maintainers:'
        }

        It "Contains ai_agents list" {
            $configContent | Should -Match 'ai_agents:'
        }

        It "Contains synthesis section" {
            $configContent | Should -Match 'synthesis:'
        }

        It "Contains marker definition" {
            $configContent | Should -Match 'marker:.*COPILOT-CONTEXT-SYNTHESIS'
        }
    }

    Context "Trusted Sources" {
        It "Includes rjmurillo as maintainer" {
            $configContent | Should -Match '-\s+rjmurillo\b'
        }

        It "Includes coderabbitai as AI agent" {
            $configContent | Should -Match '-\s+coderabbitai'
        }

        It "Includes github-actions as AI agent" {
            $configContent | Should -Match '-\s+github-actions'
        }
    }

    Context "Extraction Patterns" {
        It "Has coderabbit extraction patterns" {
            $configContent | Should -Match 'coderabbit:'
        }

        It "Has ai_triage extraction patterns" {
            $configContent | Should -Match 'ai_triage:'
        }

        It "Has AI triage marker" {
            $configContent | Should -Match 'AI-ISSUE-TRIAGE'
        }
    }
}

Describe "Synthesis Comment Marker" {

    BeforeAll {
        $marker = "<!-- COPILOT-CONTEXT-SYNTHESIS -->"
    }

    Context "Marker Format" {
        It "Is valid HTML comment" {
            $marker | Should -Match '^<!--.*-->$'
        }

        It "Contains identifier text" {
            $marker | Should -Match 'COPILOT-CONTEXT-SYNTHESIS'
        }

        It "Can be detected with regex" {
            $testBody = "Some text`n$marker`n@copilot context..."
            $testBody -match [regex]::Escape($marker) | Should -Be $true
        }

        It "Does not match similar markers" {
            $testBody = "<!-- AI-ISSUE-TRIAGE -->"
            $testBody -match [regex]::Escape($marker) | Should -Be $false
        }
    }
}

Describe "Pattern Matching" {

    Context "Maintainer Guidance Extraction" {
        It "Matches numbered list items" {
            $text = "1. First important point"
            $text -match '^\d+\.\s+(.+)$' | Should -Be $true
            $Matches[1] | Should -Be "First important point"
        }

        It "Matches bullet points with dash" {
            $text = "- Key decision here"
            $text -match '^[-*]\s+(.+)$' | Should -Be $true
            $Matches[1] | Should -Be "Key decision here"
        }

        It "Matches bullet points with asterisk" {
            $text = "* Another key point"
            $text -match '^[-*]\s+(.+)$' | Should -Be $true
            $Matches[1] | Should -Be "Another key point"
        }

        It "Does not match checkbox items" {
            $item = "[x] Completed task"
            $item -notmatch '^\[[ x]\]' | Should -Be $false
        }
    }

    Context "Issue/PR Reference Extraction" {
        It "Matches issue references" {
            $text = "Related to #123 and #456"
            $matches = [regex]::Matches($text, '#(\d+)')
            $matches.Count | Should -Be 2
            $matches[0].Groups[1].Value | Should -Be "123"
        }

        It "Matches PR references in text" {
            $text = "See PR #789 for details"
            $matches = [regex]::Matches($text, '#(\d+)')
            $matches.Count | Should -Be 1
            $matches[0].Groups[1].Value | Should -Be "789"
        }
    }

    Context "Priority Extraction" {
        It "Extracts priority from colon format" {
            $text = "Priority: P1"
            $text -match 'Priority[:\s]+(\S+)' | Should -Be $true
            $Matches[1] | Should -Be "P1"
        }

        It "Extracts priority from space format" {
            $text = "Priority P0"
            $text -match 'Priority[:\s]+(\S+)' | Should -Be $true
            $Matches[1] | Should -Be "P0"
        }
    }
}

Describe "WhatIf Behavior" {

    BeforeAll {
        $repoRoot = Join-Path $PSScriptRoot ".."
        $scriptPath = Join-Path $repoRoot ".claude" "skills" "github" "scripts" "issue" "Invoke-CopilotAssignment.ps1"
        $scriptContent = Get-Content $scriptPath -Raw
    }

    Context "ShouldProcess Pattern" {
        It "Script uses ShouldProcess for mutations" {
            $scriptContent | Should -Match '\$PSCmdlet\.ShouldProcess'
        }

        It "ShouldProcess guards comment operations" {
            $scriptContent | Should -Match 'ShouldProcess.*Issue.*Post synthesis'
        }
    }
}

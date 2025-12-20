#Requires -Modules Pester

<#
.SYNOPSIS
    Pester tests for Invoke-CopilotAssignment.ps1

.DESCRIPTION
    Tests the Copilot context synthesis system including:
    - Pattern-based structure validation
    - Configuration loading
    - Functional tests with behavior verification
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

#region Functional Tests with Mocked Dependencies

Describe "Get-MaintainerGuidance Function" {

    BeforeAll {
        # Load script to get access to functions
        $repoRoot = Join-Path $PSScriptRoot ".."
        $scriptPath = Join-Path $repoRoot ".claude" "skills" "github" "scripts" "issue" "Invoke-CopilotAssignment.ps1"

        # Parse script to extract the function
        $scriptContent = Get-Content $scriptPath -Raw

        # Extract and define the Get-MaintainerGuidance function for testing
        if ($scriptContent -match 'function Get-MaintainerGuidance \{[\s\S]*?(?=\nfunction|\n#endregion)') {
            $functionDef = $Matches[0]
            Invoke-Expression $functionDef
        }
    }

    Context "Empty Input" {
        It "Returns null for empty comments array" {
            $result = Get-MaintainerGuidance -Comments @() -Maintainers @("rjmurillo")
            $result | Should -BeNullOrEmpty
        }

        It "Returns null when no maintainer comments exist" {
            $comments = @(
                @{ user = @{ login = "someuser" }; body = "Just a comment" }
            )
            $result = Get-MaintainerGuidance -Comments $comments -Maintainers @("rjmurillo")
            $result | Should -BeNullOrEmpty
        }
    }

    Context "Bullet Point Extraction" {
        It "Extracts bullet points from maintainer comments" {
            $comments = @(
                @{
                    user = @{ login = "rjmurillo" }
                    body = "Here are my notes:`n- This is an important decision about architecture`n- Another key point about implementation"
                }
            )
            $result = Get-MaintainerGuidance -Comments $comments -Maintainers @("rjmurillo")
            $result | Should -Not -BeNullOrEmpty
            $result.Count | Should -BeGreaterThan 0
        }

        It "Extracts numbered items from maintainer comments" {
            $comments = @(
                @{
                    user = @{ login = "rjmurillo" }
                    body = "Steps to follow:`n1. First do this important thing`n2. Then do that other thing"
                }
            )
            $result = Get-MaintainerGuidance -Comments $comments -Maintainers @("rjmurillo")
            $result | Should -Not -BeNullOrEmpty
            $result[0] | Should -Match "First do this"
        }

        It "Skips checkbox items" {
            $comments = @(
                @{
                    user = @{ login = "rjmurillo" }
                    body = "- [x] This is a completed checkbox item`n- This is a regular bullet point item"
                }
            )
            $result = Get-MaintainerGuidance -Comments $comments -Maintainers @("rjmurillo")
            # Should only get the regular bullet point, not the checkbox
            $result | Should -Not -Match '\[x\]'
        }

        It "Skips items that are too short" {
            $comments = @(
                @{
                    user = @{ login = "rjmurillo" }
                    body = "- Short`n- This is a longer item that should be included"
                }
            )
            $result = Get-MaintainerGuidance -Comments $comments -Maintainers @("rjmurillo")
            # Short items (< 10 chars) should be filtered out
            $result | ForEach-Object { $_.Length | Should -BeGreaterThan 10 }
        }
    }

    Context "Multiple Maintainers" {
        It "Extracts guidance from multiple maintainers" {
            $comments = @(
                @{
                    user = @{ login = "rjmurillo" }
                    body = "- First maintainer's guidance here"
                },
                @{
                    user = @{ login = "rjmurillo-bot" }
                    body = "- Second maintainer's guidance here"
                }
            )
            $result = Get-MaintainerGuidance -Comments $comments -Maintainers @("rjmurillo", "rjmurillo-bot")
            $result | Should -Not -BeNullOrEmpty
            $result.Count | Should -Be 2
        }
    }
}

Describe "Get-CodeRabbitPlan Function" {

    BeforeAll {
        $repoRoot = Join-Path $PSScriptRoot ".."
        $scriptPath = Join-Path $repoRoot ".claude" "skills" "github" "scripts" "issue" "Invoke-CopilotAssignment.ps1"
        $scriptContent = Get-Content $scriptPath -Raw

        # Extract and define the Get-CodeRabbitPlan function
        if ($scriptContent -match 'function Get-CodeRabbitPlan \{[\s\S]*?(?=\nfunction|\n#endregion)') {
            $functionDef = $Matches[0]
            Invoke-Expression $functionDef
        }

        $testPatterns = @{
            implementation_plan = "## Implementation"
            related_issues      = "🔗 Similar Issues"
            related_prs         = "🔗 Related PRs"
        }
    }

    Context "Empty Input" {
        It "Returns null for empty comments array" {
            $result = Get-CodeRabbitPlan -Comments @() -Patterns $testPatterns
            $result | Should -BeNullOrEmpty
        }

        It "Returns null when no coderabbitai comments exist" {
            $comments = @(
                @{ user = @{ login = "someuser" }; body = "Not from CodeRabbit" }
            )
            $result = Get-CodeRabbitPlan -Comments $comments -Patterns $testPatterns
            $result | Should -BeNullOrEmpty
        }
    }

    Context "Implementation Extraction" {
        It "Extracts implementation section from CodeRabbit comment" {
            $comments = @(
                @{
                    user = @{ login = "coderabbitai" }
                    body = "## Implementation`nHere is the implementation plan.`n`n## Other Section"
                }
            )
            $result = Get-CodeRabbitPlan -Comments $comments -Patterns $testPatterns
            $result | Should -Not -BeNullOrEmpty
            $result.Implementation | Should -Match "implementation plan"
        }
    }

    Context "Related Issues Extraction" {
        It "Extracts related issue references" {
            $comments = @(
                @{
                    user = @{ login = "coderabbitai" }
                    body = "🔗 Similar Issues`n- #123 Similar problem`n- #456 Related issue"
                }
            )
            $result = Get-CodeRabbitPlan -Comments $comments -Patterns $testPatterns
            $result | Should -Not -BeNullOrEmpty
            $result.RelatedIssues | Should -Contain "#123"
            $result.RelatedIssues | Should -Contain "#456"
        }
    }
}

Describe "Get-AITriageInfo Function" {

    BeforeAll {
        $repoRoot = Join-Path $PSScriptRoot ".."
        $scriptPath = Join-Path $repoRoot ".claude" "skills" "github" "scripts" "issue" "Invoke-CopilotAssignment.ps1"
        $scriptContent = Get-Content $scriptPath -Raw

        # Extract and define the Get-AITriageInfo function
        if ($scriptContent -match 'function Get-AITriageInfo \{[\s\S]*?(?=\nfunction|\n#endregion)') {
            $functionDef = $Matches[0]
            Invoke-Expression $functionDef
        }

        $testMarker = "<!-- AI-ISSUE-TRIAGE -->"
    }

    Context "Empty Input" {
        It "Returns null for empty comments array" {
            $result = Get-AITriageInfo -Comments @() -TriageMarker $testMarker
            $result | Should -BeNullOrEmpty
        }

        It "Returns null when no triage comment exists" {
            $comments = @(
                @{ user = @{ login = "someuser" }; body = "No triage marker here" }
            )
            $result = Get-AITriageInfo -Comments $comments -TriageMarker $testMarker
            $result | Should -BeNullOrEmpty
        }
    }

    Context "Priority Extraction" {
        It "Extracts priority from triage comment" {
            $comments = @(
                @{
                    user = @{ login = "github-actions" }
                    body = "<!-- AI-ISSUE-TRIAGE -->`nPriority: P1`nCategory: bug"
                }
            )
            $result = Get-AITriageInfo -Comments $comments -TriageMarker $testMarker
            $result | Should -Not -BeNullOrEmpty
            $result.Priority | Should -Be "P1"
        }

        It "Extracts category from triage comment" {
            $comments = @(
                @{
                    user = @{ login = "github-actions" }
                    body = "<!-- AI-ISSUE-TRIAGE -->`nPriority: P2`nCategory: feature"
                }
            )
            $result = Get-AITriageInfo -Comments $comments -TriageMarker $testMarker
            $result.Category | Should -Be "feature"
        }
    }
}

Describe "Find-ExistingSynthesis Function" {

    BeforeAll {
        $repoRoot = Join-Path $PSScriptRoot ".."
        $scriptPath = Join-Path $repoRoot ".claude" "skills" "github" "scripts" "issue" "Invoke-CopilotAssignment.ps1"
        $scriptContent = Get-Content $scriptPath -Raw

        # Extract and define the Find-ExistingSynthesis function
        if ($scriptContent -match 'function Find-ExistingSynthesis \{[\s\S]*?(?=\nfunction|\n#endregion)') {
            $functionDef = $Matches[0]
            Invoke-Expression $functionDef
        }

        $testMarker = "<!-- COPILOT-CONTEXT-SYNTHESIS -->"
    }

    Context "Idempotency Detection" {
        It "Returns null when no synthesis comment exists" {
            $comments = @(
                @{ id = 1; body = "Regular comment" },
                @{ id = 2; body = "Another comment" }
            )
            $result = Find-ExistingSynthesis -Comments $comments -Marker $testMarker
            $result | Should -BeNullOrEmpty
        }

        It "Finds existing synthesis comment by marker" {
            $comments = @(
                @{ id = 1; body = "Regular comment" },
                @{ id = 2; body = "<!-- COPILOT-CONTEXT-SYNTHESIS -->`n@copilot Here is context" },
                @{ id = 3; body = "Another comment" }
            )
            $result = Find-ExistingSynthesis -Comments $comments -Marker $testMarker
            $result | Should -Not -BeNullOrEmpty
            $result.id | Should -Be 2
        }

        It "Returns first match when multiple synthesis comments exist" {
            $comments = @(
                @{ id = 1; body = "<!-- COPILOT-CONTEXT-SYNTHESIS -->`nFirst synthesis" },
                @{ id = 2; body = "<!-- COPILOT-CONTEXT-SYNTHESIS -->`nSecond synthesis" }
            )
            $result = Find-ExistingSynthesis -Comments $comments -Marker $testMarker
            $result.id | Should -Be 1
        }

        It "Does not match similar but different markers" {
            $comments = @(
                @{ id = 1; body = "<!-- AI-ISSUE-TRIAGE -->`nTriage comment" }
            )
            $result = Find-ExistingSynthesis -Comments $comments -Marker $testMarker
            $result | Should -BeNullOrEmpty
        }
    }
}

Describe "New-SynthesisComment Function" {

    BeforeAll {
        $repoRoot = Join-Path $PSScriptRoot ".."
        $scriptPath = Join-Path $repoRoot ".claude" "skills" "github" "scripts" "issue" "Invoke-CopilotAssignment.ps1"
        $scriptContent = Get-Content $scriptPath -Raw

        # Extract and define the New-SynthesisComment function
        if ($scriptContent -match 'function New-SynthesisComment \{[\s\S]*?(?=\nfunction|\n#endregion)') {
            $functionDef = $Matches[0]
            Invoke-Expression $functionDef
        }

        $testMarker = "<!-- COPILOT-CONTEXT-SYNTHESIS -->"
    }

    Context "Comment Generation" {
        It "Includes the marker at the beginning" {
            $result = New-SynthesisComment -Marker $testMarker -MaintainerGuidance @() -CodeRabbitPlan $null -AITriage $null
            $result | Should -Match '^<!-- COPILOT-CONTEXT-SYNTHESIS -->'
        }

        It "Includes @copilot mention" {
            $result = New-SynthesisComment -Marker $testMarker -MaintainerGuidance @() -CodeRabbitPlan $null -AITriage $null
            $result | Should -Match '@copilot'
        }

        It "Includes timestamp footer" {
            $result = New-SynthesisComment -Marker $testMarker -MaintainerGuidance @() -CodeRabbitPlan $null -AITriage $null
            $result | Should -Match 'Generated:.*UTC'
        }

        It "Includes maintainer guidance when provided" {
            $guidance = @("First guidance item here", "Second guidance item here")
            $result = New-SynthesisComment -Marker $testMarker -MaintainerGuidance $guidance -CodeRabbitPlan $null -AITriage $null
            $result | Should -Match '## Maintainer Guidance'
            $result | Should -Match 'First guidance item'
        }

        It "Includes AI triage info when provided" {
            $triage = @{ Priority = "P1"; Category = "bug" }
            $result = New-SynthesisComment -Marker $testMarker -MaintainerGuidance @() -CodeRabbitPlan $null -AITriage $triage
            $result | Should -Match '## AI Agent Recommendations'
            $result | Should -Match 'Priority.*P1'
        }
    }
}

Describe "Get-SynthesisConfig YAML Parsing" {

    BeforeAll {
        $repoRoot = Join-Path $PSScriptRoot ".."
        $scriptPath = Join-Path $repoRoot ".claude" "skills" "github" "scripts" "issue" "Invoke-CopilotAssignment.ps1"
        $configPath = Join-Path $repoRoot ".claude" "skills" "github" "copilot-synthesis.yml"
        $scriptContent = Get-Content $scriptPath -Raw

        # Extract and define the Get-SynthesisConfig function
        if ($scriptContent -match 'function Get-SynthesisConfig \{[\s\S]*?(?=\n#endregion)') {
            $functionDef = $Matches[0]
            Invoke-Expression $functionDef
        }
    }

    Context "Marker Extraction" {
        It "Extracts synthesis marker correctly (not ai_triage marker)" {
            $result = Get-SynthesisConfig -ConfigPath $configPath
            $result.synthesis.marker | Should -Be "<!-- COPILOT-CONTEXT-SYNTHESIS -->"
        }

        It "Returns correct marker even when ai_triage marker exists" {
            $result = Get-SynthesisConfig -ConfigPath $configPath
            # The synthesis marker should NOT be the AI triage marker
            $result.synthesis.marker | Should -Not -Be "<!-- AI-ISSUE-TRIAGE -->"
        }
    }

    Context "Trusted Sources Extraction" {
        It "Extracts maintainers list" {
            $result = Get-SynthesisConfig -ConfigPath $configPath
            $result.trusted_sources.maintainers | Should -Contain "rjmurillo"
            $result.trusted_sources.maintainers | Should -Contain "rjmurillo-bot"
        }

        It "Extracts ai_agents list" {
            $result = Get-SynthesisConfig -ConfigPath $configPath
            $result.trusted_sources.ai_agents | Should -Contain "coderabbitai"
            $result.trusted_sources.ai_agents | Should -Contain "github-actions"
        }
    }

    Context "Default Config Fallback" {
        It "Returns default config when file not found" {
            $result = Get-SynthesisConfig -ConfigPath "/nonexistent/path.yml"
            $result | Should -Not -BeNullOrEmpty
            $result.synthesis.marker | Should -Be "<!-- COPILOT-CONTEXT-SYNTHESIS -->"
        }
    }
}

#endregion

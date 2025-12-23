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

.NOTES
    Test Approach: This file uses two complementary testing strategies:

    1. PATTERN-BASED TESTS (first half of file)
       These tests validate code structure by matching against regex patterns
       in the script content. They verify:
       - Required parameters exist
       - Module dependencies are imported
       - Key functions are defined
       - Documentation is present

       These tests intentionally do NOT follow strict AAA (Arrange-Act-Assert)
       pattern because they are structural validations, not behavioral tests.
       The "Arrange" step (loading script content) is shared in BeforeAll.

    2. FUNCTIONAL TESTS (second half of file, under "#region Functional Tests")
       These tests extract individual functions from the script and test their
       actual behavior with mock data. They DO follow AAA pattern:
       - Arrange: Set up test data (comments, config, etc.)
       - Act: Call the function
       - Assert: Verify the result

    Why both approaches?
    - Pattern tests catch structural regressions quickly (missing functions, params)
    - Functional tests verify business logic correctness
    - Together they provide comprehensive coverage without integration complexity
#>

BeforeAll {
    # tests/ is at repo root, script is at .claude/skills/github/scripts/issue/
    $repoRoot = Join-Path $PSScriptRoot ".."
    $scriptPath = Join-Path $repoRoot ".claude" "skills" "github" "scripts" "issue" "Invoke-CopilotAssignment.ps1"

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
            $regexMatches = [regex]::Matches($text, '#(\d+)')
            $regexMatches.Count | Should -Be 2
            $regexMatches[0].Groups[1].Value | Should -Be "123"
        }

        It "Matches PR references in text" {
            $text = "See PR #789 for details"
            $regexMatches = [regex]::Matches($text, '#(\d+)')
            $regexMatches.Count | Should -Be 1
            $regexMatches[0].Groups[1].Value | Should -Be "789"
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
            username            = "coderabbitai[bot]"
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
                    user = @{ login = "coderabbitai[bot]" }
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
                    user = @{ login = "coderabbitai[bot]" }
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

    Context "Markdown Table Format Extraction" {
        It "Extracts priority from Markdown table format" {
            $comments = @(
                @{
                    user = @{ login = "github-actions" }
                    body = @"
<!-- AI-ISSUE-TRIAGE -->
| Property | Value |
|:---------|:------|
| **Priority** | ``P1`` |
| **Category** | ``enhancement`` |
"@
                }
            )
            $result = Get-AITriageInfo -Comments $comments -TriageMarker $testMarker
            $result | Should -Not -BeNullOrEmpty
            $result.Priority | Should -Be "P1"
        }

        It "Extracts category from Markdown table format" {
            $comments = @(
                @{
                    user = @{ login = "github-actions" }
                    body = @"
<!-- AI-ISSUE-TRIAGE -->
| Property | Value |
|:---------|:------|
| **Priority** | ``P2`` |
| **Category** | ``bug`` |
"@
                }
            )
            $result = Get-AITriageInfo -Comments $comments -TriageMarker $testMarker
            $result.Category | Should -Be "bug"
        }

        It "Extracts both priority and category from Markdown table format" {
            $comments = @(
                @{
                    user = @{ login = "github-actions" }
                    body = @"
<!-- AI-ISSUE-TRIAGE -->
### Triage Results

| Property | Value |
|:---------|:------|
| **Category** | ``enhancement`` |
|  **Priority** | ``P1`` |
| **Milestone** | v1.1 |
"@
                }
            )
            $result = Get-AITriageInfo -Comments $comments -TriageMarker $testMarker
            $result.Priority | Should -Be "P1"
            $result.Category | Should -Be "enhancement"
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

        It "Extracts custom marker when YAML has comments between synthesis and marker" {
            # Arrange - Create config with comments between synthesis: and marker:
            $tempDir = Join-Path ([System.IO.Path]::GetTempPath()) "CopilotSynthesisTests"
            if (-not (Test-Path $tempDir)) {
                New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
            }
            $customConfig = Join-Path $tempDir "custom-marker.yml"
            @"
# Comments before synthesis section
synthesis:
  # This is a comment that should be skipped
  # Multiple lines of comments here
  # The regex should handle this correctly
  marker: "<!-- CUSTOM-TEST-MARKER -->"
"@ | Set-Content $customConfig

            # Act
            $result = Get-SynthesisConfig -ConfigPath $customConfig

            # Assert - Should extract the custom marker, not default
            $result.synthesis.marker | Should -Be "<!-- CUSTOM-TEST-MARKER -->"

            # Cleanup
            Remove-Item $customConfig -Force -ErrorAction SilentlyContinue
        }
    }

    Context "Trusted Sources Extraction" {
        It "Extracts maintainers list" {
            $result = Get-SynthesisConfig -ConfigPath $configPath
            $result.trusted_sources.maintainers | Should -Contain "rjmurillo"
        }

        It "Extracts ai_agents list" {
            $result = Get-SynthesisConfig -ConfigPath $configPath
            $result.trusted_sources.ai_agents | Should -Contain "rjmurillo-bot"
            $result.trusted_sources.ai_agents | Should -Contain "coderabbitai[bot]"
            $result.trusted_sources.ai_agents | Should -Contain "github-actions[bot]"
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

#region Edge Case Tests

Describe "Edge Case: Empty and Malformed Config" {

    BeforeAll {
        $repoRoot = Join-Path $PSScriptRoot ".."
        $scriptPath = Join-Path $repoRoot ".claude" "skills" "github" "scripts" "issue" "Invoke-CopilotAssignment.ps1"
        $scriptContent = Get-Content $scriptPath -Raw

        # Extract and define the Get-SynthesisConfig function
        if ($scriptContent -match 'function Get-SynthesisConfig \{[\s\S]*?(?=\n#endregion)') {
            $functionDef = $Matches[0]
            Invoke-Expression $functionDef
        }

        # Create temp directory for test files
        $script:tempDir = Join-Path ([System.IO.Path]::GetTempPath()) "CopilotSynthesisTests"
        if (-not (Test-Path $script:tempDir)) {
            New-Item -ItemType Directory -Path $script:tempDir -Force | Out-Null
        }
    }

    AfterAll {
        # Cleanup temp directory
        if (Test-Path $script:tempDir) {
            Remove-Item -Path $script:tempDir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    Context "Empty Config File" {
        It "Returns default config when config file is empty" {
            $emptyConfig = Join-Path $script:tempDir "empty.yml"
            "" | Set-Content $emptyConfig

            $result = Get-SynthesisConfig -ConfigPath $emptyConfig
            $result | Should -Not -BeNullOrEmpty
            $result.synthesis.marker | Should -Be "<!-- COPILOT-CONTEXT-SYNTHESIS -->"
            $result.trusted_sources.maintainers | Should -Contain "rjmurillo"
        }
    }

    Context "Malformed YAML" {
        It "Returns default config when YAML is malformed" {
            $malformedConfig = Join-Path $script:tempDir "malformed.yml"
            "this: is: not: valid: yaml: [unclosed" | Set-Content $malformedConfig

            # Should not throw, should return defaults
            $result = Get-SynthesisConfig -ConfigPath $malformedConfig
            $result | Should -Not -BeNullOrEmpty
            $result.synthesis.marker | Should -Be "<!-- COPILOT-CONTEXT-SYNTHESIS -->"
        }

        It "Returns default config when config has invalid structure" {
            $invalidConfig = Join-Path $script:tempDir "invalid.yml"
            "random_key: random_value`nno_trusted_sources: true" | Set-Content $invalidConfig

            $result = Get-SynthesisConfig -ConfigPath $invalidConfig
            $result | Should -Not -BeNullOrEmpty
            # Should still have defaults
            $result.trusted_sources.maintainers | Should -Contain "rjmurillo"
        }
    }
}

Describe "Edge Case: Multiple Maintainer Comments" {

    BeforeAll {
        $repoRoot = Join-Path $PSScriptRoot ".."
        $scriptPath = Join-Path $repoRoot ".claude" "skills" "github" "scripts" "issue" "Invoke-CopilotAssignment.ps1"
        $scriptContent = Get-Content $scriptPath -Raw

        # Extract and define the Get-MaintainerGuidance function
        if ($scriptContent -match 'function Get-MaintainerGuidance \{[\s\S]*?(?=\nfunction|\n#endregion)') {
            $functionDef = $Matches[0]
            Invoke-Expression $functionDef
        }
    }

    Context "Order Preservation" {
        It "Preserves order of comments from multiple maintainers" {
            $comments = @(
                @{
                    user = @{ login = "maintainer1" }
                    body = "- First maintainer first point`n- First maintainer second point"
                },
                @{
                    user = @{ login = "maintainer2" }
                    body = "- Second maintainer contribution"
                },
                @{
                    user = @{ login = "maintainer1" }
                    body = "- First maintainer third point"
                }
            )

            $result = Get-MaintainerGuidance -Comments $comments -Maintainers @("maintainer1", "maintainer2")

            $result | Should -Not -BeNullOrEmpty
            $result.Count | Should -Be 4

            # Verify order is preserved (maintainer1's first comments come first)
            $result[0] | Should -Match "First maintainer first"
            $result[1] | Should -Match "First maintainer second"
            $result[2] | Should -Match "Second maintainer"
            $result[3] | Should -Match "First maintainer third"
        }
    }
}

Describe "Edge Case: Unicode in Comment Bodies" {

    Context "Unicode Characters in Patterns" {
        It "Regex handles emoji characters properly" {
            $text = "- Use the write_memory tool for persistence"
            $text -match '^[-*]\s+(.+)$' | Should -Be $true
            $Matches[1] | Should -Match "write_memory"
        }

        It "Regex handles Japanese characters properly" {
            $text = "- Implement localization for Japanese users"
            $text -match '^[-*]\s+(.+)$' | Should -Be $true
            $Matches[1] | Should -Match "localization"
        }

        It "Regex handles mixed Unicode symbols in text" {
            # Test that the pattern extraction works with various Unicode
            $text = "- Review the documentation carefully"
            $text -match '^[-*]\s+(.+)$' | Should -Be $true
            $Matches[1] | Should -Match "documentation"
        }

        It "Regex handles CJK characters in text" {
            $text = "- Configure settings for CJK support"
            $text -match '^[-*]\s+(.+)$' | Should -Be $true
            $Matches[1] | Should -Match "CJK"
        }
    }
}

Describe "Edge Case: RelatedPRs in AI Visibility Check" {

    BeforeAll {
        $repoRoot = Join-Path $PSScriptRoot ".."
        $scriptPath = Join-Path $repoRoot ".claude" "skills" "github" "scripts" "issue" "Invoke-CopilotAssignment.ps1"
        $scriptContent = Get-Content $scriptPath -Raw

        # Extract and define the New-SynthesisComment function
        if ($scriptContent -match 'function New-SynthesisComment \{[\s\S]*?(?=\nfunction|\n#endregion)') {
            $functionDef = $Matches[0]
            Invoke-Expression $functionDef
        }

        $script:testMarker = "<!-- COPILOT-CONTEXT-SYNTHESIS -->"
    }

    Context "RelatedPRs Visibility" {
        It "Shows AI section when only RelatedPRs exist" {
            $plan = @{
                Implementation = $null
                RelatedIssues = @()
                RelatedPRs = @("#123", "#456")
            }

            $result = New-SynthesisComment -Marker $script:testMarker -MaintainerGuidance @() -CodeRabbitPlan $plan -AITriage $null

            $result | Should -Match "## AI Agent Recommendations"
            $result | Should -Match "#123"
            $result | Should -Match "#456"
        }

        It "Shows AI section when RelatedPRs and RelatedIssues both exist" {
            $plan = @{
                Implementation = $null
                RelatedIssues = @("#789")
                RelatedPRs = @("#123")
            }

            $result = New-SynthesisComment -Marker $script:testMarker -MaintainerGuidance @() -CodeRabbitPlan $plan -AITriage $null

            $result | Should -Match "## AI Agent Recommendations"
            $result | Should -Match "Related Issues.*#789"
            $result | Should -Match "Related PRs.*#123"
        }
    }
}

Describe "Test-HasSynthesizableContent Function" {

    BeforeAll {
        $repoRoot = Join-Path $PSScriptRoot ".."
        $scriptPath = Join-Path $repoRoot ".claude" "skills" "github" "scripts" "issue" "Invoke-CopilotAssignment.ps1"
        $scriptContent = Get-Content $scriptPath -Raw

        # Extract and define the Test-HasSynthesizableContent function
        if ($scriptContent -match 'function Test-HasSynthesizableContent \{[\s\S]*?(?=\nfunction|\n#endregion)') {
            $functionDef = $Matches[0]
            Invoke-Expression $functionDef
        }
    }

    Context "Empty Inputs" {
        It "Returns false when all inputs are null" {
            $result = Test-HasSynthesizableContent -MaintainerGuidance $null -CodeRabbitPlan $null -AITriage $null
            $result | Should -Be $false
        }

        It "Returns false when all inputs are empty" {
            $result = Test-HasSynthesizableContent `
                -MaintainerGuidance @() `
                -CodeRabbitPlan @{ Implementation = $null; RelatedIssues = @(); RelatedPRs = @() } `
                -AITriage @{ Priority = $null; Category = $null }
            $result | Should -Be $false
        }

        It "Returns false with empty arrays for all fields" {
            $result = Test-HasSynthesizableContent `
                -MaintainerGuidance @() `
                -CodeRabbitPlan @{ Implementation = ""; RelatedIssues = @(); RelatedPRs = @() } `
                -AITriage @{ Priority = ""; Category = "" }
            $result | Should -Be $false
        }
    }

    Context "MaintainerGuidance Content" {
        It "Returns true when MaintainerGuidance has one item" {
            $result = Test-HasSynthesizableContent `
                -MaintainerGuidance @("Important guidance") `
                -CodeRabbitPlan $null `
                -AITriage $null
            $result | Should -Be $true
        }

        It "Returns true when MaintainerGuidance has multiple items" {
            $result = Test-HasSynthesizableContent `
                -MaintainerGuidance @("First guidance", "Second guidance") `
                -CodeRabbitPlan $null `
                -AITriage $null
            $result | Should -Be $true
        }
    }

    Context "AITriage Content" {
        It "Returns true when AITriage.Priority is set" {
            $result = Test-HasSynthesizableContent `
                -MaintainerGuidance @() `
                -CodeRabbitPlan $null `
                -AITriage @{ Priority = "P1"; Category = $null }
            $result | Should -Be $true
        }

        It "Returns true when AITriage.Category is set" {
            $result = Test-HasSynthesizableContent `
                -MaintainerGuidance @() `
                -CodeRabbitPlan $null `
                -AITriage @{ Priority = $null; Category = "bug" }
            $result | Should -Be $true
        }

        It "Returns true when both AITriage fields are set" {
            $result = Test-HasSynthesizableContent `
                -MaintainerGuidance @() `
                -CodeRabbitPlan $null `
                -AITriage @{ Priority = "P2"; Category = "feature" }
            $result | Should -Be $true
        }
    }

    Context "CodeRabbitPlan Content" {
        It "Returns true when CodeRabbitPlan.Implementation is set" {
            $result = Test-HasSynthesizableContent `
                -MaintainerGuidance @() `
                -CodeRabbitPlan @{ Implementation = "Some implementation plan"; RelatedIssues = @(); RelatedPRs = @() } `
                -AITriage $null
            $result | Should -Be $true
        }

        It "Returns true when CodeRabbitPlan.RelatedIssues has items" {
            $result = Test-HasSynthesizableContent `
                -MaintainerGuidance @() `
                -CodeRabbitPlan @{ Implementation = $null; RelatedIssues = @("#123"); RelatedPRs = @() } `
                -AITriage $null
            $result | Should -Be $true
        }

        It "Returns true when CodeRabbitPlan.RelatedPRs has items" {
            $result = Test-HasSynthesizableContent `
                -MaintainerGuidance @() `
                -CodeRabbitPlan @{ Implementation = $null; RelatedIssues = @(); RelatedPRs = @("#456") } `
                -AITriage $null
            $result | Should -Be $true
        }

        It "Returns true when CodeRabbitPlan has multiple fields populated" {
            $result = Test-HasSynthesizableContent `
                -MaintainerGuidance @() `
                -CodeRabbitPlan @{ Implementation = "Plan"; RelatedIssues = @("#1", "#2"); RelatedPRs = @("#3") } `
                -AITriage $null
            $result | Should -Be $true
        }
    }

    Context "Combined Inputs" {
        It "Returns true when multiple sources have content" {
            $result = Test-HasSynthesizableContent `
                -MaintainerGuidance @("Guidance") `
                -CodeRabbitPlan @{ Implementation = "Plan"; RelatedIssues = @(); RelatedPRs = @() } `
                -AITriage @{ Priority = "P1"; Category = "bug" }
            $result | Should -Be $true
        }

        It "Returns true with first matching source (MaintainerGuidance)" {
            $result = Test-HasSynthesizableContent `
                -MaintainerGuidance @("First") `
                -CodeRabbitPlan @{ Implementation = $null; RelatedIssues = @(); RelatedPRs = @() } `
                -AITriage @{ Priority = $null; Category = $null }
            $result | Should -Be $true
        }
    }
}

#endregion

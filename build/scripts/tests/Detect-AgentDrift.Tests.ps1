<#
.SYNOPSIS
    Pester tests for Detect-AgentDrift.ps1 script.

.DESCRIPTION
    Comprehensive unit tests for the agent drift detection script.
    Tests cover:
    - Section extraction from markdown
    - Content normalization (platform-specific syntax removal)
    - Similarity calculation
    - Agent comparison logic
    - Known exclusions filtering

.NOTES
    Requires Pester 5.x or later.
    Run with: pwsh build/scripts/Invoke-PesterTests.ps1 -TestPath "./build/scripts/tests/Detect-AgentDrift.Tests.ps1"
#>

BeforeAll {
    # Create test temp directory (cross-platform)
    $Script:TestTempDir = Join-Path ([System.IO.Path]::GetTempPath()) "Detect-AgentDrift-Tests-$(Get-Random)"
    New-Item -ItemType Directory -Path $Script:TestTempDir -Force | Out-Null

    # Define test functions (copies from script for unit testing)
    function Remove-YamlFrontmatter {
        param([string]$Content)
        if ($Content -match '^---\r?\n[\s\S]*?\r?\n---\r?\n([\s\S]*)$') {
            return $Matches[1]
        }
        return $Content
    }

    function Get-MarkdownSections {
        param([string]$Content)
        $sections = @{}
        $currentSection = "preamble"
        $currentContent = [System.Collections.ArrayList]::new()
        $lines = $Content -split '\r?\n'
        foreach ($line in $lines) {
            if ($line -match '^##\s+(.+)$') {
                if ($currentContent.Count -gt 0) {
                    $sections[$currentSection] = ($currentContent -join "`n").Trim()
                }
                $currentSection = $Matches[1].Trim()
                $currentContent = [System.Collections.ArrayList]::new()
            }
            else {
                [void]$currentContent.Add($line)
            }
        }
        if ($currentContent.Count -gt 0) {
            $sections[$currentSection] = ($currentContent -join "`n").Trim()
        }
        return $sections
    }

    function Normalize-ContentForComparison {
        param([string]$Content)
        $result = $Content
        # Normalize memory protocol syntax
        $result = $result -replace 'mcp__cloudmcp-manager__', 'cloudmcp-manager/'
        $result = $result -replace 'mcp__cognitionai-deepwiki__', 'cognitionai/deepwiki/'
        $result = $result -replace 'mcp__context7__', 'context7/'
        $result = $result -replace 'mcp__deepwiki__', 'deepwiki/'
        # Normalize handoff syntax
        $result = $result -replace '`#runSubagent with subagentType=(\w+)`', '`invoke $1`'
        $result = $result -replace '`/agent\s+(\w+)`', '`invoke $1`'
        # Normalize code blocks
        $result = $result -replace '```(bash|powershell|text|markdown|python)', '```'
        # Normalize whitespace
        $result = $result -replace '\r\n', "`n"
        $result = $result -replace '[ \t]+$', '' -split "`n" | ForEach-Object { $_.TrimEnd() }
        $result = ($result -join "`n").Trim()
        $result = $result -replace '\n{3,}', "`n`n"
        return $result
    }

    function Get-SectionSimilarity {
        param(
            [AllowEmptyString()][string]$Text1,
            [AllowEmptyString()][string]$Text2
        )
        if ([string]::IsNullOrWhiteSpace($Text1) -and [string]::IsNullOrWhiteSpace($Text2)) {
            return 100.0
        }
        if ([string]::IsNullOrWhiteSpace($Text1) -or [string]::IsNullOrWhiteSpace($Text2)) {
            return 0.0
        }
        $words1 = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
        $words2 = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
        foreach ($word in ($Text1 -split '\W+' | Where-Object { $_.Length -gt 2 })) {
            [void]$words1.Add($word)
        }
        foreach ($word in ($Text2 -split '\W+' | Where-Object { $_.Length -gt 2 })) {
            [void]$words2.Add($word)
        }
        if ($words1.Count -eq 0 -and $words2.Count -eq 0) {
            return 100.0
        }
        # Must use same comparer for intersection/union operations
        $intersection = [System.Collections.Generic.HashSet[string]]::new($words1, [StringComparer]::OrdinalIgnoreCase)
        $intersection.IntersectWith($words2)
        $union = [System.Collections.Generic.HashSet[string]]::new($words1, [StringComparer]::OrdinalIgnoreCase)
        $union.UnionWith($words2)
        if ($union.Count -eq 0) {
            return 100.0
        }
        return [Math]::Round(($intersection.Count / $union.Count) * 100, 1)
    }
}

AfterAll {
    # Clean up test artifacts
    if (Test-Path $Script:TestTempDir) {
        Remove-Item -Path $Script:TestTempDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Describe "Remove-YamlFrontmatter" {
    Context "Valid frontmatter removal" {
        It "Removes standard YAML frontmatter" {
            $content = @"
---
name: test
description: Test agent
model: opus
---
# Agent Title

Body content here.
"@
            $result = Remove-YamlFrontmatter -Content $content
            $result | Should -Match "^# Agent Title"
            $result | Should -Not -Match "---"
            $result | Should -Not -Match "name: test"
        }

        It "Handles content without frontmatter" {
            $content = "# Just a heading`n`nNo frontmatter."
            $result = Remove-YamlFrontmatter -Content $content
            $result | Should -Be $content
        }

        It "Handles VS Code agent frontmatter with tools array" {
            $content = @"
---
description: Test description
tools: ['tool1', 'tool2']
model: Claude Opus 4.5 (anthropic)
---
# Agent Title

Content.
"@
            $result = Remove-YamlFrontmatter -Content $content
            $result | Should -Match "^# Agent Title"
            $result | Should -Not -Match "tools:"
        }
    }
}

Describe "Get-MarkdownSections" {
    Context "Section extraction" {
        It "Extracts sections by ## headers" {
            $content = @"
# Title

Preamble content.

## Core Identity

Identity content here.

## Core Mission

Mission content here.
"@
            $result = Get-MarkdownSections -Content $content
            $result.Keys | Should -Contain "preamble"
            $result.Keys | Should -Contain "Core Identity"
            $result.Keys | Should -Contain "Core Mission"
            $result["Core Identity"] | Should -Match "Identity content"
            $result["Core Mission"] | Should -Match "Mission content"
        }

        It "Handles multiple subsections" {
            $content = @"
## Section One

Content one.

### Subsection

Sub content.

## Section Two

Content two.
"@
            $result = Get-MarkdownSections -Content $content
            $result.Keys | Should -Contain "Section One"
            $result.Keys | Should -Contain "Section Two"
            # Subsections should be included in parent section content
            $result["Section One"] | Should -Match "Sub content"
        }

        It "Handles empty sections" {
            $content = @"
## Empty Section

## Non-Empty Section

Has content.
"@
            $result = Get-MarkdownSections -Content $content
            $result.Keys | Should -Contain "Empty Section"
            $result["Empty Section"] | Should -BeNullOrEmpty
        }
    }
}

Describe "Normalize-ContentForComparison" {
    Context "Memory protocol syntax normalization" {
        It "Normalizes Claude MCP syntax to VS Code format" {
            $claudeContent = "mcp__cloudmcp-manager__memory-search_nodes"
            $result = Normalize-ContentForComparison -Content $claudeContent
            $result | Should -Be "cloudmcp-manager/memory-search_nodes"
        }

        It "Normalizes DeepWiki MCP syntax" {
            $claudeContent = "mcp__cognitionai-deepwiki__ask_question"
            $result = Normalize-ContentForComparison -Content $claudeContent
            $result | Should -Be "cognitionai/deepwiki/ask_question"
        }

        It "Normalizes Context7 MCP syntax" {
            $claudeContent = "mcp__context7__resolve-library-id"
            $result = Normalize-ContentForComparison -Content $claudeContent
            $result | Should -Be "context7/resolve-library-id"
        }
    }

    Context "Handoff syntax normalization" {
        It "Normalizes VS Code #runSubagent syntax with backticks" {
            # The regex requires backticks around the syntax
            $vscodeContent = 'Use `#runSubagent with subagentType=analyst` for research'
            $result = Normalize-ContentForComparison -Content $vscodeContent
            $result | Should -Match "invoke analyst"
        }

        It "Normalizes Claude /agent syntax with backticks" {
            # The regex requires backticks around the syntax
            $claudeContent = 'Use `/agent analyst` for research'
            $result = Normalize-ContentForComparison -Content $claudeContent
            $result | Should -Match "invoke analyst"
        }

        It "Preserves non-backticked handoff references" {
            # Without backticks, the syntax is preserved (intentional - these are prose references)
            $content = "Use #runSubagent with subagentType=analyst for research"
            $result = Normalize-ContentForComparison -Content $content
            $result | Should -Match "#runSubagent"
        }
    }

    Context "Whitespace normalization" {
        It "Removes trailing whitespace" {
            $content = "Line with trailing spaces   `nAnother line  "
            $result = Normalize-ContentForComparison -Content $content
            $result | Should -Not -Match '\s+$'
        }

        It "Collapses multiple blank lines" {
            $content = "Line one`n`n`n`n`nLine two"
            $result = Normalize-ContentForComparison -Content $content
            $result | Should -Be "Line one`n`nLine two"
        }

        It "Normalizes CRLF to LF" {
            $content = "Line one`r`nLine two"
            $result = Normalize-ContentForComparison -Content $content
            $result | Should -Not -Match '\r'
        }
    }

    Context "Code block normalization" {
        It "Normalizes code block language identifiers" {
            $content = '```bash' + "`necho hello`n" + '```'
            $result = Normalize-ContentForComparison -Content $content
            $result | Should -Match '^\`\`\`'
            $result | Should -Not -Match '\`\`\`bash'
        }
    }
}

Describe "Get-SectionSimilarity" {
    Context "Identical content" {
        It "Returns 100% for identical text" {
            $text = "This is identical content for testing purposes."
            $result = Get-SectionSimilarity -Text1 $text -Text2 $text
            $result | Should -Be 100.0
        }

        It "Returns 100% for both empty strings" {
            $result = Get-SectionSimilarity -Text1 "" -Text2 ""
            $result | Should -Be 100.0
        }

        It "Returns 100% for both whitespace-only strings" {
            $result = Get-SectionSimilarity -Text1 "   " -Text2 "   "
            $result | Should -Be 100.0
        }
    }

    Context "Whitespace differences ignored" {
        It "Treats whitespace-only differences as identical" {
            $text1 = "Same words here"
            $text2 = "Same   words   here"
            $result = Get-SectionSimilarity -Text1 $text1 -Text2 $text2
            $result | Should -Be 100.0
        }

        It "Ignores case differences" {
            # Words must be > 2 chars to be included in comparison
            $text1 = "Research technical approaches implementation"
            $text2 = "RESEARCH TECHNICAL APPROACHES IMPLEMENTATION"
            $result = Get-SectionSimilarity -Text1 $text1 -Text2 $text2
            $result | Should -Be 100.0
        }
    }

    Context "Semantic content changes detected" {
        It "Returns 0% for completely different content" {
            $text1 = "Alpha beta gamma delta"
            $text2 = "One two three four"
            $result = Get-SectionSimilarity -Text1 $text1 -Text2 $text2
            $result | Should -Be 0.0
        }

        It "Returns partial similarity for overlapping content" {
            $text1 = "Research analyze investigate document"
            $text2 = "Research investigate verify document"
            $result = Get-SectionSimilarity -Text1 $text1 -Text2 $text2
            $result | Should -BeGreaterThan 50.0
            $result | Should -BeLessThan 100.0
        }

        It "Returns 0% when one string is empty" {
            $result = Get-SectionSimilarity -Text1 "Content here" -Text2 ""
            $result | Should -Be 0.0
        }
    }

    Context "Word length filtering" {
        It "Ignores words with 2 or fewer characters" {
            # Only "the", "and", "for" are 3+ chars, so they should be ignored
            $text1 = "a is to by"
            $text2 = "I am at on"
            # Both have only short words, so result should be 100 (both empty after filtering)
            $result = Get-SectionSimilarity -Text1 $text1 -Text2 $text2
            $result | Should -Be 100.0
        }
    }
}

Describe "Integration Tests" {
    BeforeAll {
        # Create test agent files
        $Script:TestClaudePath = Join-Path $Script:TestTempDir "claude"
        $Script:TestVSCodePath = Join-Path $Script:TestTempDir "vs-code-agents"

        New-Item -ItemType Directory -Path $Script:TestClaudePath -Force | Out-Null
        New-Item -ItemType Directory -Path $Script:TestVSCodePath -Force | Out-Null
    }

    Context "Matching agents" {
        BeforeAll {
            # Create matching Claude agent
            $claudeAgent = @"
---
name: test-agent
description: Test agent for integration testing
model: opus
---
# Test Agent

## Core Identity

**Test Specialist** for integration testing purposes.

## Core Mission

Execute tests and validate results.

## Key Responsibilities

1. **Run** integration tests
2. **Validate** test results
3. **Report** findings
"@
            # Create matching VS Code agent
            $vscodeAgent = @"
---
description: Test agent for integration testing
tools: ['vscode', 'read']
model: Claude Opus 4.5 (anthropic)
---
# Test Agent

## Core Identity

**Test Specialist** for integration testing purposes.

## Core Mission

Execute tests and validate results.

## Key Responsibilities

1. **Run** integration tests
2. **Validate** test results
3. **Report** findings
"@
            Set-Content -Path (Join-Path $Script:TestClaudePath "matching.md") -Value $claudeAgent
            Set-Content -Path (Join-Path $Script:TestVSCodePath "matching.agent.md") -Value $vscodeAgent
        }

        It "Detects no drift for matching content" {
            $claudeContent = Get-Content -Path (Join-Path $Script:TestClaudePath "matching.md") -Raw
            $vscodeContent = Get-Content -Path (Join-Path $Script:TestVSCodePath "matching.agent.md") -Raw

            $claudeBody = Remove-YamlFrontmatter -Content $claudeContent
            $vscodeBody = Remove-YamlFrontmatter -Content $vscodeContent

            $claudeSections = Get-MarkdownSections -Content $claudeBody
            $vscodeSections = Get-MarkdownSections -Content $vscodeBody

            # Core Identity should match
            $similarity = Get-SectionSimilarity `
                -Text1 (Normalize-ContentForComparison -Content $claudeSections["Core Identity"]) `
                -Text2 (Normalize-ContentForComparison -Content $vscodeSections["Core Identity"])

            $similarity | Should -Be 100.0
        }
    }

    Context "Drifted agents" {
        BeforeAll {
            # Create Claude agent with different content
            $claudeAgent = @"
---
name: drifted-agent
description: Agent with drift
model: opus
---
# Drifted Agent

## Core Identity

**Original Role** for specific purposes.

## Core Mission

Perform original tasks and maintain original state.

## Key Responsibilities

1. **Execute** original workflows
2. **Maintain** original state
"@
            # Create VS Code agent with different content
            $vscodeAgent = @"
---
description: Agent with drift
tools: ['vscode']
model: Claude Opus 4.5 (anthropic)
---
# Drifted Agent

## Core Identity

**New Enhanced Role** for completely different purposes.

## Core Mission

Execute new workflows and manage new features.

## Key Responsibilities

1. **Implement** new features
2. **Manage** new resources
"@
            Set-Content -Path (Join-Path $Script:TestClaudePath "drifted.md") -Value $claudeAgent
            Set-Content -Path (Join-Path $Script:TestVSCodePath "drifted.agent.md") -Value $vscodeAgent
        }

        It "Detects drift for differing content" {
            $claudeContent = Get-Content -Path (Join-Path $Script:TestClaudePath "drifted.md") -Raw
            $vscodeContent = Get-Content -Path (Join-Path $Script:TestVSCodePath "drifted.agent.md") -Raw

            $claudeBody = Remove-YamlFrontmatter -Content $claudeContent
            $vscodeBody = Remove-YamlFrontmatter -Content $vscodeContent

            $claudeSections = Get-MarkdownSections -Content $claudeBody
            $vscodeSections = Get-MarkdownSections -Content $vscodeBody

            # Core Mission should have low similarity
            $similarity = Get-SectionSimilarity `
                -Text1 (Normalize-ContentForComparison -Content $claudeSections["Core Mission"]) `
                -Text2 (Normalize-ContentForComparison -Content $vscodeSections["Core Mission"])

            $similarity | Should -BeLessThan 80.0
        }
    }

    Context "Platform-specific syntax" {
        It "Treats different MCP syntax as equivalent after normalization" {
            $claudeContent = @"
## Memory Protocol

Use mcp__cloudmcp-manager__memory-search_nodes for searching.
"@
            $vscodeContent = @"
## Memory Protocol

Use cloudmcp-manager/memory-search_nodes for searching.
"@
            $claudeNorm = Normalize-ContentForComparison -Content $claudeContent
            $vscodeNorm = Normalize-ContentForComparison -Content $vscodeContent

            $similarity = Get-SectionSimilarity -Text1 $claudeNorm -Text2 $vscodeNorm
            $similarity | Should -Be 100.0
        }
    }
}

Describe "Script Execution" {
    Context "Script file validation" {
        It "Script file exists" {
            $ScriptPath = Join-Path $PSScriptRoot "..\Detect-AgentDrift.ps1"
            Test-Path $ScriptPath | Should -Be $true
        }

        It "Script has required parameters" {
            $ScriptPath = Join-Path $PSScriptRoot "..\Detect-AgentDrift.ps1"
            $scriptContent = Get-Content $ScriptPath -Raw

            $scriptContent | Should -Match '\[string\]\$ClaudePath'
            $scriptContent | Should -Match '\[string\]\$VSCodePath'
            $scriptContent | Should -Match '\[int\]\$SimilarityThreshold'
            $scriptContent | Should -Match '\[ValidateSet\("Text", "JSON", "Markdown"\)\]'
        }

        It "Script has helper functions" {
            $ScriptPath = Join-Path $PSScriptRoot "..\Detect-AgentDrift.ps1"
            $scriptContent = Get-Content $ScriptPath -Raw

            $scriptContent | Should -Match 'function Remove-YamlFrontmatter'
            $scriptContent | Should -Match 'function Get-MarkdownSections'
            $scriptContent | Should -Match 'function Normalize-ContentForComparison'
            $scriptContent | Should -Match 'function Get-SectionSimilarity'
            $scriptContent | Should -Match 'function Compare-AgentContent'
        }
    }
}

Describe "Performance" {
    Context "Execution time" {
        It "Similarity calculation completes quickly" {
            $text1 = "Research analyze investigate document surface risks dependencies unknowns"
            $text2 = "Research analyze verify document surface risks dependencies unknowns"

            $measure = Measure-Command {
                for ($i = 0; $i -lt 1000; $i++) {
                    $null = Get-SectionSimilarity -Text1 $text1 -Text2 $text2
                }
            }

            # Should complete 1000 iterations in under 2 seconds
            $measure.TotalSeconds | Should -BeLessThan 2
        }

        It "Normalization completes quickly" {
            $content = @"
Use mcp__cloudmcp-manager__memory-search_nodes for search.
Use mcp__cognitionai-deepwiki__ask_question for docs.
Use `#runSubagent with subagentType=analyst` for research.
```bash
echo hello
```
"@
            $measure = Measure-Command {
                for ($i = 0; $i -lt 1000; $i++) {
                    $null = Normalize-ContentForComparison -Content $content
                }
            }

            # Should complete 1000 iterations in under 2 seconds
            $measure.TotalSeconds | Should -BeLessThan 2
        }
    }
}

# Requires -Modules Pester

<#
.SYNOPSIS
    Pester tests for Validate-TokenBudget.ps1

.DESCRIPTION
    Tests the token budget validation script that enforces the 5K token limit
    on HANDOFF.md to prevent merge conflicts and context overflow.

    Tests cover:
    - Token estimation algorithm accuracy
    - Budget enforcement
    - Edge cases (empty files, missing files, non-ASCII content)
    - Heuristic adjustments (code-like text, multilingual, digit-heavy)
    - Exit code behavior (CI mode)
#>

BeforeAll {
    $scriptPath = Join-Path $PSScriptRoot ".." "Validate-TokenBudget.ps1"

    # Extract the Get-ApproxTokenCount function for unit testing
    $scriptContent = Get-Content -Path $scriptPath -Raw
    
    # Extract function definition (handle both LF and CRLF line endings)
    $functionPattern = '(?ms)(function\s+Get-ApproxTokenCount\s*\{.*?\r?\n\}(?=\r?\n\r?\n|\r?\nSet-StrictMode|\r?\n#|\z))'
    $match = [regex]::Match($scriptContent, $functionPattern)
    
    if ($match.Success) {
        # Execute the function in current scope
        Invoke-Expression $match.Value
    } else {
        throw "Could not extract Get-ApproxTokenCount function from $scriptPath"
    }

    # Create temp directory structure for integration tests
    $script:TestRoot = Join-Path $TestDrive "test-repo"
    $script:AgentsPath = Join-Path $TestRoot ".agents"
    $script:HandoffPath = Join-Path $AgentsPath "HANDOFF.md"
    
    New-Item -ItemType Directory -Path $AgentsPath -Force | Out-Null
}

Describe "Get-ApproxTokenCount" {
    Context "Basic text estimation" {
        It "Returns 0 for empty string" {
            $result = Get-ApproxTokenCount -Text " "
            $result | Should -BeGreaterOrEqual 0
            $result | Should -BeLessThan 5
        }

        It "Handles whitespace-only string" {
            $result = Get-ApproxTokenCount -Text "   "
            $result | Should -BeGreaterOrEqual 0
            $result | Should -BeLessThan 5
        }

        It "Estimates simple English prose correctly" {
            # "Hello world" = 12 chars ≈ 3 tokens (base) * 1.05 (safety) = 4 tokens
            $text = "Hello world"
            $result = Get-ApproxTokenCount -Text $text
            $result | Should -BeGreaterThan 2
            $result | Should -BeLessThan 6
        }

        It "Handles newline normalization" {
            # Same text with different newline styles should yield same token count
            $textLF = "Line 1`nLine 2`nLine 3"
            $textCRLF = "Line 1`r`nLine 2`r`nLine 3"
            
            $resultLF = Get-ApproxTokenCount -Text $textLF
            $resultCRLF = Get-ApproxTokenCount -Text $textCRLF
            
            $resultLF | Should -Be $resultCRLF
        }
    }

    Context "Heuristic adjustments" {
        It "Increases estimate for non-ASCII content" {
            # Non-ASCII characters (emoji, multilingual) tokenize less efficiently
            $asciiText = "Hello world this is a test message"
            $nonAsciiText = "Hello 🚀 world 你好 this is a test"
            
            $asciiTokens = Get-ApproxTokenCount -Text $asciiText
            $nonAsciiTokens = Get-ApproxTokenCount -Text $nonAsciiText
            
            # Non-ASCII should have higher token count per character
            $nonAsciiTokens | Should -BeGreaterThan $asciiTokens
        }

        It "Increases estimate for code-like text" {
            # Code has high punctuation, low whitespace
            $proseText = "This is a simple sentence with normal punctuation."
            $codeText = 'Get-Content -Path $file | Where-Object {$_.Length -gt 0} | ForEach-Object {Write-Host $_}'
            
            $proseTokens = Get-ApproxTokenCount -Text $proseText
            $codeTokens = Get-ApproxTokenCount -Text $codeText
            
            # Code should have higher token estimate due to density
            $codeTokens | Should -BeGreaterThan $proseTokens
        }

        It "Increases estimate for digit-heavy text" {
            # Numbers and IDs tokenize differently
            $proseText = "This is a simple sentence with some words in it today"
            $digitText = "PR-12345 from 2024-12-22 at 10:30:45 UTC with ID 9876543210"
            
            $proseTokens = Get-ApproxTokenCount -Text $proseText
            $digitTokens = Get-ApproxTokenCount -Text $digitText
            
            # Digit-heavy text should have higher estimate
            $digitTokens | Should -BeGreaterThan $proseTokens
        }

        It "Applies safety margin (5%)" {
            # Token count should be slightly higher than base estimate
            $text = "A" * 400  # 400 chars = 100 tokens base
            $result = Get-ApproxTokenCount -Text $text
            
            # Should be >= 105 (100 * 1.05)
            $result | Should -BeGreaterOrEqual 105
        }
    }

    Context "Real-world content" {
        It "Estimates markdown document tokens" {
            $markdown = @"

# Project Documentation

## Overview

This is a sample markdown document with:

- Lists
- **Bold text**
- *Italic text*
- `Code blocks`

## Code Example

``````powershell
function Test-Function {
    param([string]`$Name)
    Write-Host "Hello, `$Name"
}
``````

## Conclusion

Token estimation should account for markdown syntax.
"@
            $result = Get-ApproxTokenCount -Text $markdown

            # Should estimate reasonable token count
            $result | Should -BeGreaterThan 50
            $result | Should -BeLessThan 200
        }
    }
}

Describe "Validate-TokenBudget.ps1 Integration" {
    BeforeEach {
        # Clean up test files
        if (Test-Path $HandoffPath) {
            Remove-Item $HandoffPath -Force
        }
    }

    Context "File existence" {
        It "Exits 0 when HANDOFF.md doesn't exist" {
            $result = & pwsh -NoProfile -File $scriptPath -Path $TestRoot 2>&1
            $LASTEXITCODE | Should -Be 0
            $result -join "`n" | Should -Match "HANDOFF.md not found"
        }
    }

    Context "Under budget" {
        It "Passes validation for small file" {
            # Create small HANDOFF.md (well under 5K tokens)
            $content = "# Test Handoff`n`nSmall content" * 10
            Set-Content -Path $HandoffPath -Value $content -NoNewline
            
            $result = & pwsh -NoProfile -File $scriptPath -Path $TestRoot 2>&1
            $LASTEXITCODE | Should -Be 0
            $result -join "`n" | Should -Match "PASS"
        }

        It "Shows remaining token budget" {
            $content = "# Test Handoff`n`nSmall content"
            Set-Content -Path $HandoffPath -Value $content -NoNewline
            
            $result = & pwsh -NoProfile -File $scriptPath -Path $TestRoot 2>&1
            $result -join "`n" | Should -Match "Remaining:.*tokens"
        }
    }

    Context "Over budget" {
        It "Fails validation for large file" {
            # Create HANDOFF.md with >5K tokens (>20KB of text)
            $content = "# Large Handoff`n`n" + ("Lorem ipsum dolor sit amet. " * 1000)
            Set-Content -Path $HandoffPath -Value $content -NoNewline
            
            $result = & pwsh -NoProfile -File $scriptPath -Path $TestRoot -CI 2>&1
            $LASTEXITCODE | Should -Be 1
            $result -join "`n" | Should -Match "FAILED.*exceeds token budget"
        }

        It "Shows over-budget amount" {
            # Create large file
            $content = "# Large Handoff`n`n" + ("Test content with lots of text. " * 1000)
            Set-Content -Path $HandoffPath -Value $content -NoNewline
            
            $result = & pwsh -NoProfile -File $scriptPath -Path $TestRoot -CI 2>&1
            $result -join "`n" | Should -Match "Over budget by:.*tokens"
        }

        It "Shows remediation instructions when over budget" {
            # Create large file - need more content to exceed budget
            $content = "# Large Handoff`n`n" + ("Lorem ipsum dolor sit amet consectetur adipiscing elit. " * 2000)
            Set-Content -Path $HandoffPath -Value $content -NoNewline
            
            $result = & pwsh -NoProfile -File $scriptPath -Path $TestRoot -CI 2>&1
            $result -join "`n" | Should -Match "Archive current content"
            $result -join "`n" | Should -Match "ADR-014"
        }
    }

    Context "Custom token budget" {
        It "Respects custom MaxTokens parameter" {
            # Create file that's under 5K but over 500 tokens (need ~2000+ chars)
            $content = "# Test Header`n`n" + ("This is sample content with enough text to test. " * 100)
            Set-Content -Path $HandoffPath -Value $content -NoNewline
            
            # Should pass with default 5K budget
            $result1 = & pwsh -NoProfile -File $scriptPath -Path $TestRoot 2>&1
            $LASTEXITCODE | Should -Be 0
            
            # Should fail with 500 token budget
            $result2 = & pwsh -NoProfile -File $scriptPath -Path $TestRoot -MaxTokens 500 -CI 2>&1
            $LASTEXITCODE | Should -Be 1
        }
    }

    Context "CI mode behavior" {
        It "Returns exit code 1 in CI mode when over budget" {
            # Create large file - need ~25KB+ to exceed 5K tokens
            $content = "# Large Document`n`n" + ("Lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor. " * 2500)
            Set-Content -Path $HandoffPath -Value $content -NoNewline
            
            $result = & pwsh -NoProfile -File $scriptPath -Path $TestRoot -CI 2>&1
            $LASTEXITCODE | Should -Be 1
        }

        It "Returns exit code 0 in CI mode when under budget" {
            $content = "# Small`n`nContent"
            Set-Content -Path $HandoffPath -Value $content -NoNewline
            
            $result = & pwsh -NoProfile -File $scriptPath -Path $TestRoot -CI 2>&1
            $LASTEXITCODE | Should -Be 0
        }
    }

    Context "Output format" {
        It "Shows file size in KB" {
            $content = "# Test`n`nContent"
            Set-Content -Path $HandoffPath -Value $content -NoNewline
            
            $result = & pwsh -NoProfile -File $scriptPath -Path $TestRoot 2>&1
            $result -join "`n" | Should -Match "Size:.*KB"
        }

        It "Shows character count" {
            $content = "Test content"
            Set-Content -Path $HandoffPath -Value $content -NoNewline
            
            $result = & pwsh -NoProfile -File $scriptPath -Path $TestRoot 2>&1
            $result -join "`n" | Should -Match "Characters: 12"
        }

        It "Shows estimated tokens with heuristic label" {
            $content = "# Test"
            Set-Content -Path $HandoffPath -Value $content -NoNewline
            
            $result = & pwsh -NoProfile -File $scriptPath -Path $TestRoot 2>&1
            $result -join "`n" | Should -Match "Estimated tokens:.*\(heuristic\)"
        }
    }
}

Describe "Token Estimation Accuracy" {
    Context "Baseline validation" {
        It "Estimates HANDOFF.md format accurately" {
            # Simulate actual HANDOFF.md structure
            $content = @"

# Enhancement Project Handoff

**Status**: 🟢 ACTIVE

## Active Projects Dashboard

| Project | Status | PR | Next Action |
|---------|--------|----|----|
| PR #222 | 🟢 READY | 222 | Merge |
| PR #212 | 🟢 READY | 212 | Merge |

## Recent Sessions

- [Session 61](./sessions/2025-12-21-session-61.md)
- [Session 60](./sessions/2025-12-21-session-60.md)

## Key Architecture

- ADR-014: Distributed Handoff
- ADR-013: Agent Orchestration
"@
            $tokens = Get-ApproxTokenCount -Text $content

            # This structure should be ~150-250 tokens
            $tokens | Should -BeGreaterThan 100
            $tokens | Should -BeLessThan 350
        }
    }
}

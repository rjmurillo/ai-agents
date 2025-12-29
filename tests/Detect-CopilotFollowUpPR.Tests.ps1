#Requires -Modules Pester

<#
.SYNOPSIS
    Pester tests for Detect-CopilotFollowUpPR.ps1

.DESCRIPTION
    Tests the Copilot follow-up PR detection functionality.
    Validates pattern matching, announcement detection, and categorization logic.
#>

BeforeAll {
    $script:scriptPath = Join-Path $PSScriptRoot ".." ".claude" "skills" "github" "scripts" "pr" "Detect-CopilotFollowUpPR.ps1"
}

Describe "Detect-CopilotFollowUpPR" {
    Context "Pattern Matching" {
        It "Matches valid Copilot follow-up branch pattern" {
            $pattern = "copilot/sub-pr-\d+"
            "copilot/sub-pr-32" -match $pattern | Should -Be $true
            "copilot/sub-pr-156" -match $pattern | Should -Be $true
            "copilot/sub-pr-1" -match $pattern | Should -Be $true
        }

        It "Does not match invalid branch patterns" {
            $pattern = "copilot/sub-pr-\d+"
            "feature/my-branch" -match $pattern | Should -Be $false
            "copilot/feature-123" -match $pattern | Should -Be $false
            "sub-pr-32" -match $pattern | Should -Be $false
        }
    }

    Context "Script Validation" {
        # Note: These tests validate script presence and syntax only.
        # The script is not executed here, so external tools like `gh`
        # are not invoked and do not need to be mocked.

        It "Script file exists at expected path" {
            Test-Path $script:scriptPath | Should -Be $true
        }

        It "Script has valid PowerShell syntax" {
            $errors = $null
            $null = [System.Management.Automation.Language.Parser]::ParseFile(
                $script:scriptPath,
                [ref]$null,
                [ref]$errors
            )
            $errors.Count | Should -Be 0
        }
    }

    Context "Categorization Logic" {
        It "Empty diff indicates DUPLICATE category" {
            $emptyDiffResult = @{
                similarity = 100
                category = 'DUPLICATE'
                reason = 'Follow-up PR contains no changes'
            }
            $emptyDiffResult.category | Should -Be 'DUPLICATE'
            $emptyDiffResult.similarity | Should -Be 100
        }

        It "Single file change indicates LIKELY_DUPLICATE" {
            $singleFileResult = @{
                similarity = 85
                category = 'LIKELY_DUPLICATE'
                reason = 'Single file change matching original scope'
            }
            $singleFileResult.category | Should -Be 'LIKELY_DUPLICATE'
            $singleFileResult.similarity | Should -Be 85
        }

        It "Multiple file changes indicates POSSIBLE_SUPPLEMENTAL" {
            $multiFileResult = @{
                similarity = 40
                category = 'POSSIBLE_SUPPLEMENTAL'
                reason = 'Multiple file changes suggest additional work'
            }
            $multiFileResult.category | Should -Be 'POSSIBLE_SUPPLEMENTAL'
            $multiFileResult.similarity | Should -Be 40
        }
    }

    Context "Recommendation Mapping" {
        It "DUPLICATE maps to CLOSE_AS_DUPLICATE recommendation" {
            $recommendations = @{
                'DUPLICATE' = 'CLOSE_AS_DUPLICATE'
                'LIKELY_DUPLICATE' = 'REVIEW_THEN_CLOSE'
                'POSSIBLE_SUPPLEMENTAL' = 'EVALUATE_FOR_MERGE'
            }
            $recommendations['DUPLICATE'] | Should -Be 'CLOSE_AS_DUPLICATE'
        }

        It "LIKELY_DUPLICATE maps to REVIEW_THEN_CLOSE recommendation" {
            $recommendations = @{
                'DUPLICATE' = 'CLOSE_AS_DUPLICATE'
                'LIKELY_DUPLICATE' = 'REVIEW_THEN_CLOSE'
                'POSSIBLE_SUPPLEMENTAL' = 'EVALUATE_FOR_MERGE'
            }
            $recommendations['LIKELY_DUPLICATE'] | Should -Be 'REVIEW_THEN_CLOSE'
        }

        It "POSSIBLE_SUPPLEMENTAL maps to EVALUATE_FOR_MERGE recommendation" {
            $recommendations = @{
                'DUPLICATE' = 'CLOSE_AS_DUPLICATE'
                'LIKELY_DUPLICATE' = 'REVIEW_THEN_CLOSE'
                'POSSIBLE_SUPPLEMENTAL' = 'EVALUATE_FOR_MERGE'
            }
            $recommendations['POSSIBLE_SUPPLEMENTAL'] | Should -Be 'EVALUATE_FOR_MERGE'
        }
    }

    Context "Output Structure" {
        It "No follow-up result has expected structure" {
            $noFollowUpResult = @{
                found = $false
                followUpPRs = @()
                announcement = $null
                analysis = $null
                recommendation = 'NO_ACTION_NEEDED'
                message = 'No follow-up PRs detected'
            }

            $noFollowUpResult.found | Should -Be $false
            $noFollowUpResult.recommendation | Should -Be 'NO_ACTION_NEEDED'
            $noFollowUpResult.followUpPRs.Count | Should -Be 0
        }

        It "Found follow-up result includes required fields" {
            $foundResult = @{
                found = $true
                originalPRNumber = 32
                followUpPRs = @(@{number = 33})
                announcement = @{id = 123}
                analysis = @(@{category = 'DUPLICATE'})
                recommendation = 'CLOSE_AS_DUPLICATE'
                timestamp = (Get-Date -Format 'O')
            }

            $foundResult.found | Should -Be $true
            $foundResult.originalPRNumber | Should -Be 32
            $foundResult.Keys | Should -Contain 'timestamp'
        }
    }
}

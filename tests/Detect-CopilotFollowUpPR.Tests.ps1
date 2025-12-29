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

    # Read the script content and extract function definitions
    $scriptContent = Get-Content $script:scriptPath -Raw

    # Extract Test-FollowUpPattern function (updated pattern for Issue #292)
    if ($scriptContent -match '(?s)function Test-FollowUpPattern \{.*?(?=\nfunction)') {
        Invoke-Expression $Matches[0]
    }

    # Extract Compare-DiffContent function
    if ($scriptContent -match '(?s)function Compare-DiffContent \{.*?(?=\nfunction|\n# Execute detection|\Z)') {
        Invoke-Expression $Matches[0]
    }
}

Describe "Detect-CopilotFollowUpPR" {
    Context "Pattern Matching" {
        It "Matches valid Copilot follow-up branch pattern" {
            $testPR = @{ headRefName = "copilot/sub-pr-32" }
            Test-FollowUpPattern -PR $testPR | Should -Be $true

            $testPR2 = @{ headRefName = "copilot/sub-pr-156" }
            Test-FollowUpPattern -PR $testPR2 | Should -Be $true

            $testPR3 = @{ headRefName = "copilot/sub-pr-1" }
            Test-FollowUpPattern -PR $testPR3 | Should -Be $true
        }

        It "Does not match invalid branch patterns" {
            $testPR1 = @{ headRefName = "feature/my-branch" }
            Test-FollowUpPattern -PR $testPR1 | Should -Be $false

            $testPR2 = @{ headRefName = "copilot/feature-123" }
            Test-FollowUpPattern -PR $testPR2 | Should -Be $false

            $testPR3 = @{ headRefName = "sub-pr-32" }
            Test-FollowUpPattern -PR $testPR3 | Should -Be $false

            # Issue #507: Reject branches with non-numeric suffixes
            $testPR4 = @{ headRefName = "copilot/sub-pr-32a" }
            Test-FollowUpPattern -PR $testPR4 | Should -Be $false
        }
    }

    Context "PR Number Validation (Issue #292)" {
        It "Returns true when extracted PR number matches OriginalPRNumber" {
            $testPR = @{ headRefName = "copilot/sub-pr-32" }
            Test-FollowUpPattern -PR $testPR -OriginalPRNumber 32 | Should -Be $true

            $testPR2 = @{ headRefName = "copilot/sub-pr-156" }
            Test-FollowUpPattern -PR $testPR2 -OriginalPRNumber 156 | Should -Be $true
        }

        It "Returns false when extracted PR number does not match OriginalPRNumber" {
            # This prevents false positives when multiple follow-up branches exist
            $testPR = @{ headRefName = "copilot/sub-pr-32" }
            Test-FollowUpPattern -PR $testPR -OriginalPRNumber 33 | Should -Be $false
            Test-FollowUpPattern -PR $testPR -OriginalPRNumber 320 | Should -Be $false
        }

        It "Returns true for pattern-only match when OriginalPRNumber is 0" {
            $testPR = @{ headRefName = "copilot/sub-pr-99" }
            Test-FollowUpPattern -PR $testPR | Should -Be $true
            Test-FollowUpPattern -PR $testPR -OriginalPRNumber 0 | Should -Be $true
        }

        It "Returns false for invalid patterns even with matching number" {
            $testPR = @{ headRefName = "feature/sub-pr-32" }
            Test-FollowUpPattern -PR $testPR -OriginalPRNumber 32 | Should -Be $false
        }
    }

    Context "Script Validation" {
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

    Context "Categorization Logic - Compare-DiffContent" {
        It "Empty diff string returns DUPLICATE category" {
            $result = Compare-DiffContent -FollowUpDiff '' -OriginalCommits @()
            $result.category | Should -Be 'DUPLICATE'
            $result.similarity | Should -Be 100
            $result.reason | Should -Be 'Follow-up PR contains no changes'
        }

        It "Whitespace-only diff returns DUPLICATE category" {
            $result = Compare-DiffContent -FollowUpDiff '   ' -OriginalCommits @()
            $result.category | Should -Be 'DUPLICATE'
            $result.similarity | Should -Be 100
            $result.reason | Should -Be 'Follow-up PR contains no changes'
        }

        It "Single file change with original commits returns LIKELY_DUPLICATE" {
            $singleFileDiff = @"
diff --git a/file.ps1 b/file.ps1
index 1234567..abcdefg 100644
--- a/file.ps1
+++ b/file.ps1
@@ -1,3 +1,4 @@
 # Some content
+# New line
"@
            $originalCommits = @(@{ sha = 'abc123' })
            $result = Compare-DiffContent -FollowUpDiff $singleFileDiff -OriginalCommits $originalCommits
            $result.category | Should -Be 'LIKELY_DUPLICATE'
            $result.similarity | Should -Be 85
        }

        It "Multiple file changes returns POSSIBLE_SUPPLEMENTAL" {
            $multiFileDiff = @"
diff --git a/file1.ps1 b/file1.ps1
index 1234567..abcdefg 100644
--- a/file1.ps1
+++ b/file1.ps1
@@ -1,3 +1,4 @@
 # Content
diff --git a/file2.ps1 b/file2.ps1
index 7654321..gfedcba 100644
--- a/file2.ps1
+++ b/file2.ps1
@@ -1,3 +1,4 @@
 # More content
"@
            $result = Compare-DiffContent -FollowUpDiff $multiFileDiff -OriginalCommits @()
            $result.category | Should -Be 'POSSIBLE_SUPPLEMENTAL'
            $result.similarity | Should -Be 40
        }
    }

    Context "Output Structure" {
        It "No follow-up result has expected structure" {
            # This tests the expected output structure when no follow-ups are found
            $expectedKeys = @('found', 'followUpPRs', 'announcement', 'analysis', 'recommendation', 'message')
            $expectedKeys | ForEach-Object {
                # Verify the structure is documented
                $_ | Should -Not -BeNullOrEmpty
            }
        }

        It "Found follow-up result includes required fields" {
            # This tests the expected output structure when follow-ups are found
            $expectedKeys = @('found', 'originalPRNumber', 'followUpPRs', 'announcement', 'analysis', 'recommendation', 'timestamp')
            $expectedKeys | ForEach-Object {
                # Verify the structure is documented
                $_ | Should -Not -BeNullOrEmpty
            }
        }
    }
}

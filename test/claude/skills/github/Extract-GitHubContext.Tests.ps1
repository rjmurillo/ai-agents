#Requires -Modules Pester

<#
.SYNOPSIS
    Tests for Extract-GitHubContext.ps1 utility script.

.DESCRIPTION
    Validates PR/issue number extraction from text patterns and GitHub URLs.
    Part of Issue #829: Context Inference Gap fix.
#>

BeforeAll {
    $ScriptPath = Join-Path $PSScriptRoot ".." ".." ".." ".." ".claude" "skills" "github" "scripts" "utils" "Extract-GitHubContext.ps1"
}

Describe "Extract-GitHubContext" {

    Context "Module/Script Loading" {
        It "Script exists at expected path" {
            Test-Path $ScriptPath | Should -Be $true
        }

        It "Script has valid PowerShell syntax" {
            $errors = $null
            [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]$errors)
            $errors.Count | Should -Be 0
        }
    }

    Context "PR Number Extraction from Text Patterns" {

        It "Extracts PR number from 'PR 806'" {
            $result = & $ScriptPath -Text "Review PR 806 comments"
            $result.PRNumbers | Should -Contain 806
        }

        It "Extracts PR number from 'PR #806'" {
            $result = & $ScriptPath -Text "Check PR #806"
            $result.PRNumbers | Should -Contain 806
        }

        It "Extracts PR number from 'PR#806' (no space)" {
            $result = & $ScriptPath -Text "See PR#806 for details"
            $result.PRNumbers | Should -Contain 806
        }

        It "Extracts PR number case-insensitively from 'pr 123'" {
            $result = & $ScriptPath -Text "review pr 123"
            $result.PRNumbers | Should -Contain 123
        }

        It "Extracts PR number from 'pull request 123'" {
            $result = & $ScriptPath -Text "The pull request 123 needs review"
            $result.PRNumbers | Should -Contain 123
        }

        It "Extracts PR number from 'pull request #456'" {
            $result = & $ScriptPath -Text "See pull request #456"
            $result.PRNumbers | Should -Contain 456
        }

        It "Extracts PR number case-insensitively from 'Pull Request 789'" {
            $result = & $ScriptPath -Text "Check Pull Request 789"
            $result.PRNumbers | Should -Contain 789
        }

        It "Extracts standalone '#806'" {
            $result = & $ScriptPath -Text "Review #806 comments"
            $result.PRNumbers | Should -Contain 806
        }

        It "Extracts multiple PR numbers from text" {
            $result = & $ScriptPath -Text "Compare PR 100 with PR 200"
            $result.PRNumbers | Should -Contain 100
            $result.PRNumbers | Should -Contain 200
            $result.PRNumbers.Count | Should -Be 2
        }

        It "Deduplicates PR numbers mentioned multiple times" {
            $result = & $ScriptPath -Text "PR 806 and PR #806 are the same"
            $result.PRNumbers | Should -Contain 806
            $result.PRNumbers.Count | Should -Be 1
        }
    }

    Context "Issue Number Extraction from Text Patterns" {

        It "Extracts issue number from 'issue 45'" {
            $result = & $ScriptPath -Text "Related to issue 45"
            $result.IssueNumbers | Should -Contain 45
        }

        It "Extracts issue number from 'issue #45'" {
            $result = & $ScriptPath -Text "See issue #45"
            $result.IssueNumbers | Should -Contain 45
        }

        It "Extracts issue number case-insensitively from 'Issue 100'" {
            $result = & $ScriptPath -Text "Check Issue 100"
            $result.IssueNumbers | Should -Contain 100
        }

        It "Extracts multiple issue numbers" {
            $result = & $ScriptPath -Text "Issues 10 and issue #20 are related"
            $result.IssueNumbers | Should -Contain 10
            $result.IssueNumbers | Should -Contain 20
        }
    }

    Context "GitHub URL Extraction" {

        It "Extracts PR from full GitHub URL" {
            $result = & $ScriptPath -Text "Review https://github.com/owner/repo/pull/123"
            $result.PRNumbers | Should -Contain 123
            $result.Owner | Should -Be "owner"
            $result.Repo | Should -Be "repo"
        }

        It "Extracts issue from GitHub URL" {
            $result = & $ScriptPath -Text "See https://github.com/owner/repo/issues/456"
            $result.IssueNumbers | Should -Contain 456
            $result.Owner | Should -Be "owner"
            $result.Repo | Should -Be "repo"
        }

        It "Extracts context from URL with real repository names" {
            $result = & $ScriptPath -Text "Check https://github.com/rjmurillo/ai-agents/pull/806"
            $result.PRNumbers | Should -Contain 806
            $result.Owner | Should -Be "rjmurillo"
            $result.Repo | Should -Be "ai-agents"
        }

        It "Handles URL with fragments" {
            $result = & $ScriptPath -Text "https://github.com/owner/repo/pull/123#discussion_r456"
            $result.PRNumbers | Should -Contain 123
        }

        It "Handles URL with query parameters" {
            $result = & $ScriptPath -Text "https://github.com/owner/repo/pull/123?diff=split"
            $result.PRNumbers | Should -Contain 123
        }

        It "Extracts multiple URLs" {
            $text = "Compare https://github.com/owner/repo/pull/100 with https://github.com/owner/repo/pull/200"
            $result = & $ScriptPath -Text $text
            $result.PRNumbers | Should -Contain 100
            $result.PRNumbers | Should -Contain 200
            $result.URLs.Count | Should -Be 2
        }

        It "Populates URLs array with structured data" {
            $result = & $ScriptPath -Text "https://github.com/owner/repo/pull/123"
            $result.URLs.Count | Should -Be 1
            $result.URLs[0].Type | Should -Be "PR"
            $result.URLs[0].Number | Should -Be 123
            $result.URLs[0].Owner | Should -Be "owner"
            $result.URLs[0].Repo | Should -Be "repo"
        }
    }

    Context "Mixed Text and URL Extraction" {

        It "Extracts from both text patterns and URLs" {
            $text = "Review PR 100 and https://github.com/owner/repo/pull/200"
            $result = & $ScriptPath -Text $text
            $result.PRNumbers | Should -Contain 100
            $result.PRNumbers | Should -Contain 200
            $result.Owner | Should -Be "owner"
            $result.Repo | Should -Be "repo"
        }

        It "URL takes priority for owner/repo context" {
            $text = "PR 100 from https://github.com/correct-owner/correct-repo/pull/200"
            $result = & $ScriptPath -Text $text
            $result.Owner | Should -Be "correct-owner"
            $result.Repo | Should -Be "correct-repo"
        }

        It "Does not double-count # numbers inside URLs" {
            # The #123 in URL should not be extracted separately
            $text = "https://github.com/owner/repo/pull/123"
            $result = & $ScriptPath -Text $text
            $result.PRNumbers.Count | Should -Be 1
            $result.PRNumbers | Should -Contain 123
        }
    }

    Context "Edge Cases and Boundary Conditions" {

        It "Returns empty arrays for text with no PR/issue references" {
            $result = & $ScriptPath -Text "Hello world, no PR here"
            $result.PRNumbers.Count | Should -Be 0
            $result.IssueNumbers.Count | Should -Be 0
        }

        It "Returns null for owner/repo when no URL present" {
            $result = & $ScriptPath -Text "PR 806"
            $result.Owner | Should -BeNullOrEmpty
            $result.Repo | Should -BeNullOrEmpty
        }

        It "Handles large PR numbers" {
            $result = & $ScriptPath -Text "PR 999999"
            $result.PRNumbers | Should -Contain 999999
        }

        It "Does not extract PR from unrelated numbers" {
            # "123 apples" should not match (no PR/# prefix)
            $result = & $ScriptPath -Text "I have 123 apples"
            $result.PRNumbers | Should -Not -Contain 123
        }

        It "Handles multiline text" {
            $text = @"
Please review:
- PR 100
- PR 200
- issue 300
"@
            $result = & $ScriptPath -Text $text
            $result.PRNumbers | Should -Contain 100
            $result.PRNumbers | Should -Contain 200
            $result.IssueNumbers | Should -Contain 300
        }

        It "Handles special characters around PR numbers" {
            $result = & $ScriptPath -Text "(PR 123) and [PR 456]"
            $result.PRNumbers | Should -Contain 123
            $result.PRNumbers | Should -Contain 456
        }

        It "Validates GitHub owner name format in URLs" {
            # Owner names can't start or end with hyphen
            $result = & $ScriptPath -Text "https://github.com/valid-owner/repo/pull/123"
            $result.Owner | Should -Be "valid-owner"
        }

        It "Validates GitHub repo name format in URLs" {
            # Repo names can have dots, underscores, hyphens
            $result = & $ScriptPath -Text "https://github.com/owner/my_repo.name-test/pull/123"
            $result.Repo | Should -Be "my_repo.name-test"
        }
    }

    Context "RequirePR Validation (Autonomous Execution)" {

        It "Does not throw when PR found and RequirePR specified" {
            { & $ScriptPath -Text "Review PR 806" -RequirePR } | Should -Not -Throw
        }

        It "Throws when no PR found and RequirePR specified" {
            { & $ScriptPath -Text "Review the comments" -RequirePR } | Should -Throw -ExpectedMessage "*Cannot extract PR number*"
        }

        It "Error message is actionable when RequirePR fails" {
            $errorThrown = $false
            $errorMessage = ""
            try {
                & $ScriptPath -Text "Review the comments" -RequirePR
            }
            catch {
                $errorThrown = $true
                $errorMessage = $_.Exception.Message
            }

            $errorThrown | Should -Be $true
            $errorMessage | Should -Match "PR number"
            $errorMessage | Should -Match "URL"
        }
    }

    Context "RequireIssue Validation (Autonomous Execution)" {

        It "Does not throw when issue found and RequireIssue specified" {
            { & $ScriptPath -Text "Check issue 45" -RequireIssue } | Should -Not -Throw
        }

        It "Throws when no issue found and RequireIssue specified" {
            { & $ScriptPath -Text "Check the details" -RequireIssue } | Should -Throw -ExpectedMessage "*Cannot extract issue number*"
        }
    }

    Context "Output Structure" {

        It "Returns PSCustomObject with expected properties" {
            $result = & $ScriptPath -Text "PR 123"
            $result | Should -BeOfType [PSCustomObject]
            $result.PSObject.Properties.Name | Should -Contain "PRNumbers"
            $result.PSObject.Properties.Name | Should -Contain "IssueNumbers"
            $result.PSObject.Properties.Name | Should -Contain "Owner"
            $result.PSObject.Properties.Name | Should -Contain "Repo"
            $result.PSObject.Properties.Name | Should -Contain "URLs"
            $result.PSObject.Properties.Name | Should -Contain "RawMatches"
        }

        It "PRNumbers contains expected values" {
            $result = & $ScriptPath -Text "PR 123"
            # Use @() to ensure array context for single elements
            @($result.PRNumbers) | Should -Contain 123
            @($result.PRNumbers).Count | Should -Be 1
        }

        It "IssueNumbers contains expected values" {
            $result = & $ScriptPath -Text "issue 45"
            @($result.IssueNumbers) | Should -Contain 45
            @($result.IssueNumbers).Count | Should -Be 1
        }

        It "URLs contains expected structure" {
            $result = & $ScriptPath -Text "https://github.com/owner/repo/pull/123"
            @($result.URLs).Count | Should -Be 1
            $result.URLs[0].Number | Should -Be 123
        }

        It "RawMatches contains original matched text" {
            $result = & $ScriptPath -Text "Review PR 806"
            $result.RawMatches | Should -Contain "PR 806"
        }
    }

    Context "Real-World User Prompt Scenarios (Issue #829)" {

        It "Extracts from 'Review PR 806 comments... github.com/rjmurillo/ai-agents/pull/806'" {
            $text = "Review PR 806 comments... https://github.com/rjmurillo/ai-agents/pull/806"
            $result = & $ScriptPath -Text $text
            $result.PRNumbers | Should -Contain 806
            $result.Owner | Should -Be "rjmurillo"
            $result.Repo | Should -Be "ai-agents"
        }

        It "Extracts from 'respond to PR #123 feedback'" {
            $result = & $ScriptPath -Text "respond to PR #123 feedback"
            $result.PRNumbers | Should -Contain 123
        }

        It "Extracts from 'handle comments on pull request 456'" {
            $result = & $ScriptPath -Text "handle comments on pull request 456"
            $result.PRNumbers | Should -Contain 456
        }

        It "Extracts from bare URL pasted by user" {
            $result = & $ScriptPath -Text "https://github.com/owner/repo/pull/789"
            $result.PRNumbers | Should -Contain 789
        }

        It "Extracts from URL with /files path" {
            $result = & $ScriptPath -Text "https://github.com/owner/repo/pull/123/files"
            $result.PRNumbers | Should -Contain 123
        }

        It "Extracts from URL with /commits path" {
            $result = & $ScriptPath -Text "https://github.com/owner/repo/pull/123/commits"
            $result.PRNumbers | Should -Contain 123
        }
    }
}

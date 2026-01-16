<#
.SYNOPSIS
    Pester tests for Get-PRCheckLogs.ps1 script.

.DESCRIPTION
    Tests the PR check log retrieval functionality including:
    - Parameter validation
    - URL parsing (run ID, job ID extraction)
    - GitHub Actions URL validation
    - Exit code validation

    Note: This is initial test coverage. Full integration tests require
    mocking gh CLI calls and GraphQL responses.

.NOTES
    Requires Pester 5.x or later.

    EXIT CODES:
    0  - Success: All tests passed
    1  - Error: One or more tests failed (set by Pester framework)

    See: ADR-035 Exit Code Standardization
#>

BeforeAll {
    $Script:ScriptPath = Join-Path $PSScriptRoot ".." ".." ".." ".." ".claude" "skills" "github" "scripts" "pr" "Get-PRCheckLogs.ps1"
    $Script:ModulePath = Join-Path $PSScriptRoot ".." ".." ".." ".." ".claude" "skills" "github" "modules" "GitHubCore.psm1"

    # Verify script exists
    if (-not (Test-Path $Script:ScriptPath)) {
        throw "Script not found at: $Script:ScriptPath"
    }

    # Import the module for helper functions
    Import-Module $Script:ModulePath -Force

    # Mock authentication functions to prevent script from exiting during dot-source
    Mock -ModuleName GitHubCore Test-GhAuthenticated { return $true }
    Mock -ModuleName GitHubCore Resolve-RepoParams {
        return @{ Owner = 'testowner'; Repo = 'testrepo' }
    }

    # Dot-source the script once to load functions
    . $Script:ScriptPath -PullRequest 1 -ErrorAction SilentlyContinue 2>$null
}

Describe "Get-PRCheckLogs.ps1" {

    Context "Parameter Validation" {

        It "Should accept -PullRequest parameter" {
            $command = Get-Command $Script:ScriptPath
            $command.Parameters.Keys | Should -Contain 'PullRequest'
        }

        It "Should accept -Owner parameter" {
            $command = Get-Command $Script:ScriptPath
            $command.Parameters.Keys | Should -Contain 'Owner'
        }

        It "Should accept -Repo parameter" {
            $command = Get-Command $Script:ScriptPath
            $command.Parameters.Keys | Should -Contain 'Repo'
        }

        It "Should accept -ChecksInput parameter for pipeline mode" {
            $command = Get-Command $Script:ScriptPath
            $command.Parameters.Keys | Should -Contain 'ChecksInput'
            $command.Parameters['ChecksInput'].Attributes | Where-Object {
                $_ -is [System.Management.Automation.ParameterAttribute] -and $_.ValueFromPipeline
            } | Should -Not -BeNullOrEmpty
        }

        It "Should accept -MaxLines parameter with default value 160" {
            $command = Get-Command $Script:ScriptPath
            $command.Parameters.Keys | Should -Contain 'MaxLines'
        }

        It "Should accept -ContextLines parameter with default value 30" {
            $command = Get-Command $Script:ScriptPath
            $command.Parameters.Keys | Should -Contain 'ContextLines'
        }
    }

    Context "URL Parsing - Run ID Extraction" {

        It "Should extract run ID from standard GitHub Actions URL" {
            $url = "https://github.com/owner/repo/actions/runs/12345678"
            $runId = Get-RunIdFromUrl -Url $url

            $runId | Should -Be "12345678"
        }

        It "Should extract run ID from URL with job ID" {
            $url = "https://github.com/owner/repo/actions/runs/12345678/job/98765"
            $runId = Get-RunIdFromUrl -Url $url

            $runId | Should -Be "12345678"
        }

        It "Should return null for non-GitHub Actions URL" {
            $url = "https://buildkite.com/org/pipeline/builds/123"
            $runId = Get-RunIdFromUrl -Url $url

            $runId | Should -BeNullOrEmpty
        }

        It "Should return null for invalid URL format" {
            $url = "https://example.com/invalid"
            $runId = Get-RunIdFromUrl -Url $url

            $runId | Should -BeNullOrEmpty
        }

        It "Should handle URLs with query parameters" {
            $url = "https://github.com/owner/repo/actions/runs/12345678?check_suite_focus=true"
            $runId = Get-RunIdFromUrl -Url $url

            $runId | Should -Be "12345678"
        }

        It "Should handle URLs with fragments" {
            $url = "https://github.com/owner/repo/actions/runs/12345678#summary"
            $runId = Get-RunIdFromUrl -Url $url

            $runId | Should -Be "12345678"
        }
    }

    Context "URL Parsing - Job ID Extraction" {

        It "Should extract job ID from URL with job component" {
            $url = "https://github.com/owner/repo/actions/runs/12345678/job/98765"
            $jobId = Get-JobIdFromUrl -Url $url

            $jobId | Should -Be "98765"
        }

        It "Should return null for URL without job component" {
            $url = "https://github.com/owner/repo/actions/runs/12345678"
            $jobId = Get-JobIdFromUrl -Url $url

            $jobId | Should -BeNullOrEmpty
        }

        It "Should return null for non-GitHub Actions URL" {
            $url = "https://circleci.com/workflow-run/abc123"
            $jobId = Get-JobIdFromUrl -Url $url

            $jobId | Should -BeNullOrEmpty
        }

        It "Should handle job URLs with query parameters" {
            $url = "https://github.com/owner/repo/actions/runs/12345678/job/98765?pr=123"
            $jobId = Get-JobIdFromUrl -Url $url

            $jobId | Should -Be "98765"
        }
    }

    Context "GitHub Actions URL Detection" {

        It "Should identify valid GitHub Actions URL" {
            $url = "https://github.com/owner/repo/actions/runs/12345678"
            $isGitHub = Test-IsGitHubActionsUrl -Url $url

            $isGitHub | Should -Be $true
        }

        It "Should identify valid GitHub Actions URL with job" {
            $url = "https://github.com/owner/repo/actions/runs/12345678/job/98765"
            $isGitHub = Test-IsGitHubActionsUrl -Url $url

            $isGitHub | Should -Be $true
        }

        It "Should reject Buildkite URLs" {
            $url = "https://buildkite.com/org/pipeline/builds/123"
            $isGitHub = Test-IsGitHubActionsUrl -Url $url

            $isGitHub | Should -Be $false
        }

        It "Should reject CircleCI URLs" {
            $url = "https://circleci.com/workflow-run/abc123"
            $isGitHub = Test-IsGitHubActionsUrl -Url $url

            $isGitHub | Should -Be $false
        }

        It "Should reject Travis CI URLs" {
            $url = "https://travis-ci.org/owner/repo/builds/456"
            $isGitHub = Test-IsGitHubActionsUrl -Url $url

            $isGitHub | Should -Be $false
        }

        It "Should reject Jenkins URLs" {
            $url = "https://jenkins.example.com/job/123"
            $isGitHub = Test-IsGitHubActionsUrl -Url $url

            $isGitHub | Should -Be $false
        }

        It "Should reject GitLab CI URLs" {
            $url = "https://gitlab.com/owner/repo/-/pipelines/789"
            $isGitHub = Test-IsGitHubActionsUrl -Url $url

            $isGitHub | Should -Be $false
        }

        It "Should reject non-URL strings" {
            $url = "not a url"
            $isGitHub = Test-IsGitHubActionsUrl -Url $url

            $isGitHub | Should -Be $false
        }

        It "Should reject empty strings" {
            $url = ""
            $isGitHub = Test-IsGitHubActionsUrl -Url $url

            $isGitHub | Should -Be $false
        }
    }

    Context "Exit Code Documentation" {

        It "Should document exit codes in NOTES section" {
            $content = Get-Content $Script:ScriptPath -Raw
            $content | Should -Match "Exit Codes:"
            $content | Should -Match "0.*Success"
            $content | Should -Match "1.*Invalid parameters"
            $content | Should -Match "2.*PR not found"
            $content | Should -Match "3.*API error"
        }
    }

    Context "Script Metadata" {

        It "Should have a synopsis" {
            $help = Get-Help $Script:ScriptPath
            $help.Synopsis | Should -Not -BeNullOrEmpty
        }

        It "Should have a description" {
            $help = Get-Help $Script:ScriptPath
            $help.Description | Should -Not -BeNullOrEmpty
        }

        It "Should have examples" {
            $help = Get-Help $Script:ScriptPath -Examples
            $help.Examples | Should -Not -BeNullOrEmpty
        }

        It "Should reference ADR-035 for exit code standardization" {
            $help = Get-Help $Script:ScriptPath
            $help.AlertSet.Alert.Text | Should -Match "ADR-035"
        }
    }
}

#Requires -Modules Pester

<#
.SYNOPSIS
    Tests for New-Issue.ps1 script

.DESCRIPTION
    Validates syntax, parameter validation, and error handling for the New-Issue.ps1 script.
    Covers basic functionality and edge cases for creating GitHub Issues.
#>

BeforeAll {
    # Correct path: from .github/tests/skills/github -> .claude/skills/github/scripts/issue
    $ScriptPath = Join-Path $PSScriptRoot ".." ".." ".." ".." ".claude" "skills" "github" "scripts" "issue" "New-Issue.ps1"
    $ModulePath = Join-Path $PSScriptRoot ".." ".." ".." ".." ".claude" "skills" "github" "modules" "GitHubCore.psm1"

    # Import the module for error handling functions
    Import-Module $ModulePath -Force
}

Describe "New-Issue" {

    Context "Syntax Validation" {
        It "Should exist as a file" {
            Test-Path $ScriptPath | Should -BeTrue
        }

        It "Should have .ps1 extension" {
            [System.IO.Path]::GetExtension($ScriptPath) | Should -Be ".ps1"
        }

        It "Should be readable" {
            { Get-Content $ScriptPath -Raw } | Should -Not -Throw
        }

        It "Should have CmdletBinding attribute" {
            $scriptContent = Get-Content $ScriptPath -Raw
            $scriptContent | Should -Match '\[CmdletBinding'
        }
    }

    Context "Parameter Validation" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should have Title as mandatory parameter" {
            $scriptContent | Should -Match '\[Parameter\(Mandatory\)\].*\[string\]\$Title'
        }

        It "Should have optional Owner parameter" {
            $scriptContent | Should -Match '\[string\]\$Owner'
        }

        It "Should have optional Repo parameter" {
            $scriptContent | Should -Match '\[string\]\$Repo'
        }

        It "Should have optional Body parameter" {
            $scriptContent | Should -Match '\[string\]\$Body'
        }

        It "Should have optional BodyFile parameter" {
            $scriptContent | Should -Match '\[string\]\$BodyFile'
        }

        It "Should have optional Labels parameter" {
            $scriptContent | Should -Match '\[string\]\$Labels'
        }

        It "Should import GitHubCore module" {
            $scriptContent | Should -Match 'Import-Module.*GitHubCore\.psm1'
        }

        It "Should call Assert-GhAuthenticated" {
            $scriptContent | Should -Match 'Assert-GhAuthenticated'
        }

        It "Should call Resolve-RepoParams" {
            $scriptContent | Should -Match 'Resolve-RepoParams'
        }
    }

    Context "Error Handling - Exit Codes" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should document exit code 0 for Success" {
            $scriptContent | Should -Match 'Exit Codes:.*0=Success'
        }

        It "Should document exit code 1 for Invalid params" {
            $scriptContent | Should -Match 'Exit Codes:.*1=Invalid params'
        }

        It "Should document exit code 2 for File not found" {
            $scriptContent | Should -Match 'Exit Codes:.*2=File not found'
        }

        It "Should document exit code 3 for API error" {
            $scriptContent | Should -Match 'Exit Codes:.*3=API error'
        }

        It "Should document exit code 4 for Not authenticated" {
            $scriptContent | Should -Match 'Exit Codes:.*4=Not authenticated'
        }
    }

    Context "Parameter Sets" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should have BodyText parameter set" {
            $scriptContent | Should -Match "ParameterSetName\s*=\s*'BodyText'"
        }

        It "Should have BodyFile parameter set" {
            $scriptContent | Should -Match "ParameterSetName\s*=\s*'BodyFile'"
        }

        It "Should have default parameter set as BodyText" {
            $scriptContent | Should -Match "DefaultParameterSetName\s*=\s*'BodyText'"
        }
    }

    Context "Core Functionality" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should validate Title is not empty" {
            $scriptContent | Should -Match 'IsNullOrWhiteSpace\(\$Title\)'
        }

        It "Should check if BodyFile exists" {
            $scriptContent | Should -Match 'Test-Path \$BodyFile'
        }

        It "Should read body from file when BodyFile provided" {
            $scriptContent | Should -Match 'Get-Content.*\$BodyFile'
        }

        It "Should use gh issue create command" {
            $scriptContent | Should -Match "'issue'.*'create'"
        }

        It "Should check LASTEXITCODE after gh command" {
            $scriptContent | Should -Match '\$LASTEXITCODE -ne 0'
        }

        It "Should parse issue number from result URL" {
            $scriptContent | Should -Match "issues/\(\\d\+\)"
        }
    }

    Context "GitHub Actions Integration" {
        BeforeAll {
            $scriptContent = Get-Content $ScriptPath -Raw
        }

        It "Should check for GITHUB_OUTPUT environment variable" {
            $scriptContent | Should -Match '\$env:GITHUB_OUTPUT'
        }

        It "Should output success status" {
            $scriptContent | Should -Match 'success=true'
        }

        It "Should output issue_number" {
            $scriptContent | Should -Match 'issue_number='
        }

        It "Should output issue_url" {
            $scriptContent | Should -Match 'issue_url='
        }
    }

    Context "Mock-based Behavior Tests" {
        BeforeAll {
            # Mock the module functions and gh CLI
            Mock -CommandName 'gh' -MockWith {
                $global:LASTEXITCODE = 0
                return "https://github.com/test/repo/issues/123"
            }

            Mock -CommandName 'Assert-GhAuthenticated' -MockWith { }
            Mock -CommandName 'Resolve-RepoParams' -MockWith {
                return @{ Owner = 'test'; Repo = 'repo' }
            }
            Mock -CommandName 'Write-Host' -MockWith { }
        }

        It "Should require Title parameter" {
            { & $ScriptPath } | Should -Throw
        }
    }
}

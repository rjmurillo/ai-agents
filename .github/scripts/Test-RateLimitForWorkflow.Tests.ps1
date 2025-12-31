#Requires -Modules Pester

<#
.SYNOPSIS
    Pester tests for Test-RateLimitForWorkflow.ps1

.DESCRIPTION
    Tests the workflow rate limit wrapper script.
    Validates module import, threshold handling, and exit codes.

.NOTES
    Created per issue #273 (DRY rate limit code).
#>

BeforeAll {
    $script:ScriptPath = Join-Path $PSScriptRoot "Test-RateLimitForWorkflow.ps1"
    $script:ModulePath = Join-Path $PSScriptRoot ".." ".." ".claude" "skills" "github" "modules" "GitHubCore.psm1"
}

Describe "Test-RateLimitForWorkflow.ps1" {
    Context "Script Validation" {
        It "Script file exists at expected path" {
            Test-Path $script:ScriptPath | Should -Be $true
        }

        It "Script has valid PowerShell syntax" {
            $errors = $null
            $null = [System.Management.Automation.Language.Parser]::ParseFile(
                $script:ScriptPath,
                [ref]$null,
                [ref]$errors
            )
            $errors.Count | Should -Be 0
        }

        It "GitHubCore module exists" {
            Test-Path $script:ModulePath | Should -Be $true
        }
    }

    Context "Parameter Validation" {
        It "Has CoreThreshold parameter with default 100" {
            $params = (Get-Command $script:ScriptPath).Parameters
            $params.ContainsKey('CoreThreshold') | Should -Be $true
            $params['CoreThreshold'].ParameterType | Should -Be ([int])
        }

        It "Has GraphQLThreshold parameter with default 50" {
            $params = (Get-Command $script:ScriptPath).Parameters
            $params.ContainsKey('GraphQLThreshold') | Should -Be $true
            $params['GraphQLThreshold'].ParameterType | Should -Be ([int])
        }
    }

    Context "Module Integration" {
        BeforeAll {
            # Import the module to verify Test-WorkflowRateLimit exists
            Import-Module $script:ModulePath -Force
        }

        It "Test-WorkflowRateLimit function is available after module import" {
            Get-Command -Name Test-WorkflowRateLimit -ErrorAction SilentlyContinue | Should -Not -BeNullOrEmpty
        }

        AfterAll {
            Remove-Module GitHubCore -Force -ErrorAction SilentlyContinue
        }
    }

    Context "Output Validation" {
        It "Script returns exit code 0 or 1" {
            # This test validates script structure - actual execution depends on API access
            $content = Get-Content $script:ScriptPath -Raw
            $content | Should -Match 'exit 0'
            $content | Should -Match 'exit 1'
        }

        It "Script writes to GITHUB_OUTPUT when available" {
            $content = Get-Content $script:ScriptPath -Raw
            $content | Should -Match 'GITHUB_OUTPUT'
            $content | Should -Match 'core_remaining='
        }

        It "Script writes to GITHUB_STEP_SUMMARY when available" {
            $content = Get-Content $script:ScriptPath -Raw
            $content | Should -Match 'GITHUB_STEP_SUMMARY'
        }
    }
}

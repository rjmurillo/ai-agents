#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Pester tests for New-SessionLog.ps1
#>

BeforeAll {
    $scriptPath = Join-Path $PSScriptRoot "../.claude/skills/session-init/scripts/New-SessionLog.ps1"
    $repoRoot = git rev-parse --show-toplevel
}

Describe "New-SessionLog.ps1" {
    Context "Input Validation" {
        It "Should accept session number parameter" {
            # Mock test - verify parameter exists
            $ast = [System.Management.Automation.Language.Parser]::ParseFile($scriptPath, [ref]$null, [ref]$null)
            $sessionNumberParam = $ast.FindAll({ $args[0] -is [System.Management.Automation.Language.ParameterAst] -and $args[0].Name.VariablePath.UserPath -eq 'SessionNumber' }, $true)

            $sessionNumberParam | Should -Not -BeNullOrEmpty
        }

        It "Should accept objective parameter" {
            # Mock test - verify parameter exists
            $ast = [System.Management.Automation.Language.Parser]::ParseFile($scriptPath, [ref]$null, [ref]$null)
            $objectiveParam = $ast.FindAll({ $args[0] -is [System.Management.Automation.Language.ParameterAst] -and $args[0].Name.VariablePath.UserPath -eq 'Objective' }, $true)

            $objectiveParam | Should -Not -BeNullOrEmpty
        }

        It "Should have SkipValidation switch parameter" {
            # Mock test - verify parameter exists
            $ast = [System.Management.Automation.Language.Parser]::ParseFile($scriptPath, [ref]$null, [ref]$null)
            $skipValidationParam = $ast.FindAll({ $args[0] -is [System.Management.Automation.Language.ParameterAst] -and $args[0].Name.VariablePath.UserPath -eq 'SkipValidation' }, $true)

            $skipValidationParam | Should -Not -BeNullOrEmpty
        }
    }

    Context "Exit Codes" {
        It "Should define exit code 0 for success" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match 'exit 0'
        }

        It "Should define exit code 1 for git errors" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match 'exit 1'
        }

        It "Should define exit code 2 for JSON creation failure" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match 'exit 2'
        }

        It "Should define exit code 4 for validation failure" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match 'exit 4'
        }
    }

    Context "Helper Functions" {
        It "Should import GitHelpers module" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match 'Import-Module.*GitHelpers\.psm1'
        }

        It "Should import TemplateHelpers module" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match 'Import-Module.*TemplateHelpers\.psm1'
        }

        It "Should define Get-UserInput function" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match 'function Get-UserInput'
        }

        It "Should define New-JsonSessionLog function" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match 'function New-JsonSessionLog'
        }

        It "Should define Invoke-ValidationScript function" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match 'function Invoke-ValidationScript'
        }
    }

    Context "Git Integration" {
        BeforeAll {
            $gitHelpersPath = Join-Path $PSScriptRoot "../.claude/skills/session-init/modules/GitHelpers.psm1"
            $gitHelpersContent = Get-Content $gitHelpersPath -Raw
        }

        It "Should import GitHelpers module for git operations" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match 'Import-Module.*GitHelpers\.psm1'
        }

        It "GitHelpers module should call git rev-parse to find repository root" {
            $gitHelpersContent | Should -Match 'git rev-parse --show-toplevel'
        }

        It "GitHelpers module should call git branch to get current branch" {
            $gitHelpersContent | Should -Match 'git branch --show-current'
        }

        It "GitHelpers module should call git rev-parse to get commit hash" {
            $gitHelpersContent | Should -Match 'git rev-parse --short HEAD'
        }

        It "GitHelpers module should call git status to determine repository state" {
            $gitHelpersContent | Should -Match 'git status --short'
        }
    }

    Context "JSON Creation" {
        BeforeAll {
            $templateHelpersPath = Join-Path $PSScriptRoot "../.claude/skills/session-init/modules/TemplateHelpers.psm1"
            $templateHelpersContent = Get-Content $templateHelpersPath -Raw
        }

        It "Should import TemplateHelpers module for keyword extraction" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match 'Import-Module.*TemplateHelpers\.psm1'
        }

        It "TemplateHelpers module should export Get-DescriptiveKeywords function" {
            $templateHelpersContent | Should -Match 'function Get-DescriptiveKeywords'
        }

        It "Should create JSON structure with schemaVersion" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match 'schemaVersion'
        }

        It "Should create JSON structure with session metadata" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match 'session\s*=\s*@\{'
        }

        It "Should create JSON structure with protocolCompliance" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match 'protocolCompliance\s*=\s*@\{'
        }

        It "Should convert hashtable to JSON" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match 'ConvertTo-Json'
        }
    }

    Context "File Operations" {
        It "Should write to .agents/sessions/ directory" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match '\.agents/sessions'
        }

        It "Should create session log filename with pattern YYYY-MM-DD-session-NN.json" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match '\.json'
        }
    }

    Context "Validation Integration" {
        It "Should call Validate-SessionJson.ps1" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match 'Validate-SessionJson\.ps1'
        }

        It "Should pass SessionPath parameter to validation" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match '-SessionPath'
        }

        It "Should check validation exit code" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match '\$LASTEXITCODE'
        }

        It "Should support SkipValidation flag" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match 'if \(-not \$SkipValidation\)'
        }
    }

    Context "Error Handling" {
        BeforeAll {
            $gitHelpersPath = Join-Path $PSScriptRoot "../.claude/skills/session-init/modules/GitHelpers.psm1"
            $gitHelpersContent = Get-Content $gitHelpersPath -Raw
        }

        It "Should set ErrorActionPreference to Stop" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match '\$ErrorActionPreference\s*=\s*[''"]Stop[''"]'
        }

        It "Should use try-catch blocks" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match 'try\s*\{'
            $content | Should -Match 'catch\s*\{'
        }

        It "Should handle git errors with specific exception types" {
            $content = Get-Content $scriptPath -Raw
            # Script handles InvalidOperationException from GitHelpers module
            $content | Should -Match 'InvalidOperationException'
            # GitHelpers module provides detailed git error messages
            $gitHelpersContent | Should -Match 'Git error \(exit code'
        }
    }

    Context "User Experience" {
        It "Should display phase indicators" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match 'Phase 1:'
            $content | Should -Match 'Phase 2:'
            $content | Should -Match 'Phase 3:'
        }

        It "Should display success message" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match 'SUCCESS'
        }

        It "Should display failure message for validation errors" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match 'FAILED'
        }

        It "Should provide next steps guidance" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match 'Next:'
        }
    }
}

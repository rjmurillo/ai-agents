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

        It "Should define exit code 2 for template extraction failure" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match 'exit 2'
        }

        It "Should define exit code 3 for write failure" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match 'exit 3'
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

        It "Should define Invoke-TemplateExtraction function" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match 'function Invoke-TemplateExtraction'
        }

        It "Should define Write-SessionLogFile function" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match 'function Write-SessionLogFile'
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

    Context "Template Processing" {
        BeforeAll {
            $templateHelpersPath = Join-Path $PSScriptRoot "../.claude/skills/session-init/modules/TemplateHelpers.psm1"
            $templateHelpersContent = Get-Content $templateHelpersPath -Raw
        }

        It "Should call Extract-SessionTemplate.ps1" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match 'Extract-SessionTemplate\.ps1'
        }

        It "Should import TemplateHelpers module for template processing" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match 'Import-Module.*TemplateHelpers\.psm1'
        }

        It "TemplateHelpers module should replace NN placeholder" {
            $templateHelpersContent | Should -Match "-replace '\\bNN\\b'"
        }

        It "TemplateHelpers module should replace YYYY-MM-DD placeholder" {
            $templateHelpersContent | Should -Match "-replace 'YYYY-MM-DD'"
        }

        It "TemplateHelpers module should replace branch name placeholder" {
            $templateHelpersContent | Should -Match "-replace '\\\[branch name\\\]'"
        }

        It "TemplateHelpers module should replace SHA placeholder" {
            $templateHelpersContent | Should -Match "-replace '\\\[SHA\\\]'"
        }

        It "TemplateHelpers module should replace objective placeholder" {
            $templateHelpersContent | Should -Match "-replace '\\\[What this session aims to accomplish\\\]'"
        }

        It "TemplateHelpers module should replace git status placeholder" {
            $templateHelpersContent | Should -Match "-replace '\\\[clean/dirty\\\]'"
        }
    }

    Context "File Operations" {
        It "Should write to .agents/sessions/ directory" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match '\.agents/sessions'
        }

        It "Should create session log filename with pattern YYYY-MM-DD-session-NN.md" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match 'session-\$'
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
            $content | Should -Match 'Phase 4:'
            $content | Should -Match 'Phase 5:'
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

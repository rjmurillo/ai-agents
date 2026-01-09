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
        It "Should define Get-GitInfo function" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match 'function Get-GitInfo'
        }

        It "Should define Get-UserInput function" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match 'function Get-UserInput'
        }

        It "Should define Invoke-TemplateExtraction function" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match 'function Invoke-TemplateExtraction'
        }

        It "Should define New-PopulatedSessionLog function" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match 'function New-PopulatedSessionLog'
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
        It "Should call git rev-parse to find repository root" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match 'git rev-parse --show-toplevel'
        }

        It "Should call git branch to get current branch" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match 'git branch --show-current'
        }

        It "Should call git log to get commit hash" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match 'git log --oneline -1'
        }

        It "Should call git status to determine repository state" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match 'git status --short'
        }
    }

    Context "Template Processing" {
        It "Should call Extract-SessionTemplate.ps1" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match 'Extract-SessionTemplate\.ps1'
        }

        It "Should replace NN placeholder" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match "-replace '\\bNN\\b'"
        }

        It "Should replace YYYY-MM-DD placeholder" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match "-replace 'YYYY-MM-DD'"
        }

        It "Should replace branch name placeholder" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match "-replace '\\\[branch name\\\]'"
        }

        It "Should replace SHA placeholder" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match "-replace '\\\[SHA\\\]'"
        }

        It "Should replace objective placeholder" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match "-replace '\\\[What this session aims to accomplish\\\]'"
        }

        It "Should replace git status placeholder" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match "-replace '\\\[clean/dirty\\\]'"
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
        It "Should call Validate-SessionProtocol.ps1" {
            $content = Get-Content $scriptPath -Raw
            $content | Should -Match 'Validate-SessionProtocol\.ps1'
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
            $content | Should -Match 'InvalidOperationException'
            $content | Should -Match 'Git error \(exit code'
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

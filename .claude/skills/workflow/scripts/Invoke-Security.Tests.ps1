#!/usr/bin/env pwsh
#Requires -Module Pester

BeforeAll {
    $ScriptPath = Join-Path $PSScriptRoot 'Invoke-Security.ps1'
    $ModulePath = Join-Path $PSScriptRoot '../modules/WorkflowHelpers.psm1'
    Import-Module $ModulePath -Force
}

Describe 'Invoke-Security.ps1' {
    Context 'Syntax validation' {
        It 'has no parse errors' {
            $errors = $null
            $null = [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]([System.Management.Automation.Language.ParseError[]]$errors))
            $errors | Should -BeNullOrEmpty
        }

        It 'defines --owasp-only parameter' {
            $ast = [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]$null)
            $params = $ast.FindAll({ $args[0] -is [System.Management.Automation.Language.ParameterAst] }, $true)
            $params.Name.VariablePath.UserPath | Should -Contain 'OwaspOnly'
        }

        It 'defines --secrets-only parameter' {
            $ast = [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]$null)
            $params = $ast.FindAll({ $args[0] -is [System.Management.Automation.Language.ParameterAst] }, $true)
            $params.Name.VariablePath.UserPath | Should -Contain 'SecretsOnly'
        }
    }

    Context 'Check selection: default (all checks)' {
        It 'runs owasp, secrets, and deps checks by default' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match "'owasp',\s*'secrets',\s*'deps'"
        }
    }

    Context 'Check selection: --owasp-only' {
        It 'runs only owasp check when --owasp-only is set' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match "\`\$OwaspOnly.*@\('owasp'\)"
        }
    }

    Context 'Check selection: --secrets-only' {
        It 'runs only secrets check when --secrets-only is set' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match "\`\$SecretsOnly.*@\('secrets'\)"
        }
    }

    Context 'Security agent invocation' {
        It 'invokes security agent via MCP' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match "agent\s*=\s*'security'"
        }

        It 'uses opus model per ADR-013' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match "model\s*=\s*'opus'"
        }
    }

    Context 'Check execution loop' {
        It 'iterates over selected checks with status output' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match 'foreach\s*\(\$check\s+in\s+\$checks\)'
            $content | Should -Match "'owasp'\s*\{"
            $content | Should -Match "'secrets'\s*\{"
            $content | Should -Match "'deps'\s*\{"
        }
    }
}

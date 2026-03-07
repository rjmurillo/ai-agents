#!/usr/bin/env pwsh
#Requires -Module Pester

BeforeAll {
    $ScriptPath = Join-Path $PSScriptRoot 'Invoke-QA.ps1'
    $ModulePath = Join-Path $PSScriptRoot '../modules/WorkflowHelpers.psm1'
    Import-Module $ModulePath -Force
}

Describe 'Invoke-QA.ps1' {
    Context 'Syntax validation' {
        It 'has no parse errors' {
            $errors = $null
            $null = [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]([System.Management.Automation.Language.ParseError[]]$errors))
            $errors | Should -BeNullOrEmpty
        }

        It 'defines --coverage-threshold parameter' {
            $ast = [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]$null)
            $params = $ast.FindAll({ $args[0] -is [System.Management.Automation.Language.ParameterAst] }, $true)
            $params.Name.VariablePath.UserPath | Should -Contain 'CoverageThreshold'
        }
    }

    Context 'Coverage threshold' {
        It 'defaults coverage threshold to 80' {
            $ast = [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]$null)
            $params = $ast.FindAll({ $args[0] -is [System.Management.Automation.Language.ParameterAst] }, $true)
            $ctParam = $params | Where-Object { $_.Name.VariablePath.UserPath -eq 'CoverageThreshold' }
            $ctParam.DefaultValue.Value | Should -Be 80
        }

        It 'uses coverage threshold in validation output' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match '\$CoverageThreshold'
        }
    }

    Context 'Planning artifact checks' {
        It 'checks for planning artifacts in .agents/planning/' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match "\.agents/planning/"
        }

        It 'handles missing planning artifacts gracefully' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match 'SilentlyContinue|ErrorAction'
        }
    }

    Context 'QA agent invocation' {
        It 'invokes qa agent via MCP' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match "agent\s*=\s*'qa'"
        }

        It 'tracks handoff back to orchestrator' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match "from_agent\s*=\s*'qa'"
            $content | Should -Match "to_agent\s*=\s*'orchestrator'"
        }
    }

    Context 'Four-step verification process' {
        It 'runs 4 verification steps' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match '\[1/4\]'
            $content | Should -Match '\[2/4\]'
            $content | Should -Match '\[3/4\]'
            $content | Should -Match '\[4/4\]'
        }
    }
}

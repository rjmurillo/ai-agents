#!/usr/bin/env pwsh
#Requires -Module Pester

BeforeAll {
    $ScriptPath = Join-Path $PSScriptRoot 'Invoke-Plan.ps1'
    $ModulePath = Join-Path $PSScriptRoot '../modules/WorkflowHelpers.psm1'
    Import-Module $ModulePath -Force
}

Describe 'Invoke-Plan.ps1' {
    Context 'Syntax validation' {
        It 'has no parse errors' {
            $errors = $null
            $null = [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]([System.Management.Automation.Language.ParseError[]]$errors))
            $errors | Should -BeNullOrEmpty
        }

        It 'defines --arch switch parameter' {
            $ast = [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]$null)
            $params = $ast.FindAll({ $args[0] -is [System.Management.Automation.Language.ParameterAst] }, $true)
            $params.Name.VariablePath.UserPath | Should -Contain 'Arch'
        }

        It 'defines --strategic switch parameter' {
            $ast = [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]$null)
            $params = $ast.FindAll({ $args[0] -is [System.Management.Automation.Language.ParameterAst] }, $true)
            $params.Name.VariablePath.UserPath | Should -Contain 'Strategic'
        }
    }

    Context 'Validation' {
        It 'exits 3 when no task description is provided' {
            $tempDir = Join-Path ([IO.Path]::GetTempPath()) "plan-test-$(Get-Random)"
            New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
            try {
                & pwsh -NonInteractive -Command "
                    Set-Location '$tempDir'
                    `$env:AGENT_ORCHESTRATION_MCP_URL = `$null
                    & '$ScriptPath' 2>&1 | Out-Null
                    exit `$LASTEXITCODE
                "
                $LASTEXITCODE | Should -Be 3
            }
            finally {
                Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
            }
        }
    }

    Context 'Agent routing: default (planner)' {
        It 'routes to planner agent by default' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match "\`\$agentChain\s*=\s*@\('planner'\)"
        }
    }

    Context 'Agent routing: --arch (architect)' {
        It 'routes to architect agent when --arch flag is set' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match "\`\$agentChain\s*=\s*@\('architect'\)"
        }
    }

    Context 'Agent routing: --strategic (roadmap → high-level-advisor)' {
        It 'chains roadmap → high-level-advisor when --strategic flag is set' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match "'roadmap',\s*'high-level-advisor'"
        }
    }

    Context 'Workflow context integration' {
        It 'loads workflow context via Get-WorkflowContext' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match 'Get-WorkflowContext'
        }

        It 'passes context to agent invocations' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match 'context\s*=\s*\$ctx'
        }
    }
}

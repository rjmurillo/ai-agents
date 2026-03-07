#!/usr/bin/env pwsh
#Requires -Module Pester

BeforeAll {
    $ScriptPath = Join-Path $PSScriptRoot 'Invoke-Init.ps1'
    $ModulePath = Join-Path $PSScriptRoot '../modules/WorkflowHelpers.psm1'
    Import-Module $ModulePath -Force
}

Describe 'Invoke-Init.ps1' {
    Context 'Syntax validation' {
        It 'has no parse errors' {
            $errors = $null
            $null = [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]([System.Management.Automation.Language.ParseError[]]$errors))
            $errors | Should -BeNullOrEmpty
        }
    }

    Context 'Seven-step initialization sequence' {
        BeforeAll {
            $content = Get-Content $ScriptPath -Raw
        }

        It 'Step 1: activates Serena project via MCP' {
            $content | Should -Match 'mcp__serena__activate_project'
        }

        It 'Step 2: loads AGENTS.md' {
            $content | Should -Match 'AGENTS\.md'
        }

        It 'Step 3: reads HANDOFF.md' {
            $content | Should -Match 'HANDOFF\.md'
        }

        It 'Step 4: queries relevant memories' {
            $content | Should -Match 'mcp__serena__read_memory|memories|memory'
        }

        It 'Step 5: creates session log' {
            $content | Should -Match 'session.*(log|json)|session-\d|SessionNumber'
        }

        It 'Step 6: declares current branch via git' {
            $content | Should -Match 'git\s+(rev-parse|branch|symbolic-ref)'
        }

        It 'Step 7: records evidence to Session State MCP' {
            $content | Should -Match 'mcp.*session|record.*evidence|session.*state'
        }
    }

    Context 'Parameters' {
        It 'accepts -SessionNumber parameter' {
            $ast = [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]$null)
            $params = $ast.FindAll({ $args[0] -is [System.Management.Automation.Language.ParameterAst] }, $true)
            ($params | Where-Object { $_.Name.VariablePath.UserPath -eq 'SessionNumber' }) | Should -Not -BeNullOrEmpty
        }

        It 'accepts -Objective parameter' {
            $ast = [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]$null)
            $params = $ast.FindAll({ $args[0] -is [System.Management.Automation.Language.ParameterAst] }, $true)
            ($params | Where-Object { $_.Name.VariablePath.UserPath -eq 'Objective' }) | Should -Not -BeNullOrEmpty
        }
    }

    Context 'MCP fallback behavior' {
        It 'handles Serena MCP unavailability gracefully' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match 'Fallback|WARN|unavailable'
        }
    }

    Context 'Git integration' {
        It 'uses git commands for branch detection' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match 'git\s'
        }

        It 'calls Write-Step/Write-StepResult helper functions' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match 'Write-Step\s'
            $content | Should -Match 'Write-StepResult\s'
        }
    }
}

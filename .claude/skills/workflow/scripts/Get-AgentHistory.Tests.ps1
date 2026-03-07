#!/usr/bin/env pwsh
#Requires -Module Pester

BeforeAll { $ScriptPath = Join-Path $PSScriptRoot 'Get-AgentHistory.ps1' }

Describe 'Get-AgentHistory.ps1' {
    It 'has no parse errors' {
        $errors = $null
        $null = [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]([System.Management.Automation.Language.ParseError[]]$errors))
        $errors | Should -BeNullOrEmpty
    }
    It 'defines -Limit parameter with default 50' {
        $ast = [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]$null)
        $params = $ast.FindAll({ $args[0] -is [System.Management.Automation.Language.ParameterAst] }, $true)
        $limitParam = $params | Where-Object { $_.Name.VariablePath.UserPath -eq 'Limit' }
        $limitParam | Should -Not -BeNullOrEmpty
    }
}

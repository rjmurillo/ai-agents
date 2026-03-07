#!/usr/bin/env pwsh
#Requires -Module Pester

BeforeAll { $ScriptPath = Join-Path $PSScriptRoot 'Invoke-WorkflowCommand.ps1' }

Describe 'Invoke-WorkflowCommand.ps1' {
    It 'has no parse errors' {
        $errors = $null
        $null = [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]([System.Management.Automation.Language.ParseError[]]$errors))
        $errors | Should -BeNullOrEmpty
    }
    It 'defines -Command parameter as mandatory' {
        $ast = [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]$null)
        $params = $ast.FindAll({ $args[0] -is [System.Management.Automation.Language.ParameterAst] }, $true)
        $cmdParam = $params | Where-Object { $_.Name.VariablePath.UserPath -eq 'Command' }
        $cmdParam | Should -Not -BeNullOrEmpty
    }
}

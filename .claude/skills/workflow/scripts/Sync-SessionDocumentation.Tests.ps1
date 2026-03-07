#!/usr/bin/env pwsh
#Requires -Module Pester

BeforeAll { $ScriptPath = Join-Path $PSScriptRoot 'Sync-SessionDocumentation.ps1' }

Describe 'Sync-SessionDocumentation.ps1' {
    It 'has no parse errors' {
        $errors = $null
        $null = [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]([System.Management.Automation.Language.ParseError[]]$errors))
        $errors | Should -BeNullOrEmpty
    }
    It 'defines -SessionLogPath as mandatory' {
        $ast = [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]$null)
        $params = $ast.FindAll({ $args[0] -is [System.Management.Automation.Language.ParameterAst] }, $true)
        $param = $params | Where-Object { $_.Name.VariablePath.UserPath -eq 'SessionLogPath' }
        $param | Should -Not -BeNullOrEmpty
    }
    It 'exits 3 when session log not found' {
        $result = & pwsh -NonInteractive -Command "
            & '$ScriptPath' -SessionLogPath 'nonexistent-file-xyz.json'
            exit `$LASTEXITCODE
        "
        $LASTEXITCODE | Should -Be 3
    }
}

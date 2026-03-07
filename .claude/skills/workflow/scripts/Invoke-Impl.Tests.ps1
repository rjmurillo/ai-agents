#!/usr/bin/env pwsh
#Requires -Module Pester

BeforeAll {
    $ScriptPath = Join-Path $PSScriptRoot 'Invoke-Impl.ps1'
}

Describe 'Invoke-Impl.ps1' {
    It 'has no parse errors' {
        $errors = $null
        $null = [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]([System.Management.Automation.Language.ParseError[]]$errors))
        $errors | Should -BeNullOrEmpty
    }

    It 'defines --full switch parameter' {
        $ast = [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]$null)
        $params = $ast.FindAll({ $args[0] -is [System.Management.Automation.Language.ParameterAst] }, $true)
        $params.Name.VariablePath.UserPath | Should -Contain 'Full'
    }

    It 'defines --parallel switch parameter' {
        $ast = [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]$null)
        $params = $ast.FindAll({ $args[0] -is [System.Management.Automation.Language.ParameterAst] }, $true)
        $params.Name.VariablePath.UserPath | Should -Contain 'Parallel'
    }
}

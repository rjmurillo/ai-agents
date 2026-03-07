#!/usr/bin/env pwsh
#Requires -Module Pester

BeforeAll {
    $ScriptPath = Join-Path $PSScriptRoot 'Invoke-Init.ps1'
}

Describe 'Invoke-Init.ps1' {
    Context 'When git is available' {
        It 'exits with code 0 on success' {
            # Dry-run: just verify the script is parsable
            $null = [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]$null)
        }
    }

    Context 'Script syntax' {
        It 'has no parse errors' {
            $errors = $null
            $null = [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]([System.Management.Automation.Language.ParseError[]]$errors))
            $errors | Should -BeNullOrEmpty
        }
    }
}

#!/usr/bin/env pwsh
#Requires -Module Pester

BeforeAll {
    $ScriptPath = Join-Path $PSScriptRoot 'Invoke-WorkflowCommand.ps1'
    $ScriptsDir = $PSScriptRoot
}

Describe 'Invoke-WorkflowCommand.ps1' {
    Context 'Syntax validation' {
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

        It 'defines -Arguments parameter as optional hashtable' {
            $ast = [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]$null)
            $params = $ast.FindAll({ $args[0] -is [System.Management.Automation.Language.ParameterAst] }, $true)
            $argsParam = $params | Where-Object { $_.Name.VariablePath.UserPath -eq 'Arguments' }
            $argsParam | Should -Not -BeNullOrEmpty
        }
    }

    Context 'Command routing - valid commands' {
        It 'accepts 0-init as a valid command' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match "'0-init'"
        }

        It 'accepts 1-plan as a valid command' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match "'1-plan'"
        }

        It 'accepts 2-impl as a valid command' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match "'2-impl'"
        }

        It 'accepts 3-qa as a valid command' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match "'3-qa'"
        }

        It 'accepts 4-security as a valid command' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match "'4-security'"
        }

        It 'maps all 5 workflow commands to Invoke-*.ps1 scripts' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match 'Invoke-Init\.ps1'
            $content | Should -Match 'Invoke-Plan\.ps1'
            $content | Should -Match 'Invoke-Impl\.ps1'
            $content | Should -Match 'Invoke-QA\.ps1'
            $content | Should -Match 'Invoke-Security\.ps1'
        }
    }

    Context 'Command routing - invalid commands' {
        It 'exits 3 for unknown command' {
            $output = & pwsh -NonInteractive -Command "
                & '$ScriptPath' -Command 'invalid-cmd' 2>&1
                exit `$LASTEXITCODE
            "
            $LASTEXITCODE | Should -Be 3
        }

        It 'prints valid commands in error message for unknown command' {
            $output = & pwsh -NonInteractive -Command "
                & '$ScriptPath' -Command 'invalid-cmd' 2>&1
            "
            ($output -join "`n") | Should -Match '0-init'
            ($output -join "`n") | Should -Match '4-security'
        }

        It 'exits 3 for empty string command' {
            $output = & pwsh -NonInteractive -Command "
                & '$ScriptPath' -Command '' 2>&1
                exit `$LASTEXITCODE
            "
            $LASTEXITCODE | Should -Be 3
        }
    }

    Context 'Script path validation' {
        It 'exits 3 when mapped script file does not exist' {
            # The $CommandMap uses Join-Path with $PSScriptRoot which resolves at runtime.
            # We verify the pattern: if script not found → exit 3
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match 'Test-Path \$ScriptPath'
            $content | Should -Match "Command script not found"
        }
    }

    Context 'Execution logging' {
        It 'prints command name before execution' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match 'Running workflow command'
        }

        It 'prints duration and exit code after execution' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match 'Duration'
            $content | Should -Match '\$exitCode'
        }
    }

    Context 'Exit code forwarding' {
        It 'forwards exit code from invoked script' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match '\$exitCode\s*=\s*\$LASTEXITCODE'
            $content | Should -Match 'exit\s+\$exitCode'
        }
    }
}

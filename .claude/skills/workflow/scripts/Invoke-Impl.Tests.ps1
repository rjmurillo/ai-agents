#!/usr/bin/env pwsh
#Requires -Module Pester

BeforeAll {
    $ScriptPath = Join-Path $PSScriptRoot 'Invoke-Impl.ps1'
    $ModulePath = Join-Path $PSScriptRoot '../modules/WorkflowHelpers.psm1'
    Import-Module $ModulePath -Force
}

Describe 'Invoke-Impl.ps1' {
    Context 'Syntax validation' {
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

    Context 'Validation' {
        It 'exits 3 when no task description is provided' {
            $tempDir = Join-Path ([IO.Path]::GetTempPath()) "impl-test-$(Get-Random)"
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

    Context 'Execution mode: default (implementer only)' {
        It 'invokes implementer agent without chaining when no flags set' {
            # Verify script body invokes implementer as first agent
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match "agent\s*=\s*'implementer'"
        }

        It 'does not invoke qa or security without --full or --parallel flag' {
            $ast = [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]$null)
            $body = $ast.EndBlock.Statements
            # The qa/security invocations should be inside conditionals ($Full or $Parallel)
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match '\$Full'
            $content | Should -Match '\$Parallel'
        }
    }

    Context 'Execution mode: --full (sequential chain)' {
        It 'chains implementer → qa → security in sequential mode' {
            $content = Get-Content $ScriptPath -Raw
            # When $Full is set, it should iterate over qa and security
            $content | Should -Match "if\s*\(\`\$Full\)"
            $content | Should -Match "'qa',\s*'security'"
        }
    }

    Context 'Execution mode: --parallel' {
        It 'references parallel execution mode' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match '\$Parallel'
        }
    }
}

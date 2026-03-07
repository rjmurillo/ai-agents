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

        It 'defines --coverage-threshold parameter with default 80' {
            $ast = [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]$null)
            $params = $ast.FindAll({ $args[0] -is [System.Management.Automation.Language.ParameterAst] }, $true)
            $ctParam = $params | Where-Object { $_.Name.VariablePath.UserPath -eq 'CoverageThreshold' }
            $ctParam | Should -Not -BeNullOrEmpty
            $ctParam.DefaultValue.Value | Should -Be 80
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
        It 'runs steps 1 through 4' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match '\[1/4\].*QA agent'
            $content | Should -Match '\[2/4\].*coverage'
            $content | Should -Match '\[3/4\].*acceptance criteria'
            $content | Should -Match '\[4/4\].*complete'
        }
    }

    Context 'Coverage threshold handling' {
        It 'displays the configured coverage threshold' {
            $tempDir = Join-Path ([IO.Path]::GetTempPath()) "qa-test-$(Get-Random)"
            New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
            try {
                $output = & pwsh -NonInteractive -Command "
                    Set-Location '$tempDir'
                    `$env:AGENT_ORCHESTRATION_MCP_URL = `$null
                    & '$ScriptPath' -CoverageThreshold 90 'test scope' 2>&1
                    exit `$LASTEXITCODE
                "
                $LASTEXITCODE | Should -Be 0
                ($output -join "`n") | Should -Match 'Coverage threshold:.*90%'
                ($output -join "`n") | Should -Match '90% required'
            }
            finally {
                Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
            }
        }

        It 'uses default 80% threshold when not specified' {
            $tempDir = Join-Path ([IO.Path]::GetTempPath()) "qa-test-$(Get-Random)"
            New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
            try {
                $output = & pwsh -NonInteractive -Command "
                    Set-Location '$tempDir'
                    `$env:AGENT_ORCHESTRATION_MCP_URL = `$null
                    & '$ScriptPath' 'test scope' 2>&1
                    exit `$LASTEXITCODE
                "
                $LASTEXITCODE | Should -Be 0
                ($output -join "`n") | Should -Match 'Coverage threshold:.*80%'
            }
            finally {
                Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
            }
        }
    }

    Context 'Planning artifact checks' {
        It 'reports found planning artifacts when they exist' {
            $tempDir = Join-Path ([IO.Path]::GetTempPath()) "qa-test-$(Get-Random)"
            New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
            $planDir = Join-Path $tempDir '.agents/planning'
            New-Item -ItemType Directory -Path $planDir -Force | Out-Null
            New-Item -ItemType File -Path (Join-Path $planDir 'spec.md') -Value 'test' -Force | Out-Null
            try {
                $output = & pwsh -NonInteractive -Command "
                    Set-Location '$tempDir'
                    `$env:AGENT_ORCHESTRATION_MCP_URL = `$null
                    & '$ScriptPath' 'verify' 2>&1
                    exit `$LASTEXITCODE
                "
                $LASTEXITCODE | Should -Be 0
                ($output -join "`n") | Should -Match 'Planning artifacts found.*spec\.md'
            }
            finally {
                Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
            }
        }

        It 'warns when no planning artifacts found' {
            $tempDir = Join-Path ([IO.Path]::GetTempPath()) "qa-test-$(Get-Random)"
            New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
            try {
                $output = & pwsh -NonInteractive -Command "
                    Set-Location '$tempDir'
                    `$env:AGENT_ORCHESTRATION_MCP_URL = `$null
                    & '$ScriptPath' 'verify' 2>&1
                    exit `$LASTEXITCODE
                "
                $LASTEXITCODE | Should -Be 0
                ($output -join "`n") | Should -Match 'No planning artifacts found'
            }
            finally {
                Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
            }
        }
    }

    Context 'Workflow context update' {
        It 'persists LastCommand as 3-qa' {
            $tempDir = Join-Path ([IO.Path]::GetTempPath()) "qa-test-$(Get-Random)"
            New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
            try {
                & pwsh -NonInteractive -Command "
                    Set-Location '$tempDir'
                    `$env:AGENT_ORCHESTRATION_MCP_URL = `$null
                    & '$ScriptPath' 'test' 2>&1 | Out-Null
                    exit `$LASTEXITCODE
                "
                $ctxPath = Join-Path $tempDir '.agents/workflow-context.json'
                Test-Path $ctxPath | Should -BeTrue
                $ctx = Get-Content $ctxPath -Raw | ConvertFrom-Json
                $ctx.LastCommand | Should -Be '3-qa'
            }
            finally {
                Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
            }
        }
    }

    Context 'Completion output' {
        It 'prints completion message suggesting /4-security' {
            $tempDir = Join-Path ([IO.Path]::GetTempPath()) "qa-test-$(Get-Random)"
            New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
            try {
                $output = & pwsh -NonInteractive -Command "
                    Set-Location '$tempDir'
                    `$env:AGENT_ORCHESTRATION_MCP_URL = `$null
                    & '$ScriptPath' 'test' 2>&1
                    exit `$LASTEXITCODE
                "
                ($output -join "`n") | Should -Match 'QA complete.*4-security'
            }
            finally {
                Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
            }
        }
    }
}

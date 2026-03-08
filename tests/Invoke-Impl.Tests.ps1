#!/usr/bin/env pwsh
#Requires -Module Pester

BeforeAll {
    $ScriptPath = Join-Path $PSScriptRoot '../.claude/skills/workflow/scripts/Invoke-Impl.ps1'
    $ModulePath = Join-Path $PSScriptRoot '../.claude/skills/workflow/modules/WorkflowHelpers.psm1'
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

    Context 'Validation - no task provided' {
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

        It 'prints usage hint when no task given' {
            $tempDir = Join-Path ([IO.Path]::GetTempPath()) "impl-test-$(Get-Random)"
            New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
            try {
                $output = & pwsh -NonInteractive -Command "
                    Set-Location '$tempDir'
                    `$env:AGENT_ORCHESTRATION_MCP_URL = `$null
                    & '$ScriptPath' 2>&1
                "
                ($output -join "`n") | Should -Match 'Usage.*2-impl'
            }
            finally {
                Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
            }
        }
    }

    Context 'Default mode - implementer only' {
        It 'invokes implementer agent with task text' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match "agent\s*=\s*'implementer'"
        }

        It 'exits 0 in default mode with valid task and MCP config' {
            $tempDir = Join-Path ([IO.Path]::GetTempPath()) "impl-test-$(Get-Random)"
            New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
            New-Item -ItemType File -Path (Join-Path $tempDir 'mcp.json') -Value '{}' -Force | Out-Null
            try {
                $output = & pwsh -NonInteractive -Command "
                    Set-Location '$tempDir'
                    & '$ScriptPath' 'Add login form' 2>&1
                    exit `$LASTEXITCODE
                "
                $LASTEXITCODE | Should -Be 0
                ($output -join "`n") | Should -Match 'Implementing.*Add login form'
                ($output -join "`n") | Should -Match 'Implementation complete'
            }
            finally {
                Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
            }
        }

        It 'shows MCP fallback warning when MCP unavailable but still succeeds' {
            $tempDir = Join-Path ([IO.Path]::GetTempPath()) "impl-test-$(Get-Random)"
            New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
            try {
                $output = & pwsh -NonInteractive -Command "
                    Set-Location '$tempDir'
                    `$env:AGENT_ORCHESTRATION_MCP_URL = `$null
                    & '$ScriptPath' 'Fix bug' 2>&1
                    exit `$LASTEXITCODE
                "
                $LASTEXITCODE | Should -Be 0
                ($output -join "`n") | Should -Match 'unavailable'
            }
            finally {
                Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
            }
        }
    }

    Context 'Full sequential mode (--full)' {
        It 'chains implementer → qa → security' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match 'if\s*\(\$Full\)'
            $content | Should -Match "'qa',\s*'security'"
        }

        It 'tracks handoff from implementer to chained agents' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match "from_agent\s*=\s*'implementer'"
        }

        It 'runs full chain and exits 0' {
            $tempDir = Join-Path ([IO.Path]::GetTempPath()) "impl-test-$(Get-Random)"
            New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
            New-Item -ItemType File -Path (Join-Path $tempDir 'mcp.json') -Value '{}' -Force | Out-Null
            try {
                $output = & pwsh -NonInteractive -Command "
                    Set-Location '$tempDir'
                    & '$ScriptPath' -Full 'Add auth' 2>&1
                    exit `$LASTEXITCODE
                "
                $LASTEXITCODE | Should -Be 0
                ($output -join "`n") | Should -Match 'full sequential chain'
                ($output -join "`n") | Should -Match 'qa'
                ($output -join "`n") | Should -Match 'security'
            }
            finally {
                Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
            }
        }
    }

    Context 'Parallel mode (--parallel)' {
        It 'starts parallel execution for qa and security' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match 'start_parallel_execution'
            $content | Should -Match "agents\s*=.*'qa',\s*'security'"
        }

        It 'aggregates parallel results' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match 'aggregate_parallel_results'
        }

        It 'runs parallel mode and exits 0' {
            $tempDir = Join-Path ([IO.Path]::GetTempPath()) "impl-test-$(Get-Random)"
            New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
            New-Item -ItemType File -Path (Join-Path $tempDir 'mcp.json') -Value '{}' -Force | Out-Null
            try {
                $output = & pwsh -NonInteractive -Command "
                    Set-Location '$tempDir'
                    & '$ScriptPath' -Parallel 'Add auth' 2>&1
                    exit `$LASTEXITCODE
                "
                $LASTEXITCODE | Should -Be 0
                ($output -join "`n") | Should -Match 'parallel'
            }
            finally {
                Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
            }
        }
    }

    Context 'Workflow context update' {
        It 'updates LastCommand to 2-impl' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match "'LastCommand'.*'2-impl'"
        }

        It 'stores ImplTask in context' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match "'ImplTask'"
        }

        It 'persists workflow context file after execution' {
            $tempDir = Join-Path ([IO.Path]::GetTempPath()) "impl-test-$(Get-Random)"
            New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
            try {
                & pwsh -NonInteractive -Command "
                    Set-Location '$tempDir'
                    `$env:AGENT_ORCHESTRATION_MCP_URL = `$null
                    & '$ScriptPath' 'test task' 2>&1 | Out-Null
                    exit `$LASTEXITCODE
                "
                $ctxPath = Join-Path $tempDir '.agents/workflow-context.json'
                Test-Path $ctxPath | Should -BeTrue
                $ctx = Get-Content $ctxPath -Raw | ConvertFrom-Json
                $ctx.LastCommand | Should -Be '2-impl'
                $ctx.ImplTask | Should -Be 'test task'
            }
            finally {
                Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
            }
        }
    }
}

#!/usr/bin/env pwsh
#Requires -Module Pester

BeforeAll {
    $ScriptPath = Join-Path $PSScriptRoot '../.claude/skills/workflow/scripts/Invoke-Plan.ps1'
    $ModulePath = Join-Path $PSScriptRoot '../.claude/skills/workflow/modules/WorkflowHelpers.psm1'
    Import-Module $ModulePath -Force
}

Describe 'Invoke-Plan.ps1' {
    Context 'Syntax validation' {
        It 'has no parse errors' {
            $errors = $null
            $null = [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]([System.Management.Automation.Language.ParseError[]]$errors))
            $errors | Should -BeNullOrEmpty
        }

        It 'defines --arch switch parameter' {
            $ast = [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]$null)
            $params = $ast.FindAll({ $args[0] -is [System.Management.Automation.Language.ParameterAst] }, $true)
            $params.Name.VariablePath.UserPath | Should -Contain 'Arch'
        }

        It 'defines --strategic switch parameter' {
            $ast = [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]$null)
            $params = $ast.FindAll({ $args[0] -is [System.Management.Automation.Language.ParameterAst] }, $true)
            $params.Name.VariablePath.UserPath | Should -Contain 'Strategic'
        }
    }

    Context 'Validation - no task provided' {
        It 'exits 3 when no task description is provided' {
            $tempDir = Join-Path ([IO.Path]::GetTempPath()) "plan-test-$(Get-Random)"
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
            $tempDir = Join-Path ([IO.Path]::GetTempPath()) "plan-test-$(Get-Random)"
            New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
            try {
                $output = & pwsh -NonInteractive -Command "
                    Set-Location '$tempDir'
                    `$env:AGENT_ORCHESTRATION_MCP_URL = `$null
                    & '$ScriptPath' 2>&1
                "
                ($output -join "`n") | Should -Match 'Usage.*1-plan'
            }
            finally {
                Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
            }
        }
    }

    Context 'Agent routing: default (planner)' {
        It 'routes to planner agent by default' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match '\$agentChain\s*=\s*@\(''planner''\)'
        }

        It 'displays Default route description' {
            $tempDir = Join-Path ([IO.Path]::GetTempPath()) "plan-test-$(Get-Random)"
            New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
            try {
                $output = & pwsh -NonInteractive -Command "
                    Set-Location '$tempDir'
                    `$env:AGENT_ORCHESTRATION_MCP_URL = `$null
                    & '$ScriptPath' 'Design auth flow' 2>&1
                    exit `$LASTEXITCODE
                "
                $LASTEXITCODE | Should -Be 0
                ($output -join "`n") | Should -Match 'Route:.*Default.*planner'
                ($output -join "`n") | Should -Match 'Planning complete'
            }
            finally {
                Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
            }
        }
    }

    Context 'Agent routing: --arch (architect)' {
        It 'routes to architect agent when --arch flag is set' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match '\$agentChain\s*=\s*@\(''architect''\)'
        }

        It 'displays Architecture route description' {
            $tempDir = Join-Path ([IO.Path]::GetTempPath()) "plan-test-$(Get-Random)"
            New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
            try {
                $output = & pwsh -NonInteractive -Command "
                    Set-Location '$tempDir'
                    `$env:AGENT_ORCHESTRATION_MCP_URL = `$null
                    & '$ScriptPath' -Arch 'Review architecture' 2>&1
                    exit `$LASTEXITCODE
                "
                $LASTEXITCODE | Should -Be 0
                ($output -join "`n") | Should -Match 'Route:.*Architecture.*architect'
            }
            finally {
                Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
            }
        }
    }

    Context 'Agent routing: --strategic (roadmap → high-level-advisor)' {
        It 'chains roadmap → high-level-advisor when --strategic flag is set' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match "'roadmap',\s*'high-level-advisor'"
        }

        It 'tracks handoff between chained agents' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match 'track_handoff'
            $content | Should -Match 'Strategic planning chain'
        }

        It 'displays Strategic route description' {
            $tempDir = Join-Path ([IO.Path]::GetTempPath()) "plan-test-$(Get-Random)"
            New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
            try {
                $output = & pwsh -NonInteractive -Command "
                    Set-Location '$tempDir'
                    `$env:AGENT_ORCHESTRATION_MCP_URL = `$null
                    & '$ScriptPath' -Strategic 'Q2 priorities' 2>&1
                    exit `$LASTEXITCODE
                "
                $LASTEXITCODE | Should -Be 0
                ($output -join "`n") | Should -Match 'Route:.*Strategic'
                ($output -join "`n") | Should -Match 'roadmap'
                ($output -join "`n") | Should -Match 'high-level-advisor'
            }
            finally {
                Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
            }
        }
    }

    Context 'Workflow context integration' {
        It 'loads workflow context via Get-WorkflowContext' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match 'Get-WorkflowContext'
        }

        It 'passes context to agent invocations' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match 'context\s*=\s*\$ctx'
        }

        It 'persists LastCommand as 1-plan and PlanningAgent' {
            $tempDir = Join-Path ([IO.Path]::GetTempPath()) "plan-test-$(Get-Random)"
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
                $ctx.LastCommand | Should -Be '1-plan'
                $ctx.PlanningAgent | Should -Be 'planner'
                $ctx.PlanningTask | Should -Be 'test task'
            }
            finally {
                Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
            }
        }
    }
}

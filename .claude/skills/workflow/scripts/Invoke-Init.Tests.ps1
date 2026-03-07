#!/usr/bin/env pwsh
#Requires -Module Pester

BeforeAll {
    $ScriptPath = Join-Path $PSScriptRoot 'Invoke-Init.ps1'
    $ModulePath = Join-Path $PSScriptRoot '../modules/WorkflowHelpers.psm1'
    Import-Module $ModulePath -Force
}

Describe 'Invoke-Init.ps1' {
    Context 'Syntax validation' {
        It 'has no parse errors' {
            $errors = $null
            $null = [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]([System.Management.Automation.Language.ParseError[]]$errors))
            $errors | Should -BeNullOrEmpty
        }

        It 'accepts -SessionNumber parameter' {
            $ast = [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]$null)
            $params = $ast.FindAll({ $args[0] -is [System.Management.Automation.Language.ParameterAst] }, $true)
            ($params | Where-Object { $_.Name.VariablePath.UserPath -eq 'SessionNumber' }) | Should -Not -BeNullOrEmpty
        }

        It 'accepts -Objective parameter' {
            $ast = [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]$null)
            $params = $ast.FindAll({ $args[0] -is [System.Management.Automation.Language.ParameterAst] }, $true)
            ($params | Where-Object { $_.Name.VariablePath.UserPath -eq 'Objective' }) | Should -Not -BeNullOrEmpty
        }
    }

    Context 'Seven-step initialization sequence' {
        BeforeAll {
            $content = Get-Content $ScriptPath -Raw
        }

        It 'Step 1: activates Serena project via MCP' {
            $content | Should -Match 'mcp__serena__activate_project'
        }

        It 'Step 2: loads AGENTS.md' {
            $content | Should -Match 'AGENTS\.md'
        }

        It 'Step 3: reads HANDOFF.md' {
            $content | Should -Match 'HANDOFF\.md'
        }

        It 'Step 4: queries relevant memories' {
            $content | Should -Match 'mcp__serena__list_memories'
        }

        It 'Step 5: creates session log' {
            $content | Should -Match 'New-SessionLog\.ps1'
        }

        It 'Step 6: declares current branch via git' {
            $content | Should -Match 'git\s+branch\s+--show-current'
        }

        It 'Step 7: records evidence to Session State MCP' {
            $content | Should -Match 'mcp__session_state__record_evidence'
        }
    }

    Context 'MCP fallback behavior' {
        It 'handles Serena MCP unavailability with WARN status' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match "WARN.*Serena MCP unavailable"
        }

        It 'handles Session State MCP unavailability with WARN status' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match "WARN.*Session State MCP unavailable"
        }

        It 'handles memory query failure gracefully' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match "WARN.*Memory query skipped"
        }
    }

    Context 'Git integration' {
        It 'runs git branch --show-current' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match 'git branch --show-current'
        }

        It 'exits 1 on git failure' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match 'exit 1'
        }
    }

    Context 'End-to-end initialization in git repo' {
        It 'completes initialization and persists workflow context' {
            $tempDir = Join-Path ([IO.Path]::GetTempPath()) "init-test-$(Get-Random)"
            New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
            try {
                # Initialize a git repo so branch detection works
                & git -C $tempDir init --initial-branch main 2>&1 | Out-Null
                & git -C $tempDir config user.email "test@test.com" 2>&1 | Out-Null
                & git -C $tempDir config user.name "Test" 2>&1 | Out-Null
                & git -C $tempDir commit --allow-empty -m "init" 2>&1 | Out-Null

                $output = & pwsh -NonInteractive -Command "
                    Set-Location '$tempDir'
                    `$env:AGENT_ORCHESTRATION_MCP_URL = `$null
                    & '$ScriptPath' 2>&1
                    exit `$LASTEXITCODE
                "
                $LASTEXITCODE | Should -Be 0
                ($output -join "`n") | Should -Match 'Branch:.*main'
                ($output -join "`n") | Should -Match 'Session initialized'

                # Verify workflow context was persisted
                $ctxPath = Join-Path $tempDir '.agents/workflow-context.json'
                Test-Path $ctxPath | Should -BeTrue
                $ctx = Get-Content $ctxPath -Raw | ConvertFrom-Json
                $ctx.LastCommand | Should -Be '0-init'
                $ctx.Branch | Should -Be 'main'
            }
            finally {
                Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
            }
        }
    }

    Context 'AGENTS.md and HANDOFF.md detection' {
        It 'reports OK when AGENTS.md exists' {
            $tempDir = Join-Path ([IO.Path]::GetTempPath()) "init-test-$(Get-Random)"
            New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
            & git -C $tempDir init --initial-branch main 2>&1 | Out-Null
            & git -C $tempDir config user.email "test@test.com" 2>&1 | Out-Null
            & git -C $tempDir config user.name "Test" 2>&1 | Out-Null
            & git -C $tempDir commit --allow-empty -m "init" 2>&1 | Out-Null
            Set-Content (Join-Path $tempDir 'AGENTS.md') '# Agents' -Encoding UTF8
            try {
                $output = & pwsh -NonInteractive -Command "
                    Set-Location '$tempDir'
                    `$env:AGENT_ORCHESTRATION_MCP_URL = `$null
                    & '$ScriptPath' 2>&1
                "
                ($output -join "`n") | Should -Match 'OK.*AGENTS\.md loaded'
            }
            finally {
                Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
            }
        }

        It 'reports WARN when HANDOFF.md not found' {
            $tempDir = Join-Path ([IO.Path]::GetTempPath()) "init-test-$(Get-Random)"
            New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
            & git -C $tempDir init --initial-branch main 2>&1 | Out-Null
            & git -C $tempDir config user.email "test@test.com" 2>&1 | Out-Null
            & git -C $tempDir config user.name "Test" 2>&1 | Out-Null
            & git -C $tempDir commit --allow-empty -m "init" 2>&1 | Out-Null
            try {
                $output = & pwsh -NonInteractive -Command "
                    Set-Location '$tempDir'
                    `$env:AGENT_ORCHESTRATION_MCP_URL = `$null
                    & '$ScriptPath' 2>&1
                "
                ($output -join "`n") | Should -Match 'WARN.*HANDOFF\.md not found'
            }
            finally {
                Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
            }
        }
    }

    Context 'Helper function usage' {
        It 'uses Write-Step for status output' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match 'Write-Step\s'
        }

        It 'uses Write-StepResult for step outcomes' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match 'Write-StepResult\s'
        }
    }
}

#!/usr/bin/env pwsh
#Requires -Module Pester

BeforeAll {
    $ScriptPath = Join-Path $PSScriptRoot '../.claude/skills/workflow/scripts/Invoke-Security.ps1'
    $ModulePath = Join-Path $PSScriptRoot '../.claude/skills/workflow/modules/WorkflowHelpers.psm1'
    Import-Module $ModulePath -Force
}

Describe 'Invoke-Security.ps1' {
    Context 'Syntax validation' {
        It 'has no parse errors' {
            $errors = $null
            $null = [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]([System.Management.Automation.Language.ParseError[]]$errors))
            $errors | Should -BeNullOrEmpty
        }

        It 'defines --owasp-only parameter with alias' {
            $ast = [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]$null)
            $params = $ast.FindAll({ $args[0] -is [System.Management.Automation.Language.ParameterAst] }, $true)
            $params.Name.VariablePath.UserPath | Should -Contain 'OwaspOnly'
        }

        It 'defines --secrets-only parameter with alias' {
            $ast = [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]$null)
            $params = $ast.FindAll({ $args[0] -is [System.Management.Automation.Language.ParameterAst] }, $true)
            $params.Name.VariablePath.UserPath | Should -Contain 'SecretsOnly'
        }
    }

    Context 'Default execution — all checks (owasp, secrets, deps)' {
        It 'runs all three checks and exits 0' {
            $tempDir = Join-Path ([IO.Path]::GetTempPath()) "sec-test-$(Get-Random)"
            New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
            try {
                $output = & pwsh -NonInteractive -Command "
                    Set-Location '$tempDir'
                    `$env:AGENT_ORCHESTRATION_MCP_URL = `$null
                    & '$ScriptPath' 'full scope' 2>&1
                    exit `$LASTEXITCODE
                "
                $LASTEXITCODE | Should -Be 0
                $text = $output -join "`n"
                $text | Should -Match 'OWASP Top 10'
                $text | Should -Match 'Secret detection'
                $text | Should -Match 'Dependency vulnerability'
                $text | Should -Match 'Checks:.*owasp.*secrets.*deps'
            }
            finally {
                Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
            }
        }
    }

    Context 'Check selection: --owasp-only' {
        It 'runs only OWASP check and skips secrets and deps' {
            $tempDir = Join-Path ([IO.Path]::GetTempPath()) "sec-test-$(Get-Random)"
            New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
            try {
                $output = & pwsh -NonInteractive -Command "
                    Set-Location '$tempDir'
                    `$env:AGENT_ORCHESTRATION_MCP_URL = `$null
                    & '$ScriptPath' -OwaspOnly 'scope' 2>&1
                    exit `$LASTEXITCODE
                "
                $LASTEXITCODE | Should -Be 0
                $text = $output -join "`n"
                $text | Should -Match 'Checks:.*owasp'
                $text | Should -Match 'OWASP Top 10'
                $text | Should -Not -Match 'Secret detection scan issued'
                $text | Should -Not -Match 'Dependency vulnerability audit issued'
            }
            finally {
                Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
            }
        }
    }

    Context 'Check selection: --secrets-only' {
        It 'runs only secrets check and skips owasp and deps' {
            $tempDir = Join-Path ([IO.Path]::GetTempPath()) "sec-test-$(Get-Random)"
            New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
            try {
                $output = & pwsh -NonInteractive -Command "
                    Set-Location '$tempDir'
                    `$env:AGENT_ORCHESTRATION_MCP_URL = `$null
                    & '$ScriptPath' -SecretsOnly 'scope' 2>&1
                    exit `$LASTEXITCODE
                "
                $LASTEXITCODE | Should -Be 0
                $text = $output -join "`n"
                $text | Should -Match 'Checks:.*secrets'
                $text | Should -Match 'Secret detection'
                $text | Should -Not -Match 'OWASP Top 10 analysis issued'
                $text | Should -Not -Match 'Dependency vulnerability audit issued'
            }
            finally {
                Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
            }
        }
    }

    Context 'Security agent invocation' {
        It 'invokes security agent with opus model via MCP' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match "agent\s*=\s*'security'"
            $content | Should -Match "model\s*=\s*'opus'"
        }

        It 'passes selected checks array to MCP invocation' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match 'checks\s*=\s*\$checks'
        }
    }

    Context 'MCP fallback behavior' {
        It 'warns when Agent Orchestration MCP unavailable and continues' {
            $tempDir = Join-Path ([IO.Path]::GetTempPath()) "sec-test-$(Get-Random)"
            New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
            try {
                $output = & pwsh -NonInteractive -Command "
                    Set-Location '$tempDir'
                    `$env:AGENT_ORCHESTRATION_MCP_URL = `$null
                    & '$ScriptPath' 'scope' 2>&1
                    exit `$LASTEXITCODE
                "
                $LASTEXITCODE | Should -Be 0
                $text = $output -join "`n"
                $text | Should -Match 'MCP unavailable'
            }
            finally {
                Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
            }
        }
    }

    Context 'Workflow context integration' {
        It 'persists LastCommand as 4-security in workflow context' {
            $tempDir = Join-Path ([IO.Path]::GetTempPath()) "sec-test-$(Get-Random)"
            New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
            try {
                & pwsh -NonInteractive -Command "
                    Set-Location '$tempDir'
                    `$env:AGENT_ORCHESTRATION_MCP_URL = `$null
                    & '$ScriptPath' 'scope' 2>&1 | Out-Null
                    exit `$LASTEXITCODE
                "
                $LASTEXITCODE | Should -Be 0
                $ctxPath = Join-Path $tempDir '.agents/workflow-context.json'
                Test-Path $ctxPath | Should -BeTrue
                $ctx = Get-Content $ctxPath -Raw | ConvertFrom-Json
                $ctx.LastCommand | Should -Be '4-security'
            }
            finally {
                Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
            }
        }
    }

    Context 'Handoff tracking' {
        It 'tracks handoff from security to orchestrator' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match "from_agent\s*=\s*'security'"
            $content | Should -Match "to_agent\s*=\s*'orchestrator'"
        }
    }
}

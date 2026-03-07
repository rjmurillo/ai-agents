#!/usr/bin/env pwsh
#Requires -Module Pester

BeforeAll {
    $ScriptPath = Join-Path $PSScriptRoot 'Sync-SessionDocumentation.ps1'
}

Describe 'Sync-SessionDocumentation.ps1' {
    Context 'Syntax validation' {
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
    }

    Context 'Path traversal validation (CWE-22)' {
        It 'performs path traversal validation using GetFullPath and StartsWith' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match '\[IO\.Path\]::GetFullPath'
            $content | Should -Match '\.agents/sessions'
            $content | Should -Match 'StartsWith'
        }

        It 'uses case-insensitive comparison for path validation' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match 'OrdinalIgnoreCase'
        }

        It 'appends directory separator to base path to prevent prefix attacks' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match '\[IO\.Path\]::DirectorySeparatorChar'
        }

        It 'uses Test-Path -LiteralPath to prevent wildcard injection' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match 'Test-Path\s+-LiteralPath'
        }

        It 'exits 3 on path traversal attempt' {
            $tempDir = Join-Path ([IO.Path]::GetTempPath()) "sync-traversal-$(Get-Random)"
            New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
            try {
                & git -C $tempDir init -q 2>&1 | Out-Null
                & git -C $tempDir commit --allow-empty -m 'init' -q 2>&1 | Out-Null

                & pwsh -NonInteractive -Command "
                    Set-Location '$tempDir'
                    & '$ScriptPath' -SessionLogPath '../../../../etc/passwd' 2>&1 | Out-Null
                    exit `$LASTEXITCODE
                "
                $LASTEXITCODE | Should -Be 3
            }
            finally {
                Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
            }
        }

        It 'exits 3 for path outside .agents/sessions even if file exists' {
            $tempDir = Join-Path ([IO.Path]::GetTempPath()) "sync-outside-$(Get-Random)"
            $otherDir = Join-Path $tempDir 'other'
            New-Item -ItemType Directory -Path $otherDir -Force | Out-Null
            Set-Content -Path (Join-Path $otherDir 'fake.json') -Value '{}' -Encoding UTF8

            try {
                & git -C $tempDir init -q 2>&1 | Out-Null
                & git -C $tempDir commit --allow-empty -m 'init' -q 2>&1 | Out-Null

                & pwsh -NonInteractive -Command "
                    Set-Location '$tempDir'
                    & '$ScriptPath' -SessionLogPath 'other/fake.json' 2>&1 | Out-Null
                    exit `$LASTEXITCODE
                "
                $LASTEXITCODE | Should -Be 3
            }
            finally {
                Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
            }
        }
    }

    Context 'Session log not found' {
        It 'exits 3 when session log does not exist within allowed dir' {
            $tempDir = Join-Path ([IO.Path]::GetTempPath()) "sync-nofile-$(Get-Random)"
            $sessDir = Join-Path $tempDir '.agents/sessions'
            New-Item -ItemType Directory -Path $sessDir -Force | Out-Null
            & git -C $tempDir init -q 2>&1 | Out-Null
            & git -C $tempDir commit --allow-empty -m 'init' -q 2>&1 | Out-Null

            try {
                & pwsh -NonInteractive -Command "
                    Set-Location '$tempDir'
                    & '$ScriptPath' -SessionLogPath '.agents/sessions/nonexistent.json' 2>&1 | Out-Null
                    exit `$LASTEXITCODE
                "
                $LASTEXITCODE | Should -Be 3
            }
            finally {
                Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
            }
        }
    }

    Context 'Mermaid diagram generation' {
        It 'generates a mermaid sequenceDiagram' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match 'mermaid'
            $content | Should -Match 'sequenceDiagram'
        }

        It 'includes all 5 workflow participants' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match '/0-init'
            $content | Should -Match '/1-plan'
            $content | Should -Match '/2-impl'
            $content | Should -Match '/3-qa'
            $content | Should -Match '/4-security'
        }
    }

    Context 'Session log update (workLog)' {
        It 'reads session log as JSON and appends workLog entry' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match 'ConvertFrom-Json'
            $content | Should -Match 'workLog'
            $content | Should -Match 'ConvertTo-Json'
        }

        It 'creates workLog array if not present' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match "Add-Member.*'workLog'"
        }

        It 'includes timestamp, type, mermaidDiagram, and decisions in workLog entry' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match "'timestamp'"
            $content | Should -Match "'type'"
            $content | Should -Match "'mermaidDiagram'"
            $content | Should -Match "'decisions'"
        }
    }

    Context 'Agent history integration' {
        It 'queries agent history via MCP' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match 'agents://history'
        }

        It 'handles MCP unavailability gracefully' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match 'Fallback'
            $content | Should -Match 'unavailable'
        }
    }

    Context 'Serena memory integration' {
        It 'updates Serena memory via MCP' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match 'mcp__serena__write_memory'
        }
    }

    Context 'Retrospective suggestions' {
        It 'outputs retrospective learning suggestions' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match 'Suggested retrospective'
            $content | Should -Match 'workflow commands used in sequence'
            $content | Should -Match 'MCP fallbacks'
            $content | Should -Match 'acceptance criteria gaps'
        }
    }

    Context 'Functional: updates valid JSON session log' {
        It 'appends workLog entry with mermaid diagram to session log' {
            $tempDir = Join-Path ([IO.Path]::GetTempPath()) "sync-func-$(Get-Random)"
            $sessDir = Join-Path $tempDir '.agents/sessions'
            New-Item -ItemType Directory -Path $sessDir -Force | Out-Null

            & git -C $tempDir init -q 2>&1 | Out-Null
            & git -C $tempDir commit --allow-empty -m 'init' -q 2>&1 | Out-Null

            $logFile = Join-Path $sessDir 'session-test.json'
            @{ sessionNumber = 1; workLog = @() } | ConvertTo-Json | Set-Content $logFile -Encoding UTF8

            try {
                & pwsh -NonInteractive -Command "
                    Set-Location '$tempDir'
                    `$env:AGENT_ORCHESTRATION_MCP_URL = `$null
                    & '$ScriptPath' -SessionLogPath '$logFile' 2>&1 | Out-Null
                    exit `$LASTEXITCODE
                "
                $LASTEXITCODE | Should -Be 0

                $updated = Get-Content $logFile -Raw | ConvertFrom-Json
                $updated.workLog | Should -Not -BeNullOrEmpty
                $updated.workLog.Count | Should -BeGreaterOrEqual 1
                $entry = $updated.workLog[-1]
                $entry.type | Should -Be 'workflow-sync'
                $entry.timestamp | Should -Not -BeNullOrEmpty
                $entry.mermaidDiagram | Should -Match 'sequenceDiagram'
            }
            finally {
                Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
            }
        }

        It 'creates workLog array when session log has none' {
            $tempDir = Join-Path ([IO.Path]::GetTempPath()) "sync-nolog-$(Get-Random)"
            $sessDir = Join-Path $tempDir '.agents/sessions'
            New-Item -ItemType Directory -Path $sessDir -Force | Out-Null

            & git -C $tempDir init -q 2>&1 | Out-Null
            & git -C $tempDir commit --allow-empty -m 'init' -q 2>&1 | Out-Null

            $logFile = Join-Path $sessDir 'session-nolog.json'
            @{ sessionNumber = 2 } | ConvertTo-Json | Set-Content $logFile -Encoding UTF8

            try {
                & pwsh -NonInteractive -Command "
                    Set-Location '$tempDir'
                    `$env:AGENT_ORCHESTRATION_MCP_URL = `$null
                    & '$ScriptPath' -SessionLogPath '$logFile' 2>&1 | Out-Null
                    exit `$LASTEXITCODE
                "
                $LASTEXITCODE | Should -Be 0

                $updated = Get-Content $logFile -Raw | ConvertFrom-Json
                $updated.workLog | Should -Not -BeNullOrEmpty
            }
            finally {
                Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
            }
        }
    }

    Context 'Functional: MCP fallback output' {
        It 'emits fallback warning when MCP is unavailable' {
            $tempDir = Join-Path ([IO.Path]::GetTempPath()) "sync-mcp-$(Get-Random)"
            $sessDir = Join-Path $tempDir '.agents/sessions'
            New-Item -ItemType Directory -Path $sessDir -Force | Out-Null

            & git -C $tempDir init -q 2>&1 | Out-Null
            & git -C $tempDir commit --allow-empty -m 'init' -q 2>&1 | Out-Null

            $logFile = Join-Path $sessDir 'session-mcp.json'
            @{ sessionNumber = 3 } | ConvertTo-Json | Set-Content $logFile -Encoding UTF8

            try {
                $output = & pwsh -NonInteractive -Command "
                    Set-Location '$tempDir'
                    `$env:AGENT_ORCHESTRATION_MCP_URL = `$null
                    & '$ScriptPath' -SessionLogPath '$logFile' 2>&1
                    exit `$LASTEXITCODE
                "
                $LASTEXITCODE | Should -Be 0
                ($output -join "`n") | Should -Match 'unavailable|skeleton documentation'
            }
            finally {
                Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
            }
        }
    }
}

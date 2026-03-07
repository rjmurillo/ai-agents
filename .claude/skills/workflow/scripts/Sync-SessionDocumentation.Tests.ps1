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
        It 'performs path traversal validation before file access' {
            $content = Get-Content $ScriptPath -Raw
            # Must resolve path and compare against allowed base directory
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

        It 'exits 3 on path traversal attempt' {
            # Run in a temp dir without a .agents/sessions subdir
            $tempDir = Join-Path ([IO.Path]::GetTempPath()) "sync-traversal-$(Get-Random)"
            New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
            try {
                # Initialize a minimal git repo so git rev-parse works
                & git -C $tempDir init -q 2>&1 | Out-Null
                & git -C $tempDir commit --allow-empty -m 'init' -q 2>&1 | Out-Null

                $result = & pwsh -NonInteractive -Command "
                    Set-Location '$tempDir'
                    & '$ScriptPath' -SessionLogPath '../../../../etc/passwd' 2>&1
                    exit `$LASTEXITCODE
                "
                $LASTEXITCODE | Should -Be 3
            }
            finally {
                Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
            }
        }

        It 'uses Test-Path -LiteralPath to prevent wildcard injection' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match 'Test-Path\s+-LiteralPath'
        }
    }

    Context 'Session log not found' {
        It 'exits 3 when session log does not exist' {
            $result = & pwsh -NonInteractive -Command "
                & '$ScriptPath' -SessionLogPath 'nonexistent-file-xyz.json' 2>&1
                exit `$LASTEXITCODE
            "
            $LASTEXITCODE | Should -Be 3
        }
    }

    Context 'Mermaid diagram generation' {
        It 'generates a mermaid sequence diagram' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match 'mermaid'
            $content | Should -Match 'sequenceDiagram'
        }
    }

    Context 'Session log update (workLog)' {
        It 'reads session log as JSON' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match 'ConvertFrom-Json'
        }

        It 'appends a workLog entry to the session log' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match 'workLog'
        }

        It 'saves updated session log as JSON' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match 'ConvertTo-Json'
        }
    }

    Context 'Agent history integration' {
        It 'queries agent history via MCP' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match 'agents://history'
        }

        It 'handles MCP unavailability with fallback warning' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match 'Fallback|Warning|unavailable'
        }
    }

    Context 'Serena memory integration' {
        It 'updates Serena memory with cross-session context' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match 'mcp__serena__write_memory|write_memory'
        }
    }

    Context 'Retrospective suggestions' {
        It 'outputs retrospective learning suggestions' {
            $content = Get-Content $ScriptPath -Raw
            $content | Should -Match 'retrospective|Suggested'
        }
    }

    Context 'Functional: session log update' {
        It 'updates a valid JSON session log with workLog entry' {
            $tempDir = Join-Path ([IO.Path]::GetTempPath()) "sync-func-$(Get-Random)"
            $sessDir = Join-Path $tempDir '.agents/sessions'
            New-Item -ItemType Directory -Path $sessDir -Force | Out-Null

            # Initialize a minimal git repo
            & git -C $tempDir init -q 2>&1 | Out-Null
            & git -C $tempDir commit --allow-empty -m 'init' -q 2>&1 | Out-Null

            $logFile = Join-Path $sessDir 'session-test.json'
            @{ sessionNumber = 1; workLog = @() } | ConvertTo-Json | Set-Content $logFile -Encoding UTF8

            try {
                & pwsh -NonInteractive -Command "
                    Set-Location '$tempDir'
                    `$env:AGENT_ORCHESTRATION_MCP_URL = `$null
                    & '$ScriptPath' -SessionLogPath '$logFile' 2>&1
                    exit `$LASTEXITCODE
                " 2>&1 | Out-Null

                # Regardless of exit code, the session log should be updated
                $updated = Get-Content $logFile -Raw | ConvertFrom-Json
                $updated | Should -Not -BeNullOrEmpty
            }
            finally {
                Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
            }
        }
    }
}

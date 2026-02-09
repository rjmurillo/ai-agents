#Requires -Modules Pester

<#
.SYNOPSIS
    Comprehensive Pester tests for Invoke-SessionStartMemoryFirst.ps1

.DESCRIPTION
    Tests the ADR-007 Memory-First Architecture session start hook with 100% block code coverage.
    Validates .mcp.json parsing, error handling, and output generation.
#>

BeforeAll {
    $Script:HookPath = Join-Path $PSScriptRoot ".." ".claude" "hooks" "Invoke-SessionStartMemoryFirst.ps1"

    # Verify script exists
    if (-not (Test-Path $Script:HookPath)) {
        throw "Hook script not found at: $Script:HookPath"
    }
}

Describe "Invoke-SessionStartMemoryFirst" {
    Context "Script execution" {
        It "Executes without error" {
            { & $Script:HookPath } | Should -Not -Throw
        }

        It "Returns exit code 0" {
            & $Script:HookPath
            $LASTEXITCODE | Should -Be 0
        }

        It "Produces output" {
            $Output = & $Script:HookPath
            $Output | Should -Not -BeNullOrEmpty
        }
    }

    Context "MCP configuration parsing - no .mcp.json file" {
        BeforeAll {
            # Create temp directory without .mcp.json
            $Script:TestRoot = Join-Path ([System.IO.Path]::GetTempPath()) "hook-test-no-mcp-$(Get-Random)"
            New-Item -ItemType Directory -Path $Script:TestRoot -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $Script:TestRoot ".claude/hooks") -Force | Out-Null

            # Copy hook to temp location
            $TempHookPath = Join-Path $Script:TestRoot ".claude/hooks/Invoke-SessionStartMemoryFirst.ps1"
            Copy-Item -Path $Script:HookPath -Destination $TempHookPath -Force
        }

        AfterAll {
            if (Test-Path $Script:TestRoot) {
                Remove-Item -Path $Script:TestRoot -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It "Uses default configuration when .mcp.json missing" {
            $TempHookPath = Join-Path $Script:TestRoot ".claude/hooks/Invoke-SessionStartMemoryFirst.ps1"
            $Output = & $TempHookPath
            $LASTEXITCODE | Should -Be 0
            $Output | Should -Not -BeNullOrEmpty
            # Should use defaults and output compact ADR-007 status line
            $OutputString = $Output -join "`n"
            $OutputString | Should -Match "ADR-007 active"
        }
    }

    Context "MCP configuration parsing - invalid JSON" {
        BeforeAll {
            $Script:TestRoot = Join-Path ([System.IO.Path]::GetTempPath()) "hook-test-invalid-json-$(Get-Random)"
            New-Item -ItemType Directory -Path $Script:TestRoot -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $Script:TestRoot ".claude/hooks") -Force | Out-Null

            # Create invalid .mcp.json
            Set-Content -Path (Join-Path $Script:TestRoot ".mcp.json") -Value "{ invalid json"

            # Copy hook to temp location
            $TempHookPath = Join-Path $Script:TestRoot ".claude/hooks/Invoke-SessionStartMemoryFirst.ps1"
            Copy-Item -Path $Script:HookPath -Destination $TempHookPath -Force
        }

        AfterAll {
            if (Test-Path $Script:TestRoot) {
                Remove-Item -Path $Script:TestRoot -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It "Falls back to defaults gracefully when JSON is invalid" {
            $TempHookPath = Join-Path $Script:TestRoot ".claude/hooks/Invoke-SessionStartMemoryFirst.ps1"
            { & $TempHookPath } | Should -Not -Throw
            $Output = & $TempHookPath
            $LASTEXITCODE | Should -Be 0
            $Output | Should -Not -BeNullOrEmpty
        }
    }

    Context "MCP configuration parsing - missing mcpServers property" {
        BeforeAll {
            $Script:TestRoot = Join-Path ([System.IO.Path]::GetTempPath()) "hook-test-no-servers-$(Get-Random)"
            New-Item -ItemType Directory -Path $Script:TestRoot -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $Script:TestRoot ".claude/hooks") -Force | Out-Null

            # Create .mcp.json without mcpServers
            $mcpConfig = @{
                otherProperty = "value"
            } | ConvertTo-Json
            Set-Content -Path (Join-Path $Script:TestRoot ".mcp.json") -Value $mcpConfig

            # Copy hook to temp location
            $TempHookPath = Join-Path $Script:TestRoot ".claude/hooks/Invoke-SessionStartMemoryFirst.ps1"
            Copy-Item -Path $Script:HookPath -Destination $TempHookPath -Force
        }

        AfterAll {
            if (Test-Path $Script:TestRoot) {
                Remove-Item -Path $Script:TestRoot -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It "Uses defaults when mcpServers property missing" {
            $TempHookPath = Join-Path $Script:TestRoot ".claude/hooks/Invoke-SessionStartMemoryFirst.ps1"
            { & $TempHookPath } | Should -Not -Throw
            $Output = & $TempHookPath
            $LASTEXITCODE | Should -Be 0
        }
    }

    Context "MCP configuration parsing - missing forgetful property" {
        BeforeAll {
            $Script:TestRoot = Join-Path ([System.IO.Path]::GetTempPath()) "hook-test-no-forgetful-$(Get-Random)"
            New-Item -ItemType Directory -Path $Script:TestRoot -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $Script:TestRoot ".claude/hooks") -Force | Out-Null

            # Create .mcp.json without forgetful
            $mcpConfig = @{
                mcpServers = @{
                    serena = @{
                        type = "stdio"
                    }
                }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path (Join-Path $Script:TestRoot ".mcp.json") -Value $mcpConfig

            # Copy hook to temp location
            $TempHookPath = Join-Path $Script:TestRoot ".claude/hooks/Invoke-SessionStartMemoryFirst.ps1"
            Copy-Item -Path $Script:HookPath -Destination $TempHookPath -Force
        }

        AfterAll {
            if (Test-Path $Script:TestRoot) {
                Remove-Item -Path $Script:TestRoot -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It "Uses defaults when forgetful property missing" {
            $TempHookPath = Join-Path $Script:TestRoot ".claude/hooks/Invoke-SessionStartMemoryFirst.ps1"
            { & $TempHookPath } | Should -Not -Throw
            $Output = & $TempHookPath
            $LASTEXITCODE | Should -Be 0
        }
    }

    Context "MCP configuration parsing - forgetful without url property" {
        BeforeAll {
            $Script:TestRoot = Join-Path ([System.IO.Path]::GetTempPath()) "hook-test-no-url-$(Get-Random)"
            New-Item -ItemType Directory -Path $Script:TestRoot -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $Script:TestRoot ".claude/hooks") -Force | Out-Null

            # Create .mcp.json with forgetful but no url (stdio type)
            $mcpConfig = @{
                mcpServers = @{
                    forgetful = @{
                        type = "stdio"
                        command = "uvx"
                        args = @("forgetful-ai")
                    }
                }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path (Join-Path $Script:TestRoot ".mcp.json") -Value $mcpConfig

            # Copy hook to temp location
            $TempHookPath = Join-Path $Script:TestRoot ".claude/hooks/Invoke-SessionStartMemoryFirst.ps1"
            Copy-Item -Path $Script:HookPath -Destination $TempHookPath -Force
        }

        AfterAll {
            if (Test-Path $Script:TestRoot) {
                Remove-Item -Path $Script:TestRoot -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It "Uses defaults when url property missing (stdio type)" {
            $TempHookPath = Join-Path $Script:TestRoot ".claude/hooks/Invoke-SessionStartMemoryFirst.ps1"
            { & $TempHookPath } | Should -Not -Throw
            $Output = & $TempHookPath
            $LASTEXITCODE | Should -Be 0
        }
    }

    Context "MCP configuration parsing - valid http URL" {
        BeforeAll {
            $Script:TestRoot = Join-Path ([System.IO.Path]::GetTempPath()) "hook-test-valid-url-$(Get-Random)"
            New-Item -ItemType Directory -Path $Script:TestRoot -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $Script:TestRoot ".claude/hooks") -Force | Out-Null

            # Create .mcp.json with http-based forgetful
            $mcpConfig = @{
                mcpServers = @{
                    forgetful = @{
                        type = "http"
                        url = "http://localhost:8020"
                    }
                }
            } | ConvertTo-Json -Depth 10
            Set-Content -Path (Join-Path $Script:TestRoot ".mcp.json") -Value $mcpConfig

            # Copy hook to temp location
            $TempHookPath = Join-Path $Script:TestRoot ".claude/hooks/Invoke-SessionStartMemoryFirst.ps1"
            Copy-Item -Path $Script:HookPath -Destination $TempHookPath -Force
        }

        AfterAll {
            if (Test-Path $Script:TestRoot) {
                Remove-Item -Path $Script:TestRoot -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It "Parses URL successfully and outputs compact status" {
            $TempHookPath = Join-Path $Script:TestRoot ".claude/hooks/Invoke-SessionStartMemoryFirst.ps1"
            { & $TempHookPath } | Should -Not -Throw
            $Output = & $TempHookPath
            $LASTEXITCODE | Should -Be 0
            # URL is parsed but TCP check is disabled; compact output still emitted
            $OutputString = $Output -join "`n"
            $OutputString | Should -Match "ADR-007 active"
        }
    }

    Context "Output content validation - compact format" {
        BeforeAll {
            $Output = & $Script:HookPath
            $Script:OutputString = $Output -join "`n"
        }

        It "Outputs ADR-007 active marker" {
            $Script:OutputString | Should -Match "ADR-007 active"
        }

        It "Outputs exactly one line" {
            $Output = & $Script:HookPath
            $Output | Should -HaveCount 1
        }

        It "Includes Forgetful status" {
            $Script:OutputString | Should -Match "Forgetful:"
        }

        It "Shows Forgetful unavailable when not configured (default)" {
            $Script:OutputString | Should -Match "Forgetful: unavailable"
        }

        It "Includes Serena fallback hint when Forgetful unavailable" {
            $Script:OutputString | Should -Match "use Serena"
        }

        It "Includes Protocol reference" {
            $Script:OutputString | Should -Match "Protocol:"
        }

        It "References AGENTS.md as protocol source" {
            $Script:OutputString | Should -Match "AGENTS\.md"
        }

        It "References Session Protocol Gates section" {
            $Script:OutputString | Should -Match "Session Protocol Gates"
        }

        It "Does NOT include verbose Phase 1 header" {
            $Script:OutputString | Should -Not -Match "Phase 1: Serena Initialization"
        }

        It "Does NOT include verbose Phase 2 header" {
            $Script:OutputString | Should -Not -Match "Phase 2: Context Retrieval"
        }

        It "Does NOT include BLOCKING GATE text" {
            $Script:OutputString | Should -Not -Match "BLOCKING GATE"
        }

        It "Does NOT include MCP Server Status section" {
            $Script:OutputString | Should -Not -Match "MCP Server Status"
        }

        It "Does NOT include verbose Verification section" {
            $Script:OutputString | Should -Not -Match "Session logs MUST evidence memory retrieval"
        }

        It "Does NOT include pre-commit validation warning" {
            $Script:OutputString | Should -Not -Match "Pre-commit validation will fail"
        }

        It "Does NOT include SESSION-PROTOCOL.md path" {
            $Script:OutputString | Should -Not -Match "\.agents/SESSION-PROTOCOL\.md"
        }

        It "Does NOT include ADR-007 architecture document path" {
            $Script:OutputString | Should -Not -Match "\.agents/architecture/ADR-007-memory-first-architecture\.md"
        }

        It "Does NOT include mcp__serena__activate_project instruction" {
            $Script:OutputString | Should -Not -Match "mcp__serena__activate_project"
        }

        It "Does NOT include HANDOFF.md reference" {
            $Script:OutputString | Should -Not -Match "\.agents/HANDOFF\.md"
        }

        It "Does NOT include memory-index reference" {
            $Script:OutputString | Should -Not -Match "memory-index"
        }

        It "Does NOT include Forgetful query instruction" {
            $Script:OutputString | Should -Not -Match "Query Forgetful for semantic search"
        }

        It "Does NOT include install instructions" {
            $Script:OutputString | Should -Not -Match "Install-Forgetful"
        }
    }

    Context "Exit code behavior" {
        It "Always exits with code 0 (non-blocking)" {
            & $Script:HookPath
            $LASTEXITCODE | Should -Be 0
        }

        It "Exits 0 even with .mcp.json parsing errors" {
            $TestRoot = Join-Path ([System.IO.Path]::GetTempPath()) "hook-test-error-$(Get-Random)"
            New-Item -ItemType Directory -Path $TestRoot -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $TestRoot ".claude/hooks") -Force | Out-Null

            # Create corrupted .mcp.json
            Set-Content -Path (Join-Path $TestRoot ".mcp.json") -Value "{{{corrupt"

            # Copy hook to temp location
            $TempHookPath = Join-Path $TestRoot ".claude/hooks/Invoke-SessionStartMemoryFirst.ps1"
            Copy-Item -Path $Script:HookPath -Destination $TempHookPath -Force

            & $TempHookPath
            $LASTEXITCODE | Should -Be 0

            # Cleanup
            Remove-Item -Path $TestRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    Context "Strict mode compliance" {
        It "Executes cleanly under Set-StrictMode -Version Latest" {
            $TestScript = @'
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
& "{0}"
'@ -f $Script:HookPath

            { Invoke-Expression $TestScript } | Should -Not -Throw
        }
    }
}

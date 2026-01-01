#Requires -Modules Pester

<#
.SYNOPSIS
    Pester tests for Invoke-SessionStartMemoryFirst.ps1

.DESCRIPTION
    Tests the ADR-007 Memory-First Architecture session start hook.
    Validates that the hook outputs the expected context for Claude.
#>

BeforeAll {
    $ScriptPath = Join-Path $PSScriptRoot ".." ".claude" "hooks" "Invoke-SessionStartMemoryFirst.ps1"
}

Describe "Invoke-SessionStartMemoryFirst" {
    Context "Script execution" {
        It "Executes without error" {
            { & $ScriptPath } | Should -Not -Throw
        }

        It "Returns exit code 0" {
            & $ScriptPath
            $LASTEXITCODE | Should -Be 0
        }
    }

    Context "Output content" {
        BeforeAll {
            $Output = & $ScriptPath
            $OutputString = $Output -join "`n"
        }

        It "Outputs ADR-007 enforcement header" {
            $OutputString | Should -Match "ADR-007 Memory-First Enforcement"
        }

        It "Includes BLOCKING GATE instruction" {
            $OutputString | Should -Match "BLOCKING GATE"
        }

        It "Includes Phase 1 Serena initialization" {
            $OutputString | Should -Match "Phase 1: Serena Initialization"
            $OutputString | Should -Match "mcp__serena__activate_project"
            $OutputString | Should -Match "mcp__serena__initial_instructions"
        }

        It "Includes Phase 2 context retrieval" {
            $OutputString | Should -Match "Phase 2: Context Retrieval"
            $OutputString | Should -Match "HANDOFF\.md"
            $OutputString | Should -Match "memory-index"
        }

        It "Includes verification instructions" {
            $OutputString | Should -Match "Session logs MUST evidence memory retrieval"
        }

        It "References SESSION-PROTOCOL.md" {
            $OutputString | Should -Match "SESSION-PROTOCOL\.md"
        }

        It "References ADR-007 architecture document" {
            $OutputString | Should -Match "ADR-007-memory-first-architecture\.md"
        }
    }
}

<#
.SYNOPSIS
    Tests for Export-ForgetfulMemories.ps1

.DESCRIPTION
    Pester tests covering parameter validation, path traversal prevention,
    security patterns, and export functionality.

.NOTES
    EXIT CODES:
    0  - Success: All tests passed
    1  - Error: One or more tests failed (set by Pester framework)

    See: ADR-035 Exit Code Standardization
#>

BeforeAll {
    $ScriptPath = Join-Path $PSScriptRoot '..' 'forgetful' 'Export-ForgetfulMemories.ps1'
    $ScriptContent = Get-Content -Path $ScriptPath -Raw
}

Describe 'Export-ForgetfulMemories.ps1' {
    Context 'Script Syntax' {
        It 'Should be valid PowerShell' {
            $errors = $null
            [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]$errors)
            $errors | Should -BeNullOrEmpty
        }

        It 'Should have comment-based help' {
            $ScriptContent | Should -Match '\.SYNOPSIS'
            $ScriptContent | Should -Match '\.DESCRIPTION'
            $ScriptContent | Should -Match '\.PARAMETER'
            $ScriptContent | Should -Match '\.EXAMPLE'
        }
    }

    Context 'Parameter Definitions' {
        It 'Should have optional OutputFile parameter' {
            $ScriptContent | Should -Match '\[string\]\$OutputFile'
        }

        It 'Should have optional SessionNumber parameter' {
            $ScriptContent | Should -Match '\[int\]\$SessionNumber'
        }

        It 'Should have optional Topic parameter' {
            $ScriptContent | Should -Match '\[string\]\$Topic'
        }

        It 'Should have optional DatabasePath parameter with default' {
            $ScriptContent | Should -Match '\[string\]\$DatabasePath\s*='
        }

        It 'Should have optional IncludeTables parameter with default' {
            $ScriptContent | Should -Match "\[string\]\`$IncludeTables\s*=\s*'all'"
        }
    }

    Context 'Security - Path Traversal Prevention (CWE-22)' {
        It 'Should use GetFullPath for path normalization' {
            $ScriptContent | Should -Match '\[System\.IO\.Path\]::GetFullPath'
        }

        It 'Should check output path is inside exports directory' {
            $ScriptContent | Should -Match 'StartsWith\('
        }

        It 'Should add trailing separator to prevent directory bypass' {
            # Pattern: NormalizedDir.TrimEnd + DirectorySeparatorChar
            $ScriptContent | Should -Match 'TrimEnd\(\[IO\.Path\]::DirectorySeparatorChar\)'
            $ScriptContent | Should -Match '\+ \[IO\.Path\]::DirectorySeparatorChar'
        }

        It 'Should error on path traversal attempt' {
            $ScriptContent | Should -Match 'Path traversal attempt detected'
        }
    }

    Context 'Security - Command Injection Prevention (CWE-78)' {
        It 'Should quote DatabasePath in sqlite3 command calls' {
            # Pattern: sqlite3 "$DatabasePath" - the variable must be quoted
            # This matches actual sqlite3 command invocations (not comments)
            $ScriptContent | Should -Match 'sqlite3\s+"\$DatabasePath"'
        }

        It 'Should not have unquoted DatabasePath in sqlite3 calls' {
            # Ensure no unquoted $DatabasePath follows sqlite3
            # Pattern: sqlite3 $DatabasePath (without quotes) should NOT exist
            $unquotedPattern = 'sqlite3\s+\$DatabasePath\s+'
            $ScriptContent | Should -Not -Match $unquotedPattern
        }
    }

    Context 'Table Export Configuration' {
        It 'Should define all 13 data tables' {
            $ScriptContent | Should -Match "'users'"
            $ScriptContent | Should -Match "'memories'"
            $ScriptContent | Should -Match "'projects'"
            $ScriptContent | Should -Match "'entities'"
            $ScriptContent | Should -Match "'documents'"
            $ScriptContent | Should -Match "'code_artifacts'"
            $ScriptContent | Should -Match "'memory_links'"
            $ScriptContent | Should -Match "'memory_project_association'"
            $ScriptContent | Should -Match "'memory_code_artifact_association'"
            $ScriptContent | Should -Match "'memory_document_association'"
            $ScriptContent | Should -Match "'memory_entity_association'"
            $ScriptContent | Should -Match "'entity_project_association'"
            $ScriptContent | Should -Match "'entity_relationships'"
        }

        It 'Should support table filtering with IncludeTables' {
            $ScriptContent | Should -Match '\$IncludeTables -ne .all.'
        }
    }

    Context 'Export Metadata' {
        It 'Should include export timestamp' {
            $ScriptContent | Should -Match 'export_timestamp'
        }

        It 'Should include database path' {
            $ScriptContent | Should -Match 'database_path'
        }

        It 'Should include schema version' {
            $ScriptContent | Should -Match 'schema_version'
        }

        It 'Should include exported tables list' {
            $ScriptContent | Should -Match 'exported_tables'
        }

        It 'Should include export tool name' {
            $ScriptContent | Should -Match 'export_tool'
        }
    }

    Context 'Security Review Integration' {
        It 'Should call security review script after export' {
            $ScriptContent | Should -Match 'Review-MemoryExportSecurity\.ps1'
        }

        It 'Should fail if security review fails' {
            $ScriptContent | Should -Match 'if \(\$LASTEXITCODE -ne 0\)'
            $ScriptContent | Should -Match 'Security review FAILED'
        }
    }

    Context 'Error Handling' {
        It 'Should set strict mode' {
            $ScriptContent | Should -Match 'Set-StrictMode -Version Latest'
        }

        It 'Should set error action preference to Stop' {
            $ScriptContent | Should -Match "\`$ErrorActionPreference\s*=\s*'Stop'"
        }

        It 'Should check for sqlite3 availability' {
            $ScriptContent | Should -Match 'Get-Command sqlite3'
        }

        It 'Should check for database existence' {
            $ScriptContent | Should -Match 'Test-Path \$DatabasePath'
        }
    }
}

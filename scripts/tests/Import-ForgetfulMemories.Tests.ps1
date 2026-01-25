<#
.SYNOPSIS
    Tests for Import-ForgetfulMemories.ps1

.DESCRIPTION
    Pester tests covering parameter validation, merge mode behavior,
    SQL injection prevention, and import functionality.

.NOTES
    EXIT CODES:
    0  - Success: All tests passed
    1  - Error: One or more tests failed (set by Pester framework)

    See: ADR-035 Exit Code Standardization
#>

BeforeAll {
    $ScriptPath = Join-Path $PSScriptRoot '..' 'forgetful' 'Import-ForgetfulMemories.ps1'
    $ScriptContent = Get-Content -Path $ScriptPath -Raw
}

Describe 'Import-ForgetfulMemories.ps1' {
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
        It 'Should have optional InputFiles parameter' {
            $ScriptContent | Should -Match '\[string\[\]\]\$InputFiles'
        }

        It 'Should have optional DatabasePath parameter with default' {
            $ScriptContent | Should -Match '\[string\]\$DatabasePath\s*='
        }

        It 'Should have MergeMode parameter with ValidateSet' {
            $ScriptContent | Should -Match "\[ValidateSet\('Replace', 'Skip', 'Fail'\)\]"
            $ScriptContent | Should -Match '\[string\]\$MergeMode'
        }

        It 'Should have Force switch parameter' {
            $ScriptContent | Should -Match '\[switch\]\$Force'
        }
    }

    Context 'Merge Mode SQL Operations' {
        It 'Should use INSERT OR REPLACE for Replace mode' {
            $ScriptContent | Should -Match "'Replace'\s*\{\s*'INSERT OR REPLACE INTO'\s*\}"
        }

        It 'Should use INSERT OR IGNORE for Skip mode' {
            $ScriptContent | Should -Match "'Skip'\s*\{\s*'INSERT OR IGNORE INTO'\s*\}"
        }

        It 'Should use INSERT for Fail mode' {
            $ScriptContent | Should -Match "'Fail'\s*\{\s*'INSERT INTO'\s*\}"
        }

        It 'Should default to Replace mode' {
            $ScriptContent | Should -Match "\`$MergeMode\s*=\s*'Replace'"
        }
    }

    Context 'Security - SQL Injection Prevention (CWE-89)' {
        It 'Should validate column names against database schema' {
            $ScriptContent | Should -Match 'PRAGMA table_info'
            $ScriptContent | Should -Match '\$SchemaColumns'
        }

        It 'Should filter to only valid column names' {
            $ScriptContent | Should -Match '\$SchemaColumns -contains'
        }

        It 'Should warn about unknown columns' {
            $ScriptContent | Should -Match 'Ignoring unknown columns'
        }

        It 'Should escape single quotes in values' {
            # Script should escape single quotes by doubling them for SQL
            $ScriptContent | Should -Match "-replace"
            $ScriptContent | Should -Match "''"  # Doubled single quotes
        }

        It 'Should quote primary key values for SQL' {
            $ScriptContent | Should -Match '\$QuotedPkValue'
        }
    }

    Context 'Security - Command Injection Prevention (CWE-78)' {
        It 'Should quote DatabasePath in sqlite3 command calls' {
            # Pattern: sqlite3 "$DatabasePath" - the variable must be quoted
            $ScriptContent | Should -Match 'sqlite3\s+"\$DatabasePath"'
        }

        It 'Should not have unquoted DatabasePath in sqlite3 calls' {
            # Ensure no unquoted $DatabasePath follows sqlite3
            $unquotedPattern = 'sqlite3\s+\$DatabasePath\s+'
            $ScriptContent | Should -Not -Match $unquotedPattern
        }
    }

    Context 'Table Import Order (Foreign Key Dependencies)' {
        It 'Should define import order for all tables' {
            $ScriptContent | Should -Match '\$ImportOrder\s*='
        }

        It 'Should import users before other tables' {
            # Users should be first in the import order
            $ScriptContent | Should -Match "\`$ImportOrder\s*=\s*@\(\s*'users'"
        }

        It 'Should import entities before entity relationships' {
            # Entities should come before entity_relationships
            $entitiesMatch = [regex]::Match($ScriptContent, "'entities'")
            $relationshipsMatch = [regex]::Match($ScriptContent, "'entity_relationships'")
            $entitiesMatch.Index | Should -BeLessThan $relationshipsMatch.Index
        }
    }

    Context 'Primary Key Handling' {
        It 'Should define primary keys for main tables' {
            $ScriptContent | Should -Match "'users'\s*\{\s*@\('id'\)"
            $ScriptContent | Should -Match "'memories'\s*\{\s*@\('id'\)"
            $ScriptContent | Should -Match "'projects'\s*\{\s*@\('id'\)"
        }

        It 'Should define composite keys for association tables' {
            $ScriptContent | Should -Match "'memory_project_association'\s*\{\s*@\('memory_id',\s*'project_id'\)"
            $ScriptContent | Should -Match "'memory_entity_association'\s*\{\s*@\('memory_id',\s*'entity_id'\)"
            $ScriptContent | Should -Match "'entity_project_association'\s*\{\s*@\('entity_id',\s*'project_id'\)"
        }

        It 'Should build WHERE clause for composite keys' {
            $ScriptContent | Should -Match '\$WhereConditions\s*='
            $ScriptContent | Should -Match "-join ' AND '"
        }
    }

    Context 'Idempotency' {
        It 'Should track insert count' {
            $ScriptContent | Should -Match '\$InsertedCount'
        }

        It 'Should track update count' {
            $ScriptContent | Should -Match '\$UpdatedCount'
        }

        It 'Should track skip count' {
            $ScriptContent | Should -Match '\$SkippedCount'
        }

        It 'Should check record existence before insert' {
            $ScriptContent | Should -Match '\$RecordExistedBefore'
            $ScriptContent | Should -Match 'SELECT COUNT\(\*\) FROM'
        }
    }

    Context 'Export Format Validation' {
        It 'Should validate export_metadata presence' {
            $ScriptContent | Should -Match '\$ImportData\.export_metadata'
        }

        It 'Should validate data section presence' {
            $ScriptContent | Should -Match '\$ImportData\.data'
        }

        It 'Should skip invalid export format' {
            $ScriptContent | Should -Match 'Invalid export format'
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

        It 'Should handle UNIQUE constraint violations in Fail mode' {
            $ScriptContent | Should -Match 'UNIQUE constraint failed'
            $ScriptContent | Should -Match 'Duplicate record found'
        }
    }

    Context 'User Confirmation' {
        It 'Should prompt for confirmation unless Force is specified' {
            $ScriptContent | Should -Match '-not \$Force'
            $ScriptContent | Should -Match 'Read-Host'
        }

        It 'Should allow bypass with Force switch' {
            $ScriptContent | Should -Match '\[switch\]\$Force'
        }
    }
}

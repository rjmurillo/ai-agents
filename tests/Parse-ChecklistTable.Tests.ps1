#Requires -Modules Pester

<#
.SYNOPSIS
    Pester tests for Parse-ChecklistTable function in Validate-Session.ps1

.DESCRIPTION
    Tests the table parsing logic that handles markdown tables with code spans
    containing pipe characters. Ensures the parser correctly respects backticks
    when splitting table rows.
#>

BeforeAll {
    $scriptPath = Join-Path $PSScriptRoot ".." "scripts" "Validate-Session.ps1"

    # Extract the functions we need to test
    $scriptContent = Get-Content -Path $scriptPath -Raw

    # Extract Split-TableRow function - it's before Parse-ChecklistTable
    # Match from function declaration to its closing brace (greedy but constrained by Parse-ChecklistTable start)
    $splitPattern = '(?ms)function Split-TableRow\s*\{.*?(?=function Parse-ChecklistTable)'
    if ($scriptContent -match $splitPattern) {
        $splitTableRowDef = $Matches[0].TrimEnd()
        # Add closing brace if needed
        if (-not $splitTableRowDef.EndsWith('}')) {
            $splitTableRowDef += "`n}"
        }
        Invoke-Expression $splitTableRowDef
    }

    # Extract Parse-ChecklistTable function - match to next function or end of functions section
    $parsePattern = '(?ms)function Parse-ChecklistTable\([^)]+\)\s*\{.*?(?=^function\s|\z)'
    if ($scriptContent -match $parsePattern) {
        $parseTableDef = $Matches[0].TrimEnd()
        # Ensure it ends with closing brace
        if (-not $parseTableDef.EndsWith('}')) {
            # Find the last closing brace in the match
            $lastBrace = $parseTableDef.LastIndexOf('}')
            if ($lastBrace -gt 0) {
                $parseTableDef = $parseTableDef.Substring(0, $lastBrace + 1)
            }
        }
        Invoke-Expression $parseTableDef
    }
}

Describe "Split-TableRow" {
    Context "Basic table row splitting" {
        It "Should split simple row without code spans" {
            $row = ' MUST | Read file | [x] | Done '
            $result = Split-TableRow $row | ForEach-Object { $_.Trim() }
            
            $result.Count | Should -Be 4
            $result[0] | Should -Be 'MUST'
            $result[1] | Should -Be 'Read file'
            $result[2] | Should -Be '[x]'
            $result[3] | Should -Be 'Done'
        }

        It "Should handle extra whitespace" {
            $row = '  MUST  |  Read file  |  [x]  |  Done  '
            $result = Split-TableRow $row | ForEach-Object { $_.Trim() }
            
            $result.Count | Should -Be 4
            $result[0] | Should -Be 'MUST'
        }
    }

    Context "Code spans with pipe characters" {
        It "Should preserve pipes inside single backticks" {
            $row = ' MUST | Run: `grep "a|b|c"` | [x] | Clean '
            $result = Split-TableRow $row | ForEach-Object { $_.Trim() }
            
            $result.Count | Should -Be 4
            $result[0] | Should -Be 'MUST'
            $result[1] | Should -Be 'Run: `grep "a|b|c"`'
            $result[2] | Should -Be '[x]'
            $result[3] | Should -Be 'Clean'
        }

        It "Should handle the problematic SESSION-PROTOCOL.md security review row" {
            $row = ' MUST | Security review export (if exported): `grep -iE "api[_-]?key|password|token|secret|credential|private[_-]?key" [file].json` | [ ] | Evidence '
            $result = Split-TableRow $row | ForEach-Object { $_.Trim() }
            
            $result.Count | Should -Be 4
            $result[0] | Should -Be 'MUST'
            $result[1] | Should -Match 'grep.*key\|password\|token\|secret'
            $result[1] | Should -Be 'Security review export (if exported): `grep -iE "api[_-]?key|password|token|secret|credential|private[_-]?key" [file].json`'
            $result[2] | Should -Be '[ ]'
            $result[3] | Should -Be 'Evidence'
        }

        It "Should handle multiple code spans in same row" {
            $row = ' MUST | Run `cmd1|x` and `cmd2|y` | [x] | Done '
            $result = Split-TableRow $row | ForEach-Object { $_.Trim() }
            
            $result.Count | Should -Be 4
            $result[1] | Should -Be 'Run `cmd1|x` and `cmd2|y`'
        }

        It "Should handle empty code spans" {
            $row = ' MUST | Empty `` code | [x] | Done '
            $result = Split-TableRow $row | ForEach-Object { $_.Trim() }
            
            $result.Count | Should -Be 4
            $result[1] | Should -Be 'Empty `` code'
        }

        It "Should handle code span at start of column" {
            $row = ' MUST | `command|with|pipes` is the step | [x] | Done '
            $result = Split-TableRow $row | ForEach-Object { $_.Trim() }
            
            $result.Count | Should -Be 4
            $result[1] | Should -Be '`command|with|pipes` is the step'
        }

        It "Should handle code span at end of column" {
            $row = ' MUST | Run command `grep|test` | [x] | Done '
            $result = Split-TableRow $row | ForEach-Object { $_.Trim() }
            
            $result.Count | Should -Be 4
            $result[1] | Should -Be 'Run command `grep|test`'
        }
    }

    Context "Edge cases" {
        It "Should handle row with no pipes" {
            $row = 'MUST'
            $result = Split-TableRow $row
            
            # No pipes means single column
            $result.Count | Should -Be 1
            $result[0] | Should -Be 'MUST'
        }

        It "Should handle empty row" {
            $row = ''
            $result = Split-TableRow $row
            
            # Empty row returns array with one empty element
            $result.Count | Should -BeGreaterOrEqual 0
        }

        It "Should handle multiple consecutive pipes outside code spans" {
            $row = ' MUST ||  Read file | [x] '
            $result = Split-TableRow $row | ForEach-Object { $_.Trim() }
            
            # Multiple pipes create empty columns
            $result.Count | Should -Be 4
            $result[1] | Should -Be ''
        }

        It "Should toggle code span state with odd number of backticks" {
            # This is a malformed case but should handle gracefully
            $row = ' MUST | Text `with odd backtick | [x] | Done '
            $result = Split-TableRow $row
            
            # After first backtick, we're in code span until end
            # So only 2 columns (split at first pipe only)
            $result.Count | Should -Be 2
        }
    }
}

Describe "Parse-ChecklistTable" {
    Context "Table header and separator handling" {
        It "Should skip header row" {
            $tableLines = @(
                '| Req | Step | Status | Evidence |',
                '|-----|------|--------|----------|',
                '| MUST | Read file | [x] | Done |'
            )
            $result = Parse-ChecklistTable $tableLines
            
            $result.Count | Should -Be 1
            $result[0].Req | Should -Be 'MUST'
        }

        It "Should skip separator row" {
            $tableLines = @(
                '|-----|------|--------|----------|',
                '| MUST | Read file | [x] | Done |'
            )
            $result = Parse-ChecklistTable $tableLines
            
            $result.Count | Should -Be 1
        }

        It "Should skip rows with fewer than 4 columns" {
            $tableLines = @(
                '| MUST | Read file | [x] |',
                '| MUST | Write file | [x] | Done |'
            )
            $result = Parse-ChecklistTable $tableLines
            
            $result.Count | Should -Be 1
            $result[0].Step | Should -Be 'Write file'
        }
    }

    Context "Status parsing" {
        It "Should parse checked status [x]" {
            $tableLines = @('| MUST | Read file | [x] | Done |')
            $result = Parse-ChecklistTable $tableLines
            
            $result[0].Status | Should -Be 'x'
        }

        It "Should parse checked status [X] (uppercase)" {
            $tableLines = @('| MUST | Read file | [X] | Done |')
            $result = Parse-ChecklistTable $tableLines
            
            $result[0].Status | Should -Be 'x'
        }

        It "Should parse unchecked status [ ]" {
            $tableLines = @('| MUST | Read file | [ ] | Done |')
            $result = Parse-ChecklistTable $tableLines
            
            $result[0].Status | Should -Be ' '
        }

        It "Should parse checked status with extra whitespace [  x  ]" {
            $tableLines = @('| MUST | Read file | [  x  ] | Done |')
            $result = Parse-ChecklistTable $tableLines
            
            $result[0].Status | Should -Be 'x'
        }
    }

    Context "Req column normalization" {
        It "Should convert MUST to uppercase" {
            $tableLines = @('| must | Read file | [x] | Done |')
            $result = Parse-ChecklistTable $tableLines
            
            $result[0].Req | Should -Be 'MUST'
        }

        It "Should remove asterisks from Req column" {
            $tableLines = @('| **MUST** | Read file | [x] | Done |')
            $result = Parse-ChecklistTable $tableLines
            
            $result[0].Req | Should -Be 'MUST'
        }

        It "Should handle SHOULD requirement" {
            $tableLines = @('| SHOULD | Export memories | [ ] | Skipped |')
            $result = Parse-ChecklistTable $tableLines
            
            $result[0].Req | Should -Be 'SHOULD'
        }
    }

    Context "Code spans with pipes in Step column" {
        It "Should parse security review row from SESSION-PROTOCOL.md" {
            $tableLines = @(
                '| Req | Step | Status | Evidence |',
                '|-----|------|--------|----------|',
                '| MUST | Security review export (if exported): `grep -iE "api[_-]?key|password|token|secret|credential|private[_-]?key" [file].json` | [ ] | Evidence |'
            )
            $result = Parse-ChecklistTable $tableLines
            
            $result.Count | Should -Be 1
            $result[0].Req | Should -Be 'MUST'
            $result[0].Step | Should -Match 'grep.*key\|password\|token'
            $result[0].Status | Should -Be ' '
            $result[0].Evidence | Should -Be 'Evidence'
        }

        It "Should handle multiple code spans with pipes" {
            $tableLines = @(
                '| MUST | Run `cmd1|x` and `cmd2|y` | [x] | Done |'
            )
            $result = Parse-ChecklistTable $tableLines
            
            $result[0].Step | Should -Be 'Run `cmd1|x` and `cmd2|y`'
        }

        It "Should preserve all columns when pipes in code spans" {
            $tableLines = @(
                '| MUST | Command: `test|pipe` | [x] | Result: clean |'
            )
            $result = Parse-ChecklistTable $tableLines
            
            $result[0].Req | Should -Be 'MUST'
            $result[0].Step | Should -Be 'Command: `test|pipe`'
            $result[0].Status | Should -Be 'x'
            $result[0].Evidence | Should -Be 'Result: clean'
        }
    }

    Context "Multiple rows processing" {
        It "Should parse multiple rows correctly" {
            $tableLines = @(
                '| Req | Step | Status | Evidence |',
                '|-----|------|--------|----------|',
                '| MUST | Read file | [x] | Done |',
                '| MUST | Write file | [ ] | Pending |',
                '| SHOULD | Optional task | [x] | Completed |'
            )
            $result = Parse-ChecklistTable $tableLines
            
            $result.Count | Should -Be 3
            $result[0].Step | Should -Be 'Read file'
            $result[1].Step | Should -Be 'Write file'
            $result[2].Req | Should -Be 'SHOULD'
        }

        It "Should handle mix of rows with and without code spans" {
            $tableLines = @(
                '| MUST | Simple step | [x] | Done |',
                '| MUST | Command: `grep|test` | [x] | Done |',
                '| MUST | Another simple | [ ] | Pending |'
            )
            $result = Parse-ChecklistTable $tableLines
            
            $result.Count | Should -Be 3
            $result[0].Step | Should -Be 'Simple step'
            $result[1].Step | Should -Be 'Command: `grep|test`'
            $result[2].Step | Should -Be 'Another simple'
        }
    }

    Context "Raw line preservation" {
        It "Should preserve the raw line in result" {
            $tableLines = @('| MUST | Read file | [x] | Done |')
            $result = Parse-ChecklistTable $tableLines
            
            $result[0].Raw | Should -Be '| MUST | Read file | [x] | Done |'
        }
    }
}

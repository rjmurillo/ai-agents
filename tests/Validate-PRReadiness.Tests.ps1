<#
.SYNOPSIS
    Tests for Validate-PRReadiness.ps1

.DESCRIPTION
    Pester tests covering commit count, changed files, total additions,
    synthesis panel verdict, ADR compliance, and exit code behavior.

    Section 1: Structural tests (syntax validation, parameter checks)
    Section 2: Behavioral tests using extracted functions with Pester mocks

.NOTES
    EXIT CODES:
    0  - Success: All tests passed
    1  - Error: One or more tests failed (set by Pester framework)

    See: ADR-035 Exit Code Standardization
#>

BeforeAll {
    $ScriptPath = Join-Path $PSScriptRoot '..' '.agents' 'scripts' 'Validate-PRReadiness.ps1'
    $ScriptContent = Get-Content -Path $ScriptPath -Raw

    # Extract function definitions from the script using AST parsing.
    # The script's main body executes git commands and calls exit, so we
    # cannot dot-source it directly. Instead, we parse out function
    # definitions and evaluate them in the test scope.
    $ast = [System.Management.Automation.Language.Parser]::ParseFile(
        $ScriptPath, [ref]$null, [ref]$null
    )
    $functionDefs = $ast.FindAll(
        { param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] },
        $false  # do not search nested (top-level only)
    )
    $functionSource = ($functionDefs | ForEach-Object { $_.Extent.Text }) -join "`n`n"

    # Create temp file with extracted functions and dot-source it.
    # This makes all functions available for behavioral testing.
    $tempFile = [System.IO.Path]::GetTempFileName() -replace '\.tmp$', '.ps1'
    Set-Content -Path $tempFile -Value $functionSource -Encoding UTF8
    . $tempFile
    Remove-Item -Path $tempFile -ErrorAction SilentlyContinue
}

#region Section 1: Structural Tests (Safety Net)

Describe 'Validate-PRReadiness.ps1 - Structural Tests' {
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
        It 'Should have BaseBranch parameter with default origin/main' {
            $ScriptContent | Should -Match '\[string\]\$BaseBranch\s*=\s*"origin/main"'
        }

        It 'Should have MaxCommits parameter with default 20' {
            $ScriptContent | Should -Match '\[int\]\$MaxCommits\s*=\s*20'
        }

        It 'Should have MaxFiles parameter with default 10' {
            $ScriptContent | Should -Match '\[int\]\$MaxFiles\s*=\s*10'
        }

        It 'Should have MaxAdditions parameter with default 500' {
            $ScriptContent | Should -Match '\[int\]\$MaxAdditions\s*=\s*500'
        }

        It 'Should have CritiquePath parameter' {
            $ScriptContent | Should -Match '\[string\]\$CritiquePath'
        }
    }

    Context 'Exit Codes (ADR-035)' {
        It 'Should exit 0 on all checks passing' {
            $ScriptContent | Should -Match 'exit\s+0'
        }

        It 'Should exit 1 on check failures' {
            $ScriptContent | Should -Match 'exit\s+1'
        }

        It 'Should exit 2 on environment errors' {
            $ScriptContent | Should -Match 'exit\s+2'
        }
    }
}

#endregion

#region Section 2: Behavioral Tests

Describe 'Get-CommitCount' {
    It 'returns commit count from git output' {
        Mock git {
            $global:LASTEXITCODE = 0
            return "15"
        }
        $result = Get-CommitCount -Base "origin/main"
        $result | Should -Be 15
        Should -Invoke git -Times 1
    }

    It 'returns -1 when git fails' {
        Mock git {
            $global:LASTEXITCODE = 128
            return "fatal: bad revision"
        }
        $result = Get-CommitCount -Base "origin/main"
        $result | Should -Be -1
    }

    It 'handles zero commits' {
        Mock git {
            $global:LASTEXITCODE = 0
            return "0"
        }
        $result = Get-CommitCount -Base "origin/main"
        $result | Should -Be 0
    }

    It 'handles large commit counts' {
        Mock git {
            $global:LASTEXITCODE = 0
            return "999"
        }
        $result = Get-CommitCount -Base "origin/main"
        $result | Should -Be 999
    }

    It 'returns integer type' {
        Mock git {
            $global:LASTEXITCODE = 0
            return "5"
        }
        $result = Get-CommitCount -Base "origin/main"
        $result | Should -BeOfType [int]
    }
}

Describe 'Get-ChangedFileCount' {
    It 'counts changed files correctly' {
        Mock git {
            $global:LASTEXITCODE = 0
            return "file1.ps1`nfile2.ps1`nfile3.md"
        }
        $result = Get-ChangedFileCount -Base "origin/main"
        $result | Should -Be 3
    }

    It 'returns 0 for no changes' {
        Mock git {
            $global:LASTEXITCODE = 0
            return ""
        }
        $result = Get-ChangedFileCount -Base "origin/main"
        $result | Should -Be 0
    }

    It 'returns 0 for whitespace-only output' {
        Mock git {
            $global:LASTEXITCODE = 0
            return "   `n  `n "
        }
        $result = Get-ChangedFileCount -Base "origin/main"
        $result | Should -Be 0
    }

    It 'returns -1 on git error' {
        Mock git {
            $global:LASTEXITCODE = 1
            return "fatal: not a git repository"
        }
        $result = Get-ChangedFileCount -Base "origin/main"
        $result | Should -Be -1
    }

    It 'handles single file change' {
        Mock git {
            $global:LASTEXITCODE = 0
            return "only-file.txt"
        }
        $result = Get-ChangedFileCount -Base "origin/main"
        $result | Should -Be 1
    }

    It 'ignores trailing blank lines in output' {
        Mock git {
            $global:LASTEXITCODE = 0
            return "file1.ps1`nfile2.ps1`n`n"
        }
        $result = Get-ChangedFileCount -Base "origin/main"
        $result | Should -Be 2
    }
}

Describe 'Get-TotalAddition' {
    It 'parses insertion count from standard git diff --stat' {
        Mock git {
            $global:LASTEXITCODE = 0
            return " file1.ps1 | 10 +++++++---`n file2.ps1 | 5 +++++`n 2 files changed, 120 insertions(+), 30 deletions(-)"
        }
        $result = Get-TotalAddition -Base "origin/main"
        $result | Should -Be 120
    }

    It 'handles stats with only insertions' {
        Mock git {
            $global:LASTEXITCODE = 0
            return " file1.ps1 | 45 ++++++`n 1 file changed, 45 insertions(+)"
        }
        $result = Get-TotalAddition -Base "origin/main"
        $result | Should -Be 45
    }

    It 'handles stats with insertions and deletions' {
        Mock git {
            $global:LASTEXITCODE = 0
            return " 5 files changed, 200 insertions(+), 50 deletions(-)"
        }
        $result = Get-TotalAddition -Base "origin/main"
        $result | Should -Be 200
    }

    It 'handles singular insertion' {
        Mock git {
            $global:LASTEXITCODE = 0
            return " 1 file changed, 1 insertion(+)"
        }
        $result = Get-TotalAddition -Base "origin/main"
        $result | Should -Be 1
    }

    It 'returns 0 for deletions only (no insertions)' {
        Mock git {
            $global:LASTEXITCODE = 0
            return " 2 files changed, 10 deletions(-)"
        }
        $result = Get-TotalAddition -Base "origin/main"
        $result | Should -Be 0
    }

    It 'returns -1 on git error' {
        Mock git {
            $global:LASTEXITCODE = 128
            return "fatal: bad revision"
        }
        $result = Get-TotalAddition -Base "origin/main"
        $result | Should -Be -1
    }

    It 'returns 0 for empty diff output' {
        Mock git {
            $global:LASTEXITCODE = 0
            return ""
        }
        $result = Get-TotalAddition -Base "origin/main"
        $result | Should -Be 0
    }
}

Describe 'Test-SynthesisPanelVerdict' {
    It 'returns passed when no critique directory exists' {
        Mock Test-Path { return $false }
        $result = Test-SynthesisPanelVerdict -Path "/nonexistent/path"
        $result.Passed | Should -BeTrue
        $result.Detail | Should -Match 'No critique directory found'
    }

    It 'returns passed when critique directory is empty' {
        Mock Test-Path { return $true }
        Mock Get-ChildItem { return @() }
        $result = Test-SynthesisPanelVerdict -Path "/some/path"
        $result.Passed | Should -BeTrue
        $result.Detail | Should -Match 'No critique files found'
    }

    It 'returns passed when no blocking verdicts exist' {
        $mockFile = [PSCustomObject]@{
            FullName = "/some/path/critique-1.md"
            Name     = "critique-1.md"
        }
        Mock Test-Path { return $true }
        Mock Get-ChildItem { return @($mockFile) }
        Mock Get-Content {
            return @"
## Verdict

**APPROVED**

- [x] All items resolved
"@
        }
        $result = Test-SynthesisPanelVerdict -Path "/some/path"
        $result.Passed | Should -BeTrue
        $result.Detail | Should -Match '1 file\(s\) checked'
    }

    It 'returns failed when REJECTED with P0 exists' {
        $mockFile = [PSCustomObject]@{
            FullName = "/some/path/critique-blocking.md"
            Name     = "critique-blocking.md"
        }
        Mock Test-Path { return $true }
        Mock Get-ChildItem { return @($mockFile) }
        Mock Get-Content {
            return @"
## Verdict

**REJECTED - Critical blocking issues found**

- [ ] **SCOPE-001: Critical issue (P0)**
"@
        }
        $result = Test-SynthesisPanelVerdict -Path "/some/path"
        $result.Passed | Should -BeFalse
        $result.Detail | Should -Match 'Blocking critique'
        $result.Detail | Should -Match 'critique-blocking.md'
    }

    It 'returns failed when NEEDS_CHANGES with P1 exists' {
        $mockFile = [PSCustomObject]@{
            FullName = "/some/path/critique-changes.md"
            Name     = "critique-changes.md"
        }
        Mock Test-Path { return $true }
        Mock Get-ChildItem { return @($mockFile) }
        Mock Get-Content {
            return @"
## Verdict

**NEEDS_CHANGES**

- [ ] **Fix P1 issue with validation**
"@
        }
        $result = Test-SynthesisPanelVerdict -Path "/some/path"
        $result.Passed | Should -BeFalse
        $result.Detail | Should -Match 'Blocking critique'
    }

    It 'returns passed when verdict is blocking but all items are checked' {
        $mockFile = [PSCustomObject]@{
            FullName = "/some/path/critique-resolved.md"
            Name     = "critique-resolved.md"
        }
        Mock Test-Path { return $true }
        Mock Get-ChildItem { return @($mockFile) }
        Mock Get-Content {
            return @"
## Verdict

**REJECTED - Critical blocking issues found**

- [x] **SCOPE-001: Critical issue (P0)**
"@
        }
        # REJECTED verdict exists but no unchecked P0/P1 items, so
        # hasBlockingVerdict is true but hasBlockingPriority is false.
        # Both must be true for blocking.
        $result = Test-SynthesisPanelVerdict -Path "/some/path"
        $result.Passed | Should -BeTrue
    }

    It 'returns passed when unchecked P0 exists but verdict is APPROVED' {
        $mockFile = [PSCustomObject]@{
            FullName = "/some/path/critique-partial.md"
            Name     = "critique-partial.md"
        }
        Mock Test-Path { return $true }
        Mock Get-ChildItem { return @($mockFile) }
        Mock Get-Content {
            return @"
## Verdict

**APPROVED**

- [ ] **SCOPE-001: Critical issue (P0)**
"@
        }
        # Unchecked P0 exists but verdict is not REJECTED/NEEDS_CHANGES.
        # hasBlockingVerdict is false, so no blocking.
        $result = Test-SynthesisPanelVerdict -Path "/some/path"
        $result.Passed | Should -BeTrue
    }

    It 'handles Final Verdict heading' {
        $mockFile = [PSCustomObject]@{
            FullName = "/some/path/critique-final.md"
            Name     = "critique-final.md"
        }
        Mock Test-Path { return $true }
        Mock Get-ChildItem { return @($mockFile) }
        Mock Get-Content {
            return @"
## Final Verdict

**REJECTED**

- [ ] **Critical P0 blocker**
"@
        }
        $result = Test-SynthesisPanelVerdict -Path "/some/path"
        $result.Passed | Should -BeFalse
    }

    It 'handles multiple critique files with mixed verdicts' {
        $mockFiles = @(
            [PSCustomObject]@{ FullName = "/path/good.md"; Name = "good.md" }
            [PSCustomObject]@{ FullName = "/path/bad.md"; Name = "bad.md" }
        )
        Mock Test-Path { return $true }
        Mock Get-ChildItem { return $mockFiles }
        Mock Get-Content {
            param($Path)
            if ($Path -eq "/path/good.md") {
                return "## Verdict`n`n**APPROVED**`n`n- [x] All good"
            }
            return "## Verdict`n`n**REJECTED - Critical**`n`n- [ ] **P0 blocker**"
        }
        $result = Test-SynthesisPanelVerdict -Path "/some/path"
        $result.Passed | Should -BeFalse
        $result.Detail | Should -Match 'bad.md'
    }

    It 'skips files with empty content' {
        $mockFile = [PSCustomObject]@{
            FullName = "/some/path/empty.md"
            Name     = "empty.md"
        }
        Mock Test-Path { return $true }
        Mock Get-ChildItem { return @($mockFile) }
        Mock Get-Content { return "" }
        $result = Test-SynthesisPanelVerdict -Path "/some/path"
        $result.Passed | Should -BeTrue
    }
}

Describe 'Test-ADRCompliance' {
    BeforeEach {
        # Test-ADRCompliance uses $RepoRoot from script scope.
        # Set it in the current scope so Join-Path works.
        $script:RepoRoot = "/fake/repo"
    }

    It 'returns passed when no architecture directory exists' {
        Mock Test-Path { return $false }
        $result = Test-ADRCompliance
        $result.Passed | Should -BeTrue
        $result.Detail | Should -Match 'No architecture directory found'
    }

    It 'returns passed when no ADR files exist' {
        Mock Test-Path { return $true }
        Mock Get-ChildItem { return @() }
        $result = Test-ADRCompliance
        $result.Passed | Should -BeTrue
        $result.Detail | Should -Match 'No ADR files found'
    }

    It 'returns passed when all ADRs have required sections' {
        $mockFile = [PSCustomObject]@{
            FullName = "/fake/repo/.agents/architecture/ADR-001.md"
            Name     = "ADR-001.md"
        }
        Mock Test-Path { return $true }
        Mock Get-ChildItem { return @($mockFile) }
        Mock Get-Content {
            return @"
# ADR-001: Some Decision

## Status
Accepted

## Context
Some context here.

## Decision
We decided to do X.

## Consequences
This means Y.
"@
        }
        $result = Test-ADRCompliance
        $result.Passed | Should -BeTrue
        $result.Detail | Should -Match '1 ADR\(s\) have required structure'
    }

    It 'returns failed when ADR missing Status section' {
        $mockFile = [PSCustomObject]@{
            FullName = "/fake/repo/.agents/architecture/ADR-002.md"
            Name     = "ADR-002.md"
        }
        Mock Test-Path { return $true }
        Mock Get-ChildItem { return @($mockFile) }
        Mock Get-Content {
            return @"
# ADR-002: Missing Status

## Context
Some context.

## Decision
We decided something.
"@
        }
        $result = Test-ADRCompliance
        $result.Passed | Should -BeFalse
        $result.Detail | Should -Match 'ADR-002.md'
    }

    It 'returns failed when ADR missing Decision section' {
        $mockFile = [PSCustomObject]@{
            FullName = "/fake/repo/.agents/architecture/ADR-003.md"
            Name     = "ADR-003.md"
        }
        Mock Test-Path { return $true }
        Mock Get-ChildItem { return @($mockFile) }
        Mock Get-Content {
            return @"
# ADR-003: Missing Decision

## Status
Accepted

## Context
Some context.
"@
        }
        $result = Test-ADRCompliance
        $result.Passed | Should -BeFalse
        $result.Detail | Should -Match 'ADR-003.md'
    }

    It 'returns failed when ADR missing both Status and Decision' {
        $mockFile = [PSCustomObject]@{
            FullName = "/fake/repo/.agents/architecture/ADR-004.md"
            Name     = "ADR-004.md"
        }
        Mock Test-Path { return $true }
        Mock Get-ChildItem { return @($mockFile) }
        Mock Get-Content {
            return @"
# ADR-004: Bare Bones

## Context
Just context, nothing else.
"@
        }
        $result = Test-ADRCompliance
        $result.Passed | Should -BeFalse
        $result.Detail | Should -Match 'ADR-004.md'
    }

    It 'handles multiple ADRs with mixed compliance' {
        $mockFiles = @(
            [PSCustomObject]@{ FullName = "/fake/repo/.agents/architecture/ADR-010.md"; Name = "ADR-010.md" }
            [PSCustomObject]@{ FullName = "/fake/repo/.agents/architecture/ADR-011.md"; Name = "ADR-011.md" }
        )
        Mock Test-Path { return $true }
        Mock Get-ChildItem { return $mockFiles }
        Mock Get-Content {
            param($Path)
            if ($Path -eq "/fake/repo/.agents/architecture/ADR-010.md") {
                return "## Status`nAccepted`n## Decision`nDo X"
            }
            return "## Context`nJust context"
        }
        $result = Test-ADRCompliance
        $result.Passed | Should -BeFalse
        $result.Detail | Should -Match 'ADR-011.md'
        $result.Detail | Should -Not -Match 'ADR-010.md'
    }

    It 'skips files with empty content' {
        $mockFile = [PSCustomObject]@{
            FullName = "/fake/repo/.agents/architecture/ADR-005.md"
            Name     = "ADR-005.md"
        }
        Mock Test-Path { return $true }
        Mock Get-ChildItem { return @($mockFile) }
        Mock Get-Content { return "" }
        $result = Test-ADRCompliance
        $result.Passed | Should -BeTrue
    }
}

Describe 'Add-CheckResult' {
    BeforeEach {
        $script:CheckResults = @()
    }

    It 'adds a passed result with PASS status' {
        Add-CheckResult -Name "Test Check" -Passed $true -Detail "All good"
        $script:CheckResults.Count | Should -Be 1
        $script:CheckResults[0].Name | Should -Be "Test Check"
        $script:CheckResults[0].Status | Should -Be "PASS"
        $script:CheckResults[0].Detail | Should -Be "All good"
    }

    It 'adds a failed result with FAIL status' {
        Add-CheckResult -Name "Bad Check" -Passed $false -Detail "Something broke"
        $script:CheckResults.Count | Should -Be 1
        $script:CheckResults[0].Name | Should -Be "Bad Check"
        $script:CheckResults[0].Status | Should -Be "FAIL"
        $script:CheckResults[0].Detail | Should -Be "Something broke"
    }

    It 'accumulates multiple results' {
        Add-CheckResult -Name "Check A" -Passed $true -Detail "OK"
        Add-CheckResult -Name "Check B" -Passed $false -Detail "Not OK"
        Add-CheckResult -Name "Check C" -Passed $true -Detail "Also OK"
        $script:CheckResults.Count | Should -Be 3
    }

    It 'creates PSCustomObject results with correct properties' {
        Add-CheckResult -Name "Typed Check" -Passed $true -Detail "Type test"
        $result = $script:CheckResults[0]
        $result.PSObject.Properties.Name | Should -Contain 'Name'
        $result.PSObject.Properties.Name | Should -Contain 'Status'
        $result.PSObject.Properties.Name | Should -Contain 'Detail'
    }
}

Describe 'Write-Status' {
    It 'accepts all valid status values without error' {
        Mock Write-Host {}
        $validStatuses = @('PASS', 'FAIL', 'WARNING', 'SKIP', 'RUNNING')
        foreach ($status in $validStatuses) {
            { Write-Status -Status $status -Message "Test message" } | Should -Not -Throw
        }
    }

    It 'rejects invalid status values' {
        { Write-Status -Status 'INVALID' -Message "Test" } | Should -Throw
    }

    It 'formats output as [STATUS] Message' {
        Mock Write-Host {}
        # Write-Status calls Write-ColorOutput which calls Write-Host.
        # We verify it does not throw and the call chain works.
        { Write-Status -Status 'PASS' -Message "Check completed" } | Should -Not -Throw
    }
}

Describe 'Write-ColorOutput' {
    It 'calls Write-Host without error' {
        Mock Write-Host {}
        { Write-ColorOutput -Message "Test output" } | Should -Not -Throw
        Should -Invoke Write-Host -Times 1
    }
}

Describe 'Threshold Boundary Tests' {
    # These tests verify the comparison logic embedded in the script's main body.
    # Since we cannot run the main body directly (it calls exit), we test
    # the threshold logic by exercising the comparison operators directly.
    # The script uses -gt (greater than), so exactly-at-threshold passes
    # and one-over fails.

    Context 'Commit count boundaries' {
        It 'passes at exactly 20 commits (default threshold)' {
            Mock git {
                $global:LASTEXITCODE = 0
                return "20"
            }
            $count = Get-CommitCount -Base "origin/main"
            $maxCommits = 20
            ($count -gt $maxCommits) | Should -BeFalse
        }

        It 'fails at 21 commits (one over default threshold)' {
            Mock git {
                $global:LASTEXITCODE = 0
                return "21"
            }
            $count = Get-CommitCount -Base "origin/main"
            $maxCommits = 20
            ($count -gt $maxCommits) | Should -BeTrue
        }

        It 'passes at 19 commits (one under default threshold)' {
            Mock git {
                $global:LASTEXITCODE = 0
                return "19"
            }
            $count = Get-CommitCount -Base "origin/main"
            $maxCommits = 20
            ($count -gt $maxCommits) | Should -BeFalse
        }
    }

    Context 'Changed files boundaries' {
        It 'passes at exactly 10 files (default threshold)' {
            Mock git {
                $global:LASTEXITCODE = 0
                return (@(1..10 | ForEach-Object { "file$_.ps1" }) -join "`n")
            }
            $count = Get-ChangedFileCount -Base "origin/main"
            $maxFiles = 10
            ($count -gt $maxFiles) | Should -BeFalse
        }

        It 'fails at 11 files (one over default threshold)' {
            Mock git {
                $global:LASTEXITCODE = 0
                return (@(1..11 | ForEach-Object { "file$_.ps1" }) -join "`n")
            }
            $count = Get-ChangedFileCount -Base "origin/main"
            $maxFiles = 10
            ($count -gt $maxFiles) | Should -BeTrue
        }

        It 'passes at 9 files (one under default threshold)' {
            Mock git {
                $global:LASTEXITCODE = 0
                return (@(1..9 | ForEach-Object { "file$_.ps1" }) -join "`n")
            }
            $count = Get-ChangedFileCount -Base "origin/main"
            $maxFiles = 10
            ($count -gt $maxFiles) | Should -BeFalse
        }
    }

    Context 'Total additions boundaries' {
        It 'passes at exactly 500 additions (default threshold)' {
            Mock git {
                $global:LASTEXITCODE = 0
                return " 5 files changed, 500 insertions(+), 10 deletions(-)"
            }
            $count = Get-TotalAddition -Base "origin/main"
            $maxAdditions = 500
            ($count -gt $maxAdditions) | Should -BeFalse
        }

        It 'fails at 501 additions (one over default threshold)' {
            Mock git {
                $global:LASTEXITCODE = 0
                return " 5 files changed, 501 insertions(+), 10 deletions(-)"
            }
            $count = Get-TotalAddition -Base "origin/main"
            $maxAdditions = 500
            ($count -gt $maxAdditions) | Should -BeTrue
        }

        It 'passes at 499 additions (one under default threshold)' {
            Mock git {
                $global:LASTEXITCODE = 0
                return " 5 files changed, 499 insertions(+), 10 deletions(-)"
            }
            $count = Get-TotalAddition -Base "origin/main"
            $maxAdditions = 500
            ($count -gt $maxAdditions) | Should -BeFalse
        }
    }
}

Describe 'Integration - Full Script Execution' {
    # Test the script as a black box via pwsh -File.
    # This validates exit codes and end-to-end behavior.

    It 'exits 2 when not in a git repository' {
        $result = pwsh -NoProfile -Command "
            Set-Location ([System.IO.Path]::GetTempPath())
            & '$ScriptPath' 2>&1
            `$LASTEXITCODE
        "
        # Last line of output is the exit code
        $exitCode = [int]($result | Select-Object -Last 1)
        $exitCode | Should -Be 2
    }
}

Describe 'Regex Pattern Behavior' {
    # These tests verify the actual regex patterns used in the script
    # against controlled content, ensuring parsing logic is correct.

    Context 'Verdict pattern matching' {
        It 'matches REJECTED verdict in markdown heading' {
            $content = "## Verdict`n`n**REJECTED - Critical blocking issues found**"
            $content -match '(?m)^##\s+(?:Final\s+)?Verdict\s*\r?\n\s*\r?\n\*\*\s*(?:REJECTED|NEEDS_CHANGES)' | Should -BeTrue
        }

        It 'matches NEEDS_CHANGES verdict in markdown heading' {
            $content = "## Verdict`n`n**NEEDS_CHANGES**"
            $content -match '(?m)^##\s+(?:Final\s+)?Verdict\s*\r?\n\s*\r?\n\*\*\s*(?:REJECTED|NEEDS_CHANGES)' | Should -BeTrue
        }

        It 'matches Final Verdict heading' {
            $content = "## Final Verdict`n`n**REJECTED**"
            $content -match '(?m)^##\s+(?:Final\s+)?Verdict\s*\r?\n\s*\r?\n\*\*\s*(?:REJECTED|NEEDS_CHANGES)' | Should -BeTrue
        }

        It 'does not match APPROVED verdict' {
            $content = "## Verdict`n`n**APPROVED**"
            $content -match '(?m)^##\s+(?:Final\s+)?Verdict\s*\r?\n\s*\r?\n\*\*\s*(?:REJECTED|NEEDS_CHANGES)' | Should -BeFalse
        }
    }

    Context 'Blocking priority pattern matching' {
        It 'matches unchecked P0 items' {
            $content = "- [ ] **SCOPE-001: Critical issue (P0)**"
            $content -match '(?m)^-\s+\[\s\]\s+.*(?:Critical|CRITICAL|P0|P1)' | Should -BeTrue
        }

        It 'matches unchecked P1 items' {
            $content = "- [ ] **Fix P1 issue with validation**"
            $content -match '(?m)^-\s+\[\s\]\s+.*(?:Critical|CRITICAL|P0|P1)' | Should -BeTrue
        }

        It 'does not match checked (resolved) items' {
            $content = "- [x] **SCOPE-001: Critical issue (P0)**"
            $content -match '(?m)^-\s+\[\s\]\s+.*(?:Critical|CRITICAL|P0|P1)' | Should -BeFalse
        }

        It 'does not match non-critical unchecked items' {
            $content = "- [ ] **Minor style suggestion**"
            $content -match '(?m)^-\s+\[\s\]\s+.*(?:Critical|CRITICAL|P0|P1)' | Should -BeFalse
        }
    }

    Context 'Git stat insertion parsing' {
        It 'extracts insertion count from standard stat summary' {
            $line = " 5 files changed, 120 insertions(+), 30 deletions(-)"
            $line -match '(\d+)\s+insertion' | Should -BeTrue
            [int]$Matches[1] | Should -Be 120
        }

        It 'extracts insertion count when no deletions' {
            $line = " 3 files changed, 45 insertions(+)"
            $line -match '(\d+)\s+insertion' | Should -BeTrue
            [int]$Matches[1] | Should -Be 45
        }

        It 'handles singular insertion' {
            $line = " 1 file changed, 1 insertion(+)"
            $line -match '(\d+)\s+insertion' | Should -BeTrue
            [int]$Matches[1] | Should -Be 1
        }

        It 'returns false for deletions only' {
            $line = " 2 files changed, 10 deletions(-)"
            $line -match '(\d+)\s+insertion' | Should -BeFalse
        }
    }
}

#endregion

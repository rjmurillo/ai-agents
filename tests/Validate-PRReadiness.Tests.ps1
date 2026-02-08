<#
.SYNOPSIS
    Tests for Validate-PRReadiness.ps1

.DESCRIPTION
    Pester tests covering commit count, changed files, total additions,
    synthesis panel verdict, ADR compliance, and exit code behavior.

.NOTES
    EXIT CODES:
    0  - Success: All tests passed
    1  - Error: One or more tests failed (set by Pester framework)

    See: ADR-035 Exit Code Standardization
#>

BeforeAll {
    $ScriptPath = Join-Path $PSScriptRoot '..' '.agents' 'scripts' 'Validate-PRReadiness.ps1'
    $ScriptContent = Get-Content -Path $ScriptPath -Raw  # used in Describe blocks via Pester scoping
}

Describe 'Validate-PRReadiness.ps1' {
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

    Context 'Strict Mode and Error Handling' {
        It 'Should use StrictMode Latest' {
            $ScriptContent | Should -Match 'Set-StrictMode\s+-Version\s+Latest'
        }

        It 'Should set ErrorActionPreference to Stop' {
            $ScriptContent | Should -Match "\`$ErrorActionPreference\s*=\s*'Stop'"
        }
    }

    Context 'Color Output' {
        It 'Should detect NO_COLOR environment variable' {
            $ScriptContent | Should -Match '\$env:NO_COLOR'
        }

        It 'Should detect CI environment variable' {
            $ScriptContent | Should -Match '\$env:CI'
        }

        It 'Should define Write-ColorOutput function' {
            $ScriptContent | Should -Match 'function\s+Write-ColorOutput'
        }

        It 'Should define Write-Status function' {
            $ScriptContent | Should -Match 'function\s+Write-Status'
        }

        It 'Should support PASS, FAIL, WARNING, SKIP, RUNNING statuses' {
            $ScriptContent | Should -Match "'PASS', 'FAIL', 'WARNING', 'SKIP', 'RUNNING'"
        }
    }

    Context 'Git Environment Validation' {
        It 'Should verify git repository' {
            $ScriptContent | Should -Match 'git\s+rev-parse\s+--show-toplevel'
        }

        It 'Should verify base branch exists' {
            $ScriptContent | Should -Match 'git\s+rev-parse\s+--verify\s+\$BaseBranch'
        }

        It 'Should exit 2 on environment errors' {
            $ScriptContent | Should -Match 'exit\s+2'
        }
    }

    Context 'Check 1: Commit Count' {
        It 'Should define Get-CommitCount function' {
            $ScriptContent | Should -Match 'function\s+Get-CommitCount'
        }

        It 'Should use git rev-list --count for commit counting' {
            $ScriptContent | Should -Match 'git\s+rev-list\s+--count'
        }

        It 'Should compare against MaxCommits threshold' {
            $ScriptContent | Should -Match '\$commitCount\s+-gt\s+\$MaxCommits'
        }

        It 'Should provide remediation for excess commits' {
            $ScriptContent | Should -Match 'Squash commits'
        }
    }

    Context 'Check 2: Changed Files Count' {
        It 'Should define Get-ChangedFileCount function' {
            $ScriptContent | Should -Match 'function\s+Get-ChangedFileCount'
        }

        It 'Should use git diff --name-only for file counting' {
            $ScriptContent | Should -Match 'git\s+diff\s+--name-only'
        }

        It 'Should compare against MaxFiles threshold' {
            $ScriptContent | Should -Match '\$fileCount\s+-gt\s+\$MaxFiles'
        }

        It 'Should provide remediation for excess files' {
            $ScriptContent | Should -Match 'Split changes into multiple'
        }
    }

    Context 'Check 3: Total Additions' {
        It 'Should define Get-TotalAddition function' {
            $ScriptContent | Should -Match 'function\s+Get-TotalAddition'
        }

        It 'Should use git diff --stat for addition counting' {
            $ScriptContent | Should -Match 'git\s+diff\s+--stat'
        }

        It 'Should parse insertion count from stat output' {
            # The script uses regex '(\d+)\s+insertion' to parse git diff --stat
            $ScriptContent | Should -Match 'summaryLine.*-match.*insertion'
        }

        It 'Should compare against MaxAdditions threshold' {
            $ScriptContent | Should -Match '\$additions\s+-gt\s+\$MaxAdditions'
        }

        It 'Should provide remediation for excess additions' {
            $ScriptContent | Should -Match 'Break the PR into smaller'
        }
    }

    Context 'Check 4: Synthesis Panel Verdict' {
        It 'Should define Test-SynthesisPanelVerdict function' {
            $ScriptContent | Should -Match 'function\s+Test-SynthesisPanelVerdict'
        }

        It 'Should scan for REJECTED verdicts' {
            $ScriptContent | Should -Match 'REJECTED'
        }

        It 'Should scan for NEEDS_CHANGES verdicts' {
            $ScriptContent | Should -Match 'NEEDS_CHANGES'
        }

        It 'Should check for blocking priority items (P0/P1)' {
            $ScriptContent | Should -Match 'P0\|P1'
        }

        It 'Should handle missing critique directory gracefully' {
            $ScriptContent | Should -Match 'No critique directory found'
        }

        It 'Should provide remediation for blocking critiques' {
            $ScriptContent | Should -Match 'Address blocking critique findings'
        }
    }

    Context 'Check 5: ADR Compliance' {
        It 'Should define Test-ADRCompliance function' {
            $ScriptContent | Should -Match 'function\s+Test-ADRCompliance'
        }

        It 'Should check for Status section in ADRs' {
            $ScriptContent | Should -Match "hasStatus.*Status"
        }

        It 'Should check for Decision section in ADRs' {
            $ScriptContent | Should -Match "hasDecision.*Decision"
        }

        It 'Should handle missing architecture directory gracefully' {
            $ScriptContent | Should -Match 'No architecture directory found'
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

    Context 'Summary Output' {
        It 'Should display PR Readiness header' {
            $ScriptContent | Should -Match 'PR Readiness Validation'
        }

        It 'Should show total checks count' {
            $ScriptContent | Should -Match 'Total Checks'
        }

        It 'Should show passed count' {
            $ScriptContent | Should -Match 'Passed:'
        }

        It 'Should show failed count' {
            $ScriptContent | Should -Match 'Failed:'
        }

        It 'Should display detailed results' {
            $ScriptContent | Should -Match 'Detailed Results'
        }
    }

    Context 'Add-CheckResult Tracking' {
        It 'Should define Add-CheckResult function' {
            $ScriptContent | Should -Match 'function\s+Add-CheckResult'
        }

        It 'Should track results with Name, Status, and Detail' {
            $ScriptContent | Should -Match 'Name\s*=\s*\$Name'
            $ScriptContent | Should -Match 'Status\s*='
            $ScriptContent | Should -Match 'Detail\s*=\s*\$Detail'
        }

        It 'Should use @() array wrapping for result counting' {
            $ScriptContent | Should -Match '@\(\$CheckResults\s*\|\s*Where-Object'
        }
    }

    Context 'Synthesis Panel Verdict Logic' {
        # Test the regex patterns used for blocking verdict detection

        It 'Should match REJECTED verdict in markdown heading' {
            $content = @"
## Verdict

**REJECTED - Critical blocking issues found**
"@
            $content -match '(?m)^##\s+(?:Final\s+)?Verdict\s*\r?\n\s*\r?\n\*\*\s*(?:REJECTED|NEEDS_CHANGES)' | Should -BeTrue
        }

        It 'Should match NEEDS_CHANGES verdict in markdown heading' {
            $content = @"
## Verdict

**NEEDS_CHANGES**
"@
            $content -match '(?m)^##\s+(?:Final\s+)?Verdict\s*\r?\n\s*\r?\n\*\*\s*(?:REJECTED|NEEDS_CHANGES)' | Should -BeTrue
        }

        It 'Should match Final Verdict heading' {
            $content = @"
## Final Verdict

**REJECTED**
"@
            $content -match '(?m)^##\s+(?:Final\s+)?Verdict\s*\r?\n\s*\r?\n\*\*\s*(?:REJECTED|NEEDS_CHANGES)' | Should -BeTrue
        }

        It 'Should not match APPROVED verdict' {
            $content = @"
## Verdict

**APPROVED**
"@
            $content -match '(?m)^##\s+(?:Final\s+)?Verdict\s*\r?\n\s*\r?\n\*\*\s*(?:REJECTED|NEEDS_CHANGES)' | Should -BeFalse
        }

        It 'Should match unchecked P0 blocking items' {
            $content = "- [ ] **SCOPE-001: Critical issue (P0)**"
            $content -match '(?m)^-\s+\[\s\]\s+.*(?:Critical|CRITICAL|P0|P1)' | Should -BeTrue
        }

        It 'Should match unchecked P1 blocking items' {
            $content = "- [ ] **Fix P1 issue with validation**"
            $content -match '(?m)^-\s+\[\s\]\s+.*(?:Critical|CRITICAL|P0|P1)' | Should -BeTrue
        }

        It 'Should not match checked (resolved) items' {
            $content = "- [x] **SCOPE-001: Critical issue (P0)**"
            $content -match '(?m)^-\s+\[\s\]\s+.*(?:Critical|CRITICAL|P0|P1)' | Should -BeFalse
        }

        It 'Should not match non-critical unchecked items' {
            $content = "- [ ] **Minor style suggestion**"
            $content -match '(?m)^-\s+\[\s\]\s+.*(?:Critical|CRITICAL|P0|P1)' | Should -BeFalse
        }
    }

    Context 'Git Stat Parsing' {
        It 'Should extract insertion count from standard stat summary' {
            $line = " 5 files changed, 120 insertions(+), 30 deletions(-)"
            $line -match '(\d+)\s+insertion' | Should -BeTrue
            [int]$Matches[1] | Should -Be 120
        }

        It 'Should extract insertion count when no deletions' {
            $line = " 3 files changed, 45 insertions(+)"
            $line -match '(\d+)\s+insertion' | Should -BeTrue
            [int]$Matches[1] | Should -Be 45
        }

        It 'Should handle singular insertion' {
            $line = " 1 file changed, 1 insertion(+)"
            $line -match '(\d+)\s+insertion' | Should -BeTrue
            [int]$Matches[1] | Should -Be 1
        }

        It 'Should handle deletions only (no insertions)' {
            $line = " 2 files changed, 10 deletions(-)"
            $line -match '(\d+)\s+insertion' | Should -BeFalse
        }
    }
}

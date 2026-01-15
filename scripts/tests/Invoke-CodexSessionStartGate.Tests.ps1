<#
.SYNOPSIS
    Pester tests for Invoke-CodexSessionStartGate.ps1

.DESCRIPTION
    Tests gate script execution, exit codes, and core functionality.
    Note: The script uses Write-Host for colorized output, so content verification is limited.
    Tests focus on exit codes, prerequisites, and execution without errors.

.NOTES
    Requires Pester 5.x or later.

    EXIT CODES:
    0  - Success: All tests passed
    1  - Error: One or more tests failed (set by Pester framework)

    See: ADR-035 Exit Code Standardization
#>

BeforeAll {
    $Script:GateScriptPath = Join-Path $PSScriptRoot ".." "Invoke-CodexSessionStartGate.ps1"
    $Script:RepoRoot = (git -C $PSScriptRoot rev-parse --show-toplevel).Trim()
}

Describe "Invoke-CodexSessionStartGate.ps1 - Script Existence" {
    It "Gate script exists" {
        Test-Path $Script:GateScriptPath | Should -Be $true
    }
    
    It "Gate script has valid PowerShell syntax" {
        { $null = [System.Management.Automation.PSParser]::Tokenize((Get-Content $Script:GateScriptPath -Raw), [ref]$null) } | Should -Not -Throw
    }
}

Describe "Gate 1: Memory-First Verification - Prerequisites" {
    It "Memory index file exists" {
        $memoryIndexPath = Join-Path $Script:RepoRoot ".serena" "memories" "memory-index.md"
        Test-Path $memoryIndexPath | Should -Be $true -Because "Memory index is required for Gate 1"
    }
    
    It "At least one Tier 1 memory exists" {
        $tier1Memories = @('project-overview', 'codebase-structure', 'usage-mandatory')
        $memoriesPath = Join-Path $Script:RepoRoot ".serena" "memories"
        
        $existingCount = 0
        foreach ($memory in $tier1Memories) {
            $memoryPath = Join-Path $memoriesPath "$memory.md"
            if (Test-Path $memoryPath) {
                $existingCount++
            }
        }
        
        $existingCount | Should -BeGreaterThan 0 -Because "At least one Tier 1 memory should exist"
    }
}

Describe "Gate 2: Skill Availability Check - Prerequisites" {
    It "GitHub skills directory exists" {
        $skillsPath = Join-Path $Script:RepoRoot ".claude" "skills" "github" "scripts"
        Test-Path $skillsPath | Should -Be $true -Because "Skills directory is required for Gate 2"
    }
    
    It "At least one skill script exists" {
        $skillsPath = Join-Path $Script:RepoRoot ".claude" "skills" "github" "scripts"
        $operations = @('pr', 'issue', 'reactions', 'label', 'milestone')
        
        $skillCount = 0
        foreach ($op in $operations) {
            $opPath = Join-Path $skillsPath $op
            if (Test-Path $opPath) {
                $scripts = @(Get-ChildItem -Path $opPath -Filter "*.ps1" -ErrorAction SilentlyContinue)
                $skillCount += $scripts.Count
            }
        }
        
        $skillCount | Should -BeGreaterThan 0 -Because "At least one skill script should exist"
    }
}

Describe "Gate 3: Session Log Verification - Prerequisites" {
    It "Sessions directory exists" {
        $sessionsDir = Join-Path $Script:RepoRoot ".agents" "sessions"
        Test-Path $sessionsDir | Should -Be $true -Because "Sessions directory is required for Gate 3"
    }
    
    It "Today's session log exists" {
        $today = Get-Date -Format "yyyy-MM-dd"
        $sessionsDir = Join-Path $Script:RepoRoot ".agents" "sessions"
        $todaysSessions = Get-ChildItem -Path $sessionsDir -Filter "$today-session-*.json" -ErrorAction SilentlyContinue
        
        $todaysSessions.Count | Should -BeGreaterThan 0 -Because "At least one session log should exist for today"
    }
    
    It "Today's session log has valid JSON structure" {
        $today = Get-Date -Format "yyyy-MM-dd"
        $sessionsDir = Join-Path $Script:RepoRoot ".agents" "sessions"
        $todaysSessions = Get-ChildItem -Path $sessionsDir -Filter "$today-session-*.json" -ErrorAction SilentlyContinue | Sort-Object Name -Descending | Select-Object -First 1
        
        if ($todaysSessions) {
            { $null = Get-Content $todaysSessions.FullName -Raw | ConvertFrom-Json } | Should -Not -Throw
        }
    }
}

Describe "Gate 4: Branch Verification - Prerequisites" {
    It "Current branch is not main or master" {
        $currentBranch = (git -C $Script:RepoRoot branch --show-current).Trim()
        $currentBranch | Should -Not -BeIn @('main', 'master') -Because "Should be on a feature branch"
    }
}

Describe "Script Execution - CheckOnly Mode" {
    It "Runs in CheckOnly mode without errors" {
        { & $Script:GateScriptPath -CheckOnly } | Should -Not -Throw
    }
    
    It "Returns exit code 0 in CheckOnly mode" {
        & $Script:GateScriptPath -CheckOnly
        $LASTEXITCODE | Should -Be 0 -Because "CheckOnly mode never blocks"
    }
}

Describe "Script Execution - Skip Parameters" {
    It "Accepts -SkipMemoryGate parameter" {
        { & $Script:GateScriptPath -CheckOnly -SkipMemoryGate } | Should -Not -Throw
    }
    
    It "Accepts -SkipSkillGate parameter" {
        { & $Script:GateScriptPath -CheckOnly -SkipSkillGate } | Should -Not -Throw
    }
    
    It "Accepts -SkipSessionLogGate parameter" {
        { & $Script:GateScriptPath -CheckOnly -SkipSessionLogGate } | Should -Not -Throw
    }
    
    It "Accepts -SkipBranchGate parameter" {
        { & $Script:GateScriptPath -CheckOnly -SkipBranchGate } | Should -Not -Throw
    }
    
    It "Accepts multiple skip parameters" {
        { & $Script:GateScriptPath -CheckOnly -SkipMemoryGate -SkipSkillGate } | Should -Not -Throw
    }
}

Describe "Exit Code Compliance (ADR-035)" {
    It "Returns exit code 0 when all gates pass" {
        # Run with CheckOnly to ensure non-blocking
        & $Script:GateScriptPath -CheckOnly
        $LASTEXITCODE | Should -Be 0
    }
    
    It "Script has proper exit code documentation in header" {
        $scriptContent = Get-Content $Script:GateScriptPath -Raw
        $scriptContent | Should -Match "EXIT CODES" -Because "Script should document exit codes per ADR-035"
        $scriptContent | Should -Match "0\s+-\s+Success" -Because "Exit code 0 should be documented"
        $scriptContent | Should -Match "1\s+-\s+Logic error" -Because "Exit code 1 should be documented"
        $scriptContent | Should -Match "2\s+-\s+Gate condition not met" -Because "Exit code 2 should be documented"
        $scriptContent | Should -Match "3\s+-\s+External dependency failure" -Because "Exit code 3 should be documented"
    }
}

Describe "Script Parameter Validation" {
    It "Has CmdletBinding attribute" {
        $scriptContent = Get-Content $Script:GateScriptPath -Raw
        $scriptContent | Should -Match '\[CmdletBinding\(\)\]' -Because "Script should support common parameters"
    }
    
    It "Has proper parameter definitions" {
        $scriptContent = Get-Content $Script:GateScriptPath -Raw
        $scriptContent | Should -Match '\[switch\]\$CheckOnly'
        $scriptContent | Should -Match '\[switch\]\$SkipMemoryGate'
        $scriptContent | Should -Match '\[switch\]\$SkipSkillGate'
        $scriptContent | Should -Match '\[switch\]\$SkipSessionLogGate'
        $scriptContent | Should -Match '\[switch\]\$SkipBranchGate'
    }
}

Describe "Script Documentation" {
    It "Has synopsis" {
        $scriptContent = Get-Content $Script:GateScriptPath -Raw
        $scriptContent | Should -Match '\.SYNOPSIS' -Because "Script should have synopsis"
    }
    
    It "Has description" {
        $scriptContent = Get-Content $Script:GateScriptPath -Raw
        $scriptContent | Should -Match '\.DESCRIPTION' -Because "Script should have description"
    }
    
    It "Has examples" {
        $scriptContent = Get-Content $Script:GateScriptPath -Raw
        $scriptContent | Should -Match '\.EXAMPLE' -Because "Script should have usage examples"
    }
    
    It "References ADR-033 (Gate Architecture)" {
        $scriptContent = Get-Content $Script:GateScriptPath -Raw
        $scriptContent | Should -Match 'ADR-033' -Because "Script implements ADR-033 gates"
    }
    
    It "References ADR-035 (Exit Code Standardization)" {
        $scriptContent = Get-Content $Script:GateScriptPath -Raw
        $scriptContent | Should -Match 'ADR-035' -Because "Script follows ADR-035 exit codes"
    }
}

<#
.SYNOPSIS
    Pester tests for Complete-SessionLog.ps1 script.

.DESCRIPTION
    Tests the session log completion functionality including:
    - Auto-detection of most recent session log
    - Explicit -SessionPath usage
    - Error handling for missing files and invalid JSON
    - DryRun mode (no file modification)
    - Evidence gathering (endingCommit, handoffNotUpdated, serenaMemoryUpdated,
      changesCommitted, checklistComplete)
    - HANDOFF.md modification detection (MUST NOT violation)

    All tests are isolated from real git state. Tests that exercise git-dependent
    behavior use a temporary git repository created fresh for each test.

.NOTES
    Requires Pester 5.x or later.

    EXIT CODES:
    0  - Success: All tests passed
    1  - Error: One or more tests failed (set by Pester framework)

    See: ADR-035 Exit Code Standardization
#>

BeforeAll {
    $Script:ScriptPath = Resolve-Path (Join-Path $PSScriptRoot '..' '.claude' 'skills' 'session-end' 'scripts' 'Complete-SessionLog.ps1')

    if (-not (Test-Path $Script:ScriptPath)) {
        throw "Script not found at: $Script:ScriptPath"
    }

    # Helper: create a valid session log hashtable with all required fields
    function New-TestSessionLog {
        param(
            [int]$Number = 1,
            [string]$Date = '2026-02-07',
            [string]$Branch = 'feat/test-branch',
            [string]$StartingCommit = 'abc1234',
            [string]$Objective = 'Test objective',
            [string]$EndingCommit = '',
            [hashtable]$SessionEndOverrides = @{}
        )

        $sessionEnd = @{
            checklistComplete    = @{ level = 'MUST'; Complete = $false; Evidence = '' }
            handoffNotUpdated    = @{ level = 'MUST NOT'; Complete = $false; Evidence = '' }
            serenaMemoryUpdated  = @{ level = 'MUST'; Complete = $false; Evidence = '' }
            markdownLintRun      = @{ level = 'MUST'; Complete = $false; Evidence = '' }
            changesCommitted     = @{ level = 'MUST'; Complete = $false; Evidence = '' }
            validationPassed     = @{ level = 'MUST'; Complete = $false; Evidence = '' }
            tasksUpdated         = @{ level = 'SHOULD'; Complete = $false; Evidence = '' }
            retrospectiveInvoked = @{ level = 'SHOULD'; Complete = $false; Evidence = '' }
        }

        foreach ($key in $SessionEndOverrides.Keys) {
            $sessionEnd[$key] = $SessionEndOverrides[$key]
        }

        return @{
            session              = @{
                number         = $Number
                date           = $Date
                branch         = $Branch
                startingCommit = $StartingCommit
                objective      = $Objective
            }
            protocolCompliance   = @{
                sessionStart = @{
                    serenaActivated    = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
                    serenaInstructions = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
                    handoffRead        = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
                    sessionLogCreated  = @{ level = 'MUST'; Complete = $true; Evidence = 'This file' }
                    skillScriptsListed = @{ level = 'MUST'; Complete = $true; Evidence = 'Listed' }
                    usageMandatoryRead = @{ level = 'MUST'; Complete = $true; Evidence = 'Read' }
                    constraintsRead    = @{ level = 'MUST'; Complete = $true; Evidence = 'Read' }
                    memoriesLoaded     = @{ level = 'MUST'; Complete = $true; Evidence = 'Loaded' }
                    branchVerified     = @{ level = 'MUST'; Complete = $true; Evidence = 'Verified' }
                    notOnMain          = @{ level = 'MUST'; Complete = $true; Evidence = 'On feat/test' }
                }
                sessionEnd   = $sessionEnd
            }
            workLog              = @()
            endingCommit         = $EndingCommit
            nextSteps            = @()
        }
    }

    # Helper: write a session log to a file and return the path
    function Write-TestSessionLog {
        param(
            [string]$Directory,
            [string]$FileName,
            [hashtable]$SessionData
        )

        $filePath = Join-Path $Directory $FileName
        $SessionData | ConvertTo-Json -Depth 10 | Set-Content $filePath -Encoding utf8
        return $filePath
    }

    # Helper: create a temporary git repo with the directory structure the script expects.
    # Returns the repo root path. The repo has:
    #   .agents/sessions/          (for session logs)
    #   .agents/HANDOFF.md         (for HANDOFF modification detection)
    #   .serena/memories/          (for Serena memory detection)
    #   scripts/Validate-SessionJson.ps1  (fake validation script)
    #
    # The script under test derives $repoRoot from $PSScriptRoot (4 levels up).
    # To make it resolve correctly we create a matching directory depth:
    #   <tempRoot>/.claude/skills/session-end/scripts/
    # and copy the script there. Then $PSScriptRoot resolves to that path,
    # and Split-Path x4 yields <tempRoot>.
    function New-TestRepo {
        param(
            [switch]$ValidationFails
        )

        $tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) "csl-test-$(Get-Random)"
        New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null

        # Initialize a git repo
        Push-Location $tempRoot
        git init --initial-branch=feat/test-branch 2>&1 | Out-Null
        git config user.email 'test@test.com' 2>&1 | Out-Null
        git config user.name 'Test' 2>&1 | Out-Null

        # Create directory structure
        $sessionsDir = Join-Path $tempRoot '.agents' 'sessions'
        $handoffDir = Join-Path $tempRoot '.agents'
        $serenaDir = Join-Path $tempRoot '.serena' 'memories'
        $scriptsDir = Join-Path $tempRoot 'scripts'
        $skillScriptsDir = Join-Path $tempRoot '.claude' 'skills' 'session-end' 'scripts'

        New-Item -ItemType Directory -Path $sessionsDir -Force | Out-Null
        New-Item -ItemType Directory -Path $serenaDir -Force | Out-Null
        New-Item -ItemType Directory -Path $scriptsDir -Force | Out-Null
        New-Item -ItemType Directory -Path $skillScriptsDir -Force | Out-Null

        # Create HANDOFF.md
        'HANDOFF content' | Set-Content (Join-Path $handoffDir 'HANDOFF.md') -Encoding utf8

        # Create validation script
        $validationExitCode = if ($ValidationFails) { 1 } else { 0 }
        $validateContent = @"
param([string]`$SessionPath)
Write-Host 'Validation $(if ($ValidationFails) { "failed" } else { "passed" })'
exit $validationExitCode
"@
        $validateContent | Set-Content (Join-Path $scriptsDir 'Validate-SessionJson.ps1') -Encoding utf8

        # Copy the script under test to the matching directory depth
        Copy-Item $Script:ScriptPath -Destination $skillScriptsDir -Force

        # Initial commit with all structure files
        git add -A 2>&1 | Out-Null
        git commit -m 'Initial commit' 2>&1 | Out-Null
        Pop-Location

        return @{
            Root        = $tempRoot
            SessionsDir = $sessionsDir
            SerenaDir   = $serenaDir
            ScriptPath  = Join-Path $skillScriptsDir 'Complete-SessionLog.ps1'
        }
    }

    # Helper: run the script in a subprocess to isolate exit calls
    function Invoke-CompleteSessionLog {
        param(
            [string]$ScriptToRun,
            [string]$SessionPath = '',
            [switch]$DryRun,
            [string]$WorkingDir = ''
        )

        $args = @()
        if ($SessionPath) {
            $args += "-SessionPath '$SessionPath'"
        }
        if ($DryRun) {
            $args += '-DryRun'
        }

        $argString = $args -join ' '
        $cdCommand = if ($WorkingDir) { "Set-Location '$WorkingDir'; " } else { '' }

        $output = pwsh -NoProfile -NonInteractive -Command "${cdCommand}& '$ScriptToRun' $argString 2>&1" 2>&1
        $exitCode = $LASTEXITCODE

        return @{
            Output   = ($output -join "`n")
            ExitCode = $exitCode
        }
    }
}

Describe 'Complete-SessionLog.ps1' {

    Context 'Auto-detection of session log' {

        It 'Should find the most recent session log when no -SessionPath given' {
            $repo = New-TestRepo
            try {
                # Create two session files with different dates
                $older = New-TestSessionLog -Date '2026-02-05'
                Write-TestSessionLog -Directory $repo.SessionsDir `
                    -FileName '2026-02-05-session-1.json' -SessionData $older | Out-Null
                Start-Sleep -Milliseconds 50

                $newer = New-TestSessionLog -Date '2026-02-06'
                $newerPath = Write-TestSessionLog -Directory $repo.SessionsDir `
                    -FileName '2026-02-06-session-2.json' -SessionData $newer

                $result = Invoke-CompleteSessionLog -ScriptToRun $repo.ScriptPath `
                    -WorkingDir $repo.Root

                # Should auto-detect and mention the session file in output
                $result.Output | Should -Match 'Auto-detected'
                $result.Output | Should -Match 'session-'
            }
            finally {
                Remove-Item $repo.Root -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It 'Should exit 1 with error when no session files exist' {
            $repo = New-TestRepo
            try {
                # Sessions dir is empty (no .json files matching the pattern)
                $result = Invoke-CompleteSessionLog -ScriptToRun $repo.ScriptPath `
                    -WorkingDir $repo.Root

                $result.ExitCode | Should -Be 1
                $result.Output | Should -Match 'FAIL.*No session log found'
            }
            finally {
                Remove-Item $repo.Root -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
    }

    Context 'Explicit -SessionPath' {

        It 'Should use provided -SessionPath when specified' {
            $repo = New-TestRepo
            try {
                $session = New-TestSessionLog
                $sessionPath = Write-TestSessionLog -Directory $repo.SessionsDir `
                    -FileName '2026-02-07-session-1.json' -SessionData $session

                $result = Invoke-CompleteSessionLog -ScriptToRun $repo.ScriptPath `
                    -SessionPath $sessionPath -WorkingDir $repo.Root

                # Should NOT show "Auto-detected" message
                $result.Output | Should -Not -Match 'Auto-detected'
            }
            finally {
                Remove-Item $repo.Root -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It 'Should exit 1 when provided -SessionPath does not exist' {
            $nonExistent = Join-Path ([System.IO.Path]::GetTempPath()) "does-not-exist-$(Get-Random).json"

            $result = Invoke-CompleteSessionLog -ScriptToRun $Script:ScriptPath `
                -SessionPath $nonExistent

            $result.ExitCode | Should -Be 1
            $result.Output | Should -Match 'FAIL.*not found'
        }

        It 'Should exit 1 when -SessionPath is outside .agents/sessions (CWE-22 path traversal)' {
            $repo = New-TestRepo
            try {
                # Create a valid session file outside the sessions directory
                $outsidePath = Join-Path $repo.Root 'outside-session.json'
                $session = New-TestSessionLog
                $session | ConvertTo-Json -Depth 10 | Set-Content $outsidePath -Encoding utf8

                $result = Invoke-CompleteSessionLog -ScriptToRun $repo.ScriptPath `
                    -SessionPath $outsidePath -WorkingDir $repo.Root

                $result.ExitCode | Should -Be 1
                $result.Output | Should -Match 'FAIL.*must be inside'
            }
            finally {
                Remove-Item $repo.Root -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
    }

    Context 'Invalid JSON handling' {

        It 'Should exit 1 when session file contains invalid JSON' {
            $repo = New-TestRepo
            try {
                $badJsonPath = Join-Path $repo.SessionsDir 'bad.json'
                '{invalid json content' | Set-Content $badJsonPath -Encoding utf8

                $result = Invoke-CompleteSessionLog -ScriptToRun $repo.ScriptPath `
                    -SessionPath $badJsonPath -WorkingDir $repo.Root

                $result.ExitCode | Should -Be 1
                $result.Output | Should -Match 'FAIL.*Invalid JSON'
            }
            finally {
                Remove-Item $repo.Root -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It 'Should exit 1 when session file lacks protocolCompliance.sessionEnd' {
            $repo = New-TestRepo
            try {
                $incomplete = @{
                    session            = @{
                        number         = 1
                        date           = '2026-02-07'
                        branch         = 'feat/test'
                        startingCommit = 'abc1234'
                        objective      = 'Test'
                    }
                    protocolCompliance = @{
                        sessionStart = @{}
                    }
                }
                $sessionPath = Join-Path $repo.SessionsDir 'no-session-end.json'
                $incomplete | ConvertTo-Json -Depth 10 | Set-Content $sessionPath -Encoding utf8

                $result = Invoke-CompleteSessionLog -ScriptToRun $repo.ScriptPath `
                    -SessionPath $sessionPath -WorkingDir $repo.Root

                $result.ExitCode | Should -Be 1
                $result.Output | Should -Match 'FAIL.*missing.*sessionEnd'
            }
            finally {
                Remove-Item $repo.Root -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
    }

    Context 'DryRun mode' {

        It 'Should not modify the session file when -DryRun is specified' {
            $repo = New-TestRepo
            try {
                $session = New-TestSessionLog
                $sessionPath = Write-TestSessionLog -Directory $repo.SessionsDir `
                    -FileName '2026-02-07-session-1.json' -SessionData $session

                $originalContent = Get-Content $sessionPath -Raw

                Invoke-CompleteSessionLog -ScriptToRun $repo.ScriptPath `
                    -SessionPath $sessionPath -DryRun -WorkingDir $repo.Root | Out-Null

                $afterContent = Get-Content $sessionPath -Raw
                $afterContent | Should -Be $originalContent
            }
            finally {
                Remove-Item $repo.Root -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It 'Should display DRY RUN message when -DryRun is specified' {
            $repo = New-TestRepo
            try {
                $session = New-TestSessionLog
                $sessionPath = Write-TestSessionLog -Directory $repo.SessionsDir `
                    -FileName '2026-02-07-session-1.json' -SessionData $session

                $result = Invoke-CompleteSessionLog -ScriptToRun $repo.ScriptPath `
                    -SessionPath $sessionPath -DryRun -WorkingDir $repo.Root

                $result.Output | Should -Match 'DRY RUN'
            }
            finally {
                Remove-Item $repo.Root -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
    }

    Context 'Ending commit population' {

        It 'Should set endingCommit from git rev-parse when field is empty' {
            $repo = New-TestRepo
            try {
                $session = New-TestSessionLog -EndingCommit ''
                $sessionPath = Write-TestSessionLog -Directory $repo.SessionsDir `
                    -FileName '2026-02-07-session-1.json' -SessionData $session

                # Get the expected commit SHA
                Push-Location $repo.Root
                $expectedCommit = (git rev-parse --short HEAD 2>&1 | Out-String).Trim()
                Pop-Location

                Invoke-CompleteSessionLog -ScriptToRun $repo.ScriptPath `
                    -SessionPath $sessionPath -WorkingDir $repo.Root | Out-Null

                $updated = Get-Content $sessionPath -Raw | ConvertFrom-Json
                $updated.endingCommit | Should -Be $expectedCommit
            }
            finally {
                Remove-Item $repo.Root -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It 'Should not overwrite endingCommit when already populated' {
            $repo = New-TestRepo
            try {
                $session = New-TestSessionLog -EndingCommit 'existing1'
                $sessionPath = Write-TestSessionLog -Directory $repo.SessionsDir `
                    -FileName '2026-02-07-session-1.json' -SessionData $session

                Invoke-CompleteSessionLog -ScriptToRun $repo.ScriptPath `
                    -SessionPath $sessionPath -WorkingDir $repo.Root | Out-Null

                $updated = Get-Content $sessionPath -Raw | ConvertFrom-Json
                $updated.endingCommit | Should -Be 'existing1'
            }
            finally {
                Remove-Item $repo.Root -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
    }

    Context 'HANDOFF.md modification detection' {

        It 'Should set handoffNotUpdated evidence when HANDOFF.md is unchanged' {
            $repo = New-TestRepo
            try {
                $session = New-TestSessionLog
                $sessionPath = Write-TestSessionLog -Directory $repo.SessionsDir `
                    -FileName '2026-02-07-session-1.json' -SessionData $session

                # HANDOFF.md is committed and unchanged
                Invoke-CompleteSessionLog -ScriptToRun $repo.ScriptPath `
                    -SessionPath $sessionPath -WorkingDir $repo.Root | Out-Null

                $updated = Get-Content $sessionPath -Raw | ConvertFrom-Json -AsHashtable
                $handoff = $updated.protocolCompliance.sessionEnd.handoffNotUpdated
                $handoff.Complete | Should -Be $false
                $handoff.Evidence | Should -Match 'not modified'
            }
            finally {
                Remove-Item $repo.Root -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It 'Should detect HANDOFF.md modification as MUST NOT violation' {
            $repo = New-TestRepo
            try {
                $session = New-TestSessionLog
                $sessionPath = Write-TestSessionLog -Directory $repo.SessionsDir `
                    -FileName '2026-02-07-session-1.json' -SessionData $session

                # Modify HANDOFF.md (unstaged change)
                $handoffPath = Join-Path $repo.Root '.agents' 'HANDOFF.md'
                'Modified content' | Set-Content $handoffPath -Encoding utf8

                Invoke-CompleteSessionLog -ScriptToRun $repo.ScriptPath `
                    -SessionPath $sessionPath -WorkingDir $repo.Root | Out-Null

                $updated = Get-Content $sessionPath -Raw | ConvertFrom-Json -AsHashtable
                $handoff = $updated.protocolCompliance.sessionEnd.handoffNotUpdated
                $handoff.Complete | Should -Be $true
                $handoff.Evidence | Should -Match 'HANDOFF\.md was modified'
            }
            finally {
                Remove-Item $repo.Root -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
    }

    Context 'Serena memory updated detection' {

        It 'Should mark serenaMemoryUpdated when .serena/memories/ has staged changes' {
            $repo = New-TestRepo
            try {
                $session = New-TestSessionLog
                $sessionPath = Write-TestSessionLog -Directory $repo.SessionsDir `
                    -FileName '2026-02-07-session-1.json' -SessionData $session

                # Create a new memory file and stage it
                $memoryFile = Join-Path $repo.SerenaDir 'test-memory.md'
                'Memory content' | Set-Content $memoryFile -Encoding utf8
                Push-Location $repo.Root
                git add '.serena/memories/test-memory.md' 2>&1 | Out-Null
                Pop-Location

                Invoke-CompleteSessionLog -ScriptToRun $repo.ScriptPath `
                    -SessionPath $sessionPath -WorkingDir $repo.Root | Out-Null

                $updated = Get-Content $sessionPath -Raw | ConvertFrom-Json -AsHashtable
                $serena = $updated.protocolCompliance.sessionEnd.serenaMemoryUpdated
                $serena.Complete | Should -Be $true
                $serena.Evidence | Should -Match '\.serena/memories/'
            }
            finally {
                Remove-Item $repo.Root -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It 'Should leave serenaMemoryUpdated incomplete when no memory changes exist' {
            $repo = New-TestRepo
            try {
                $session = New-TestSessionLog
                $sessionPath = Write-TestSessionLog -Directory $repo.SessionsDir `
                    -FileName '2026-02-07-session-1.json' -SessionData $session

                # No changes to .serena/memories/
                Invoke-CompleteSessionLog -ScriptToRun $repo.ScriptPath `
                    -SessionPath $sessionPath -WorkingDir $repo.Root | Out-Null

                $updated = Get-Content $sessionPath -Raw | ConvertFrom-Json -AsHashtable
                $serena = $updated.protocolCompliance.sessionEnd.serenaMemoryUpdated
                $serena.Complete | Should -Be $false
            }
            finally {
                Remove-Item $repo.Root -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
    }

    Context 'Changes committed detection' {

        It 'Should mark changesCommitted as true when working tree is clean' {
            $repo = New-TestRepo
            try {
                $session = New-TestSessionLog
                $sessionPath = Write-TestSessionLog -Directory $repo.SessionsDir `
                    -FileName '2026-02-07-session-1.json' -SessionData $session

                # Commit the session file so working tree is clean
                Push-Location $repo.Root
                git add -A 2>&1 | Out-Null
                git commit -m 'Add session log' 2>&1 | Out-Null
                Pop-Location

                Invoke-CompleteSessionLog -ScriptToRun $repo.ScriptPath `
                    -SessionPath $sessionPath -WorkingDir $repo.Root | Out-Null

                $updated = Get-Content $sessionPath -Raw | ConvertFrom-Json -AsHashtable
                $committed = $updated.protocolCompliance.sessionEnd.changesCommitted

                # Note: the script itself modifies the session file, so after running
                # there will be uncommitted changes (the updated session file).
                # The check happens BEFORE the file is written, so it sees the state
                # at the time of evaluation. With a clean tree at the start, the
                # status --porcelain check runs before the script writes back.
                # However, the script structure evaluates Test-UncommittedChanges
                # before writing. So a clean tree at invocation time should pass.
                $committed.Complete | Should -Be $true
                $committed.Evidence | Should -Match 'committed'
            }
            finally {
                Remove-Item $repo.Root -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It 'Should leave changesCommitted incomplete when uncommitted changes exist' {
            $repo = New-TestRepo
            try {
                $session = New-TestSessionLog
                $sessionPath = Write-TestSessionLog -Directory $repo.SessionsDir `
                    -FileName '2026-02-07-session-1.json' -SessionData $session

                # Create an uncommitted file (do not commit)
                'uncommitted content' | Set-Content (Join-Path $repo.Root 'dirty.txt') -Encoding utf8

                Invoke-CompleteSessionLog -ScriptToRun $repo.ScriptPath `
                    -SessionPath $sessionPath -WorkingDir $repo.Root | Out-Null

                $updated = Get-Content $sessionPath -Raw | ConvertFrom-Json -AsHashtable
                $committed = $updated.protocolCompliance.sessionEnd.changesCommitted
                $committed.Complete | Should -Be $false
            }
            finally {
                Remove-Item $repo.Root -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
    }

    Context 'Checklist evaluation' {

        It 'Should set checklistComplete to false when MUST NOT item is violated' {
            $repo = New-TestRepo
            try {
                $session = New-TestSessionLog
                $sessionPath = Write-TestSessionLog -Directory $repo.SessionsDir `
                    -FileName '2026-02-07-session-1.json' -SessionData $session

                # Modify HANDOFF.md to trigger MUST NOT violation
                $handoffPath = Join-Path $repo.Root '.agents' 'HANDOFF.md'
                'Modified HANDOFF' | Set-Content $handoffPath -Encoding utf8

                Invoke-CompleteSessionLog -ScriptToRun $repo.ScriptPath `
                    -SessionPath $sessionPath -WorkingDir $repo.Root | Out-Null

                $updated = Get-Content $sessionPath -Raw | ConvertFrom-Json -AsHashtable
                $checklist = $updated.protocolCompliance.sessionEnd.checklistComplete
                $checklist.Complete | Should -Be $false
            }
            finally {
                Remove-Item $repo.Root -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It 'Should set checklistComplete to false when MUST items are incomplete' {
            $repo = New-TestRepo
            try {
                $session = New-TestSessionLog
                $sessionPath = Write-TestSessionLog -Directory $repo.SessionsDir `
                    -FileName '2026-02-07-session-1.json' -SessionData $session

                # serenaMemoryUpdated (MUST) will remain false because no memory changes
                # changesCommitted (MUST) will remain false because uncommitted files exist
                'dirty file' | Set-Content (Join-Path $repo.Root 'dirty.txt') -Encoding utf8

                Invoke-CompleteSessionLog -ScriptToRun $repo.ScriptPath `
                    -SessionPath $sessionPath -WorkingDir $repo.Root | Out-Null

                $updated = Get-Content $sessionPath -Raw | ConvertFrom-Json -AsHashtable
                $checklist = $updated.protocolCompliance.sessionEnd.checklistComplete
                $checklist.Complete | Should -Be $false
            }
            finally {
                Remove-Item $repo.Root -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It 'Should reflect all MUST items in checklistComplete evaluation' {
            $repo = New-TestRepo
            try {
                # Pre-mark serenaMemoryUpdated as complete via overrides
                $overrides = @{
                    serenaMemoryUpdated = @{ level = 'MUST'; Complete = $true; Evidence = 'Pre-set' }
                }
                $session = New-TestSessionLog -SessionEndOverrides $overrides
                $sessionPath = Write-TestSessionLog -Directory $repo.SessionsDir `
                    -FileName '2026-02-07-session-1.json' -SessionData $session

                # Stage memory file so the script sees it
                $memFile = Join-Path $repo.SerenaDir 'test.md'
                'memory' | Set-Content $memFile -Encoding utf8
                Push-Location $repo.Root
                git add -A 2>&1 | Out-Null
                git commit -m 'Add all' 2>&1 | Out-Null
                Pop-Location

                Invoke-CompleteSessionLog -ScriptToRun $repo.ScriptPath `
                    -SessionPath $sessionPath -WorkingDir $repo.Root | Out-Null

                $updated = Get-Content $sessionPath -Raw | ConvertFrom-Json -AsHashtable
                $checklist = $updated.protocolCompliance.sessionEnd.checklistComplete

                # checklistComplete.Evidence should be non-empty regardless of pass/fail
                $checklist.Evidence | Should -Not -BeNullOrEmpty
            }
            finally {
                Remove-Item $repo.Root -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
    }

    Context 'Validation script integration' {

        It 'Should exit 1 when Validate-SessionJson.ps1 fails' {
            $repo = New-TestRepo -ValidationFails
            try {
                $session = New-TestSessionLog
                $sessionPath = Write-TestSessionLog -Directory $repo.SessionsDir `
                    -FileName '2026-02-07-session-1.json' -SessionData $session

                $result = Invoke-CompleteSessionLog -ScriptToRun $repo.ScriptPath `
                    -SessionPath $sessionPath -WorkingDir $repo.Root

                $result.ExitCode | Should -Be 1
                $result.Output | Should -Match 'FAIL'
            }
            finally {
                Remove-Item $repo.Root -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It 'Should exit 0 when validation passes' {
            $repo = New-TestRepo
            try {
                $session = New-TestSessionLog
                $sessionPath = Write-TestSessionLog -Directory $repo.SessionsDir `
                    -FileName '2026-02-07-session-1.json' -SessionData $session

                $result = Invoke-CompleteSessionLog -ScriptToRun $repo.ScriptPath `
                    -SessionPath $sessionPath -WorkingDir $repo.Root

                $result.ExitCode | Should -Be 0
                $result.Output | Should -Match 'PASS'
            }
            finally {
                Remove-Item $repo.Root -Recurse -Force -ErrorAction SilentlyContinue
            }
        }

        It 'Should set validationPassed evidence after successful validation' {
            $repo = New-TestRepo
            try {
                $session = New-TestSessionLog
                $sessionPath = Write-TestSessionLog -Directory $repo.SessionsDir `
                    -FileName '2026-02-07-session-1.json' -SessionData $session

                Invoke-CompleteSessionLog -ScriptToRun $repo.ScriptPath `
                    -SessionPath $sessionPath -WorkingDir $repo.Root | Out-Null

                $updated = Get-Content $sessionPath -Raw | ConvertFrom-Json -AsHashtable
                $validation = $updated.protocolCompliance.sessionEnd.validationPassed
                $validation.Complete | Should -Be $true
                $validation.Evidence | Should -Match 'passed'
            }
            finally {
                Remove-Item $repo.Root -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
    }
}

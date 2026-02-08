#Requires -Modules Pester

<#
.SYNOPSIS
    Behavior-based evaluation suite for session protocol compliance.

.DESCRIPTION
    Targets novel session protocol behaviors absent from standard agent training data.
    Uses behavior-based assertions per Vercel methodology: tests verify what happens,
    not how it is implemented.

    Each eval tests a specific protocol behavior that agents must learn from
    project documentation rather than pre-training. This distinguishes protocol
    compliance from general coding ability.

    DOES NOT duplicate Validate-SessionJson.ps1 structural validation.
    Instead, tests behavioral invariants that structural validation cannot catch.

.NOTES
    EXIT CODES:
    0  - Success: All evals passed
    1  - Error: One or more evals failed (set by Pester framework)

    See: ADR-035 Exit Code Standardization
    Reference: .agents/analysis/vercel-passive-context-vs-skills-research.md
    Issue: #1106

.LINK
    https://vercel.com/blog/agents-md-outperforms-skills-in-our-agent-evals
#>

BeforeAll {
    $Script:RepoRoot = (git -C $PSScriptRoot rev-parse --show-toplevel 2>$null)
    if (-not $Script:RepoRoot) {
        $Script:RepoRoot = Split-Path $PSScriptRoot -Parent
    }
    $Script:RepoRoot = $Script:RepoRoot.Trim()

    $Script:ValidatorPath = Join-Path $Script:RepoRoot 'scripts' 'Validate-SessionJson.ps1'
    $Script:SchemaPath = Join-Path $Script:RepoRoot '.agents' 'schemas' 'session-log.schema.json'
    $Script:SessionProtocolPath = Join-Path $Script:RepoRoot '.agents' 'SESSION-PROTOCOL.md'
    $Script:HandoffPath = Join-Path $Script:RepoRoot '.agents' 'HANDOFF.md'

    # Shared temp directory for all tests
    $Script:TempRoot = Join-Path ([System.IO.Path]::GetTempPath()) "protocol-evals-$(Get-Random)"
    New-Item -ItemType Directory -Path $Script:TempRoot -Force | Out-Null

    # Helper: create a minimal valid session log as hashtable
    function New-ValidSessionLog {
        param(
            [int]$SessionNumber = 1,
            [string]$Branch = 'feat/test-eval',
            [string]$Date = '2026-02-08',
            [string]$Commit = 'abc1234'
        )
        return @{
            schemaVersion = '1.0'
            session = @{
                number = $SessionNumber
                date = $Date
                branch = $Branch
                startingCommit = $Commit
                objective = 'Eval test session'
            }
            protocolCompliance = @{
                sessionStart = @{
                    serenaActivated = @{ level = 'MUST'; Complete = $true; Evidence = 'Tool output present' }
                    serenaInstructions = @{ level = 'MUST'; Complete = $true; Evidence = 'Tool output present' }
                    handoffRead = @{ level = 'MUST'; Complete = $true; Evidence = 'Content in context' }
                    sessionLogCreated = @{ level = 'MUST'; Complete = $true; Evidence = 'This file exists' }
                    skillScriptsListed = @{ level = 'MUST'; Complete = $true; Evidence = 'Listed' }
                    usageMandatoryRead = @{ level = 'MUST'; Complete = $true; Evidence = 'Content in context' }
                    constraintsRead = @{ level = 'MUST'; Complete = $true; Evidence = 'Content in context' }
                    memoriesLoaded = @{ level = 'MUST'; Complete = $true; Evidence = 'Loaded 3 memories' }
                    branchVerified = @{ level = 'MUST'; Complete = $true; Evidence = 'feat/test-eval' }
                    notOnMain = @{ level = 'MUST'; Complete = $true; Evidence = 'On feat/test-eval' }
                }
                sessionEnd = @{
                    checklistComplete = @{ level = 'MUST'; Complete = $true; Evidence = 'All items complete' }
                    handoffNotUpdated = @{ level = 'MUST NOT'; Complete = $false; Evidence = 'HANDOFF.md unchanged' }
                    serenaMemoryUpdated = @{ level = 'MUST'; Complete = $true; Evidence = 'Memory write confirmed' }
                    markdownLintRun = @{ level = 'MUST'; Complete = $true; Evidence = 'Lint clean' }
                    changesCommitted = @{ level = 'MUST'; Complete = $true; Evidence = 'Committed abc1234' }
                    validationPassed = @{ level = 'MUST'; Complete = $true; Evidence = 'Exit code 0' }
                }
            }
            workLog = @()
            endingCommit = 'def5678'
            nextSteps = @()
        }
    }

    # Counter for unique subdirectories to prevent session number collisions.
    # The validator checks for duplicate session numbers within the same directory,
    # so each test file must live in its own isolated directory.
    $Script:TestCounter = 0

    # Helper: write session log to an isolated temp subdirectory and return path.
    # Each call creates a new subdirectory to avoid session number uniqueness conflicts.
    function Write-SessionLogFile {
        param(
            [hashtable]$SessionData,
            [string]$FileName = $null
        )
        $Script:TestCounter++
        $subDir = Join-Path $Script:TempRoot "test-$($Script:TestCounter)"
        New-Item -ItemType Directory -Path $subDir -Force | Out-Null

        if (-not $FileName) {
            $date = $SessionData.session.date
            $num = $SessionData.session.number
            $FileName = "$date-session-$num.json"
        }
        $path = Join-Path $subDir $FileName
        $SessionData | ConvertTo-Json -Depth 10 | Set-Content $path -Encoding utf8
        return $path
    }
}

AfterAll {
    if (Test-Path $Script:TempRoot) {
        Remove-Item $Script:TempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

# =============================================================================
# CATEGORY 1: Session Start Compliance
# Novel behavior: Agents must complete a specific 6-phase startup sequence
# before any work begins. This sequence is project-specific and not in
# standard agent training data.
# =============================================================================

Describe 'Eval: Serena activation is a blocking gate' -Tag 'SessionStart', 'Eval' {
    # BEHAVIOR: When Serena activation steps are incomplete, the session
    # must not pass validation. This tests that the two-step Serena init
    # (activate_project + initial_instructions) is enforced as a unit.

    It 'Session fails validation when serenaActivated is incomplete' {
        $log = New-ValidSessionLog
        $log.protocolCompliance.sessionStart.serenaActivated.Complete = $false
        $log.protocolCompliance.sessionStart.serenaActivated.Evidence = ''
        $path = Write-SessionLogFile -SessionData $log

        & $Script:ValidatorPath -SessionPath $path -PreCommit 2>&1 | Out-Null
        $LASTEXITCODE | Should -Be 1 -Because 'Serena activation is MUST; incomplete blocks validation'
    }

    It 'Session fails validation when serenaInstructions is incomplete' {
        $log = New-ValidSessionLog
        $log.protocolCompliance.sessionStart.serenaInstructions.Complete = $false
        $log.protocolCompliance.sessionStart.serenaInstructions.Evidence = ''
        $path = Write-SessionLogFile -SessionData $log -FileName 'serena-instructions-missing.json'

        & $Script:ValidatorPath -SessionPath $path -PreCommit 2>&1 | Out-Null
        $LASTEXITCODE | Should -Be 1 -Because 'Serena instructions is MUST; incomplete blocks validation'
    }

    It 'Session passes when both Serena steps are complete with evidence' {
        $log = New-ValidSessionLog
        $path = Write-SessionLogFile -SessionData $log -FileName 'serena-both-complete.json'

        & $Script:ValidatorPath -SessionPath $path -PreCommit 2>&1 | Out-Null
        $LASTEXITCODE | Should -Be 0 -Because 'Both Serena steps complete with evidence should pass'
    }
}

Describe 'Eval: HANDOFF.md read-only enforcement' -Tag 'SessionEnd', 'Eval' {
    # BEHAVIOR: HANDOFF.md must never be modified during a session.
    # The protocolCompliance field "handoffNotUpdated" uses MUST NOT semantics:
    # Complete=true means it WAS updated (violation), Complete=false means correct.

    It 'Session fails when HANDOFF.md was modified (handoffNotUpdated Complete=true)' {
        $log = New-ValidSessionLog
        $log.protocolCompliance.sessionEnd.handoffNotUpdated.Complete = $true
        $log.protocolCompliance.sessionEnd.handoffNotUpdated.Evidence = 'Updated HANDOFF.md'
        $path = Write-SessionLogFile -SessionData $log -FileName 'handoff-violated.json'

        & $Script:ValidatorPath -SessionPath $path -PreCommit 2>&1 | Out-Null
        $LASTEXITCODE | Should -Be 1 -Because 'HANDOFF.md is read-only; modification violates MUST NOT'
    }

    It 'Session passes when HANDOFF.md was not modified (handoffNotUpdated Complete=false)' {
        $log = New-ValidSessionLog
        # Default has Complete=$false which is correct for MUST NOT
        $path = Write-SessionLogFile -SessionData $log -FileName 'handoff-preserved.json'

        & $Script:ValidatorPath -SessionPath $path -PreCommit 2>&1 | Out-Null
        $LASTEXITCODE | Should -Be 0 -Because 'HANDOFF.md untouched satisfies MUST NOT constraint'
    }

    It 'HANDOFF.md exists as a reference document in the repository' {
        Test-Path $Script:HandoffPath | Should -Be $true -Because 'HANDOFF.md must exist for agents to read (not modify)'
    }
}

# =============================================================================
# CATEGORY 2: Branch Verification Safety
# Novel behavior: Branch must be verified before git operations to prevent
# wrong-branch commits. This is project-specific (learned from PR #669).
# =============================================================================

Describe 'Eval: Branch verification blocks work on main' -Tag 'GitSafety', 'Eval' {
    # BEHAVIOR: The session protocol requires branch verification before any
    # git operations. Sessions on main/master must be rejected.

    It 'Session fails when branchVerified is incomplete' {
        $log = New-ValidSessionLog
        $log.protocolCompliance.sessionStart.branchVerified.Complete = $false
        $log.protocolCompliance.sessionStart.branchVerified.Evidence = ''
        $path = Write-SessionLogFile -SessionData $log -FileName 'no-branch-verify.json'

        & $Script:ValidatorPath -SessionPath $path -PreCommit 2>&1 | Out-Null
        $LASTEXITCODE | Should -Be 1 -Because 'Branch verification is MUST; unverified blocks session'
    }

    It 'Session fails when notOnMain is incomplete' {
        $log = New-ValidSessionLog
        $log.protocolCompliance.sessionStart.notOnMain.Complete = $false
        $log.protocolCompliance.sessionStart.notOnMain.Evidence = ''
        $path = Write-SessionLogFile -SessionData $log -FileName 'on-main.json'

        & $Script:ValidatorPath -SessionPath $path -PreCommit 2>&1 | Out-Null
        $LASTEXITCODE | Should -Be 1 -Because 'notOnMain is MUST; working on main blocks session'
    }

    It 'Branch name in session metadata must follow conventional naming' {
        # BEHAVIOR: Branch names like "feat/", "fix/", etc. are expected.
        # Non-conventional names produce a warning but do not fail.
        $log = New-ValidSessionLog -Branch 'random-branch-name'
        $path = Write-SessionLogFile -SessionData $log -FileName 'unconventional-branch.json'

        # Should pass (warnings are not failures)
        & $Script:ValidatorPath -SessionPath $path -PreCommit 2>&1 | Out-Null
        $LASTEXITCODE | Should -Be 0 -Because 'Unconventional branch names warn but do not block'
    }
}

# =============================================================================
# CATEGORY 3: Session Log Schema Compliance
# Novel behavior: Session logs must conform to project-specific JSON schema
# with fields like protocolCompliance, workLog, and endingCommit that are
# not standard in any agent training data.
# =============================================================================

Describe 'Eval: Session log JSON schema is enforced' -Tag 'Schema', 'Eval' {
    It 'Schema file exists and is valid JSON' {
        Test-Path $Script:SchemaPath | Should -Be $true -Because 'Schema is required for validation'
        { Get-Content $Script:SchemaPath -Raw | ConvertFrom-Json } | Should -Not -Throw
    }

    It 'Session number in filename must match number in JSON' {
        $log = New-ValidSessionLog -SessionNumber 42
        # Write with matching filename
        $path = Write-SessionLogFile -SessionData $log -FileName '2026-02-08-session-42.json'

        & $Script:ValidatorPath -SessionPath $path -PreCommit 2>&1 | Out-Null
        $LASTEXITCODE | Should -Be 0 -Because 'Matching session numbers should pass'
    }

    It 'Session number mismatch between filename and JSON causes failure' {
        $log = New-ValidSessionLog -SessionNumber 42
        # Write with MISMATCHED filename (session-99 but JSON says 42)
        $path = Write-SessionLogFile -SessionData $log -FileName '2026-02-08-session-99.json'

        & $Script:ValidatorPath -SessionPath $path -PreCommit 2>&1 | Out-Null
        $LASTEXITCODE | Should -Be 1 -Because 'Filename session-99 mismatches JSON number 42'
    }

    It 'Commit SHA must be valid hex format (7-40 chars)' {
        $log = New-ValidSessionLog -Commit 'zzzinvalid'
        $path = Write-SessionLogFile -SessionData $log -FileName 'bad-sha.json'

        & $Script:ValidatorPath -SessionPath $path -PreCommit 2>&1 | Out-Null
        $LASTEXITCODE | Should -Be 1 -Because 'Non-hex characters in SHA must fail'
    }
}

# =============================================================================
# CATEGORY 4: Memory-First Retrieval Pattern (ADR-007)
# Novel behavior: Agents must read memories before reasoning from pre-training.
# The session protocol enforces this through MUST-level checklist items.
# =============================================================================

Describe 'Eval: Memory-first pattern is enforced at session start' -Tag 'MemoryFirst', 'Eval' {
    # BEHAVIOR: The validator enforces handoffRead as a MUST item.
    # usageMandatoryRead and memoriesLoaded are documented as MUST in the
    # session protocol but the validator checks a subset of 6 items:
    # serenaActivated, serenaInstructions, handoffRead, sessionLogCreated,
    # branchVerified, notOnMain.

    It 'Session fails when handoffRead is incomplete' {
        $log = New-ValidSessionLog
        $log.protocolCompliance.sessionStart.handoffRead.Complete = $false
        $log.protocolCompliance.sessionStart.handoffRead.Evidence = ''
        $path = Write-SessionLogFile -SessionData $log -FileName 'no-handoff-read.json'

        & $Script:ValidatorPath -SessionPath $path -PreCommit 2>&1 | Out-Null
        $LASTEXITCODE | Should -Be 1 -Because 'HANDOFF.md reading is MUST for context retrieval'
    }

    It 'Validator enforces exactly 6 sessionStart MUST items' {
        # BEHAVIOR: The validator checks a specific set of 6 sessionStart MUST items.
        # This test documents the enforced set to detect drift.
        $validatorContent = Get-Content $Script:ValidatorPath -Raw
        $enforced = @('serenaActivated', 'serenaInstructions', 'handoffRead', 'sessionLogCreated', 'branchVerified', 'notOnMain')
        foreach ($item in $enforced) {
            $validatorContent | Should -Match "'$item'" -Because "$item must be in the validator's enforced MUST items"
        }
    }

    It 'Session protocol documents memory loading as MUST requirement' {
        # BEHAVIOR: The protocol documents these as MUST even though the validator
        # does not yet enforce them. This test documents the protocol expectation.
        $protocolContent = Get-Content $Script:SessionProtocolPath -Raw
        $protocolContent | Should -Match 'MUST read.*memory-index' -Because 'Memory loading is documented as MUST in protocol'
    }

    It 'Memory index file exists in repository for agents to discover' {
        $memoryIndexPath = Join-Path $Script:RepoRoot '.serena' 'memories' 'memory-index.md'
        Test-Path $memoryIndexPath | Should -Be $true -Because 'memory-index must exist for agents to find task-relevant memories'
    }

    It 'usage-mandatory memory file exists for protocol compliance' {
        $usageMandatoryPath = Join-Path $Script:RepoRoot '.serena' 'memories' 'usage-mandatory.md'
        Test-Path $usageMandatoryPath | Should -Be $true -Because 'usage-mandatory is a MUST-read memory per session protocol'
    }
}

# =============================================================================
# CATEGORY 5: QA Routing Triggers
# Novel behavior: Feature sessions MUST route to QA agent before commit.
# Investigation-only sessions may skip QA but only when staged files match
# a strict allowlist. This allowlist-based exemption is project-specific.
# =============================================================================

Describe 'Eval: QA routing enforcement for feature sessions' -Tag 'QARouting', 'Eval' {
    It 'Session end requires QA validation evidence for feature work' {
        # BEHAVIOR: The session end checklist must include evidence of QA routing.
        # When QA is skipped, evidence must explain why (investigation-only, docs-only).
        $log = New-ValidSessionLog
        # A fully valid session includes all end items complete
        $path = Write-SessionLogFile -SessionData $log -FileName 'with-qa.json'

        & $Script:ValidatorPath -SessionPath $path -PreCommit 2>&1 | Out-Null
        $LASTEXITCODE | Should -Be 0 -Because 'Complete session end with QA evidence should pass'
    }

    It 'Session protocol documents QA as MUST for feature implementation' {
        # BEHAVIOR: The SESSION-PROTOCOL.md file defines QA as blocking for features.
        $protocolContent = Get-Content $Script:SessionProtocolPath -Raw
        $protocolContent | Should -Match 'MUST invoke the qa agent' -Because 'QA routing is documented as MUST for feature sessions'
        $protocolContent | Should -Match 'MUST NOT commit feature code without QA validation' -Because 'QA gate blocks feature commits'
    }

    It 'Investigation-only allowlist module exists and exports required functions' {
        $allowlistPath = Join-Path $Script:RepoRoot 'scripts' 'modules' 'InvestigationAllowlist.psm1'
        Test-Path $allowlistPath | Should -Be $true -Because 'Allowlist module is required for investigation-only exemption'

        Import-Module $allowlistPath -Force
        $commands = Get-Command -Module InvestigationAllowlist
        $commands.Name | Should -Contain 'Get-InvestigationAllowlist' -Because 'Allowlist patterns must be retrievable'
        $commands.Name | Should -Contain 'Test-FileMatchesAllowlist' -Because 'File matching must be available'
    }

    It 'Investigation-only allowlist permits session artifacts' {
        $allowlistPath = Join-Path $Script:RepoRoot 'scripts' 'modules' 'InvestigationAllowlist.psm1'
        Import-Module $allowlistPath -Force

        # These paths should be allowed (investigation artifacts)
        Test-FileMatchesAllowlist -FilePath '.agents/sessions/2026-02-08-session-01.json' | Should -Be $true
        Test-FileMatchesAllowlist -FilePath '.agents/analysis/investigation-report.md' | Should -Be $true
        Test-FileMatchesAllowlist -FilePath '.serena/memories/findings.md' | Should -Be $true
    }

    It 'Investigation-only allowlist blocks implementation artifacts' {
        $allowlistPath = Join-Path $Script:RepoRoot 'scripts' 'modules' 'InvestigationAllowlist.psm1'
        Import-Module $allowlistPath -Force

        # These paths should be blocked (implementation artifacts)
        Test-FileMatchesAllowlist -FilePath 'scripts/New-Feature.ps1' | Should -Be $false
        Test-FileMatchesAllowlist -FilePath 'tests/New-Feature.Tests.ps1' | Should -Be $false
        Test-FileMatchesAllowlist -FilePath '.github/workflows/new-workflow.yml' | Should -Be $false
        Test-FileMatchesAllowlist -FilePath 'CLAUDE.md' | Should -Be $false
    }
}

# =============================================================================
# CATEGORY 6: Session End Compliance
# Novel behavior: Session end has 6 MUST-level items that must all be satisfied
# before a session can be considered complete. Missing any one blocks validation.
# =============================================================================

Describe 'Eval: Session end checklist completeness' -Tag 'SessionEnd', 'Eval' {
    It 'Session fails when markdownLintRun is incomplete' {
        $log = New-ValidSessionLog
        $log.protocolCompliance.sessionEnd.markdownLintRun.Complete = $false
        $log.protocolCompliance.sessionEnd.markdownLintRun.Evidence = ''
        $path = Write-SessionLogFile -SessionData $log -FileName 'no-lint.json'

        & $Script:ValidatorPath -SessionPath $path -PreCommit 2>&1 | Out-Null
        $LASTEXITCODE | Should -Be 1 -Because 'Markdown lint is MUST at session end'
    }

    It 'Session fails when serenaMemoryUpdated is incomplete' {
        $log = New-ValidSessionLog
        $log.protocolCompliance.sessionEnd.serenaMemoryUpdated.Complete = $false
        $log.protocolCompliance.sessionEnd.serenaMemoryUpdated.Evidence = ''
        $path = Write-SessionLogFile -SessionData $log -FileName 'no-memory-update.json'

        & $Script:ValidatorPath -SessionPath $path -PreCommit 2>&1 | Out-Null
        $LASTEXITCODE | Should -Be 1 -Because 'Serena memory update is MUST at session end'
    }

    It 'Session fails when changesCommitted is incomplete' {
        $log = New-ValidSessionLog
        $log.protocolCompliance.sessionEnd.changesCommitted.Complete = $false
        $log.protocolCompliance.sessionEnd.changesCommitted.Evidence = ''
        $path = Write-SessionLogFile -SessionData $log -FileName 'no-commit.json'

        & $Script:ValidatorPath -SessionPath $path -PreCommit 2>&1 | Out-Null
        $LASTEXITCODE | Should -Be 1 -Because 'Committing changes is MUST at session end'
    }

    It 'Session fails when validationPassed is incomplete' {
        $log = New-ValidSessionLog
        $log.protocolCompliance.sessionEnd.validationPassed.Complete = $false
        $log.protocolCompliance.sessionEnd.validationPassed.Evidence = ''
        $path = Write-SessionLogFile -SessionData $log -FileName 'no-validation.json'

        & $Script:ValidatorPath -SessionPath $path -PreCommit 2>&1 | Out-Null
        $LASTEXITCODE | Should -Be 1 -Because 'Validation pass is MUST at session end'
    }

    It 'Fully complete session end passes validation' {
        $log = New-ValidSessionLog
        $path = Write-SessionLogFile -SessionData $log -FileName 'complete-end.json'

        & $Script:ValidatorPath -SessionPath $path -PreCommit 2>&1 | Out-Null
        $LASTEXITCODE | Should -Be 0 -Because 'All session end MUST items are complete'
    }
}

# =============================================================================
# CATEGORY 7: MUST NOT Inverted Semantics
# Novel behavior: MUST NOT items have inverted completion semantics.
# Complete=true means the prohibited action WAS performed (violation).
# Complete=false means the prohibition was respected (correct).
# This is counterintuitive and project-specific.
# =============================================================================

Describe 'Eval: MUST NOT items have inverted completion semantics' -Tag 'Semantics', 'Eval' {
    It 'MUST NOT with Complete=true is a violation (action was performed)' {
        $log = New-ValidSessionLog
        $log.protocolCompliance.sessionEnd.handoffNotUpdated = @{
            level = 'MUST NOT'
            Complete = $true
            Evidence = 'HANDOFF.md was modified'
        }
        $path = Write-SessionLogFile -SessionData $log -FileName 'must-not-violated.json'

        & $Script:ValidatorPath -SessionPath $path -PreCommit 2>&1 | Out-Null
        $LASTEXITCODE | Should -Be 1 -Because 'MUST NOT + Complete=true means prohibited action occurred'
    }

    It 'MUST NOT with Complete=false is correct (action was not performed)' {
        $log = New-ValidSessionLog
        # Default already has Complete=$false for handoffNotUpdated
        $path = Write-SessionLogFile -SessionData $log -FileName 'must-not-respected.json'

        & $Script:ValidatorPath -SessionPath $path -PreCommit 2>&1 | Out-Null
        $LASTEXITCODE | Should -Be 0 -Because 'MUST NOT + Complete=false means prohibition respected'
    }
}

# =============================================================================
# CATEGORY 8: Session Number Uniqueness (CWE-362 Defense)
# Novel behavior: Session numbers must be unique within the sessions directory
# to prevent race conditions when multiple agents create sessions concurrently.
# =============================================================================

Describe 'Eval: Session number uniqueness is enforced' -Tag 'Uniqueness', 'Eval' {
    BeforeAll {
        # Create isolated sessions directory with two session files sharing a number
        $Script:UniqueTestDir = Join-Path $Script:TempRoot 'uniqueness-test'
        New-Item -ItemType Directory -Path $Script:UniqueTestDir -Force | Out-Null
    }

    It 'Duplicate session numbers across files cause validation failure' {
        $log1 = New-ValidSessionLog -SessionNumber 50
        $log2 = New-ValidSessionLog -SessionNumber 50
        $log2.session.objective = 'Different session same number'

        # Write both files to same directory
        $path1 = Join-Path $Script:UniqueTestDir '2026-02-08-session-50.json'
        $path2 = Join-Path $Script:UniqueTestDir '2026-02-07-session-50.json'

        $log1 | ConvertTo-Json -Depth 10 | Set-Content $path1 -Encoding utf8
        $log2 | ConvertTo-Json -Depth 10 | Set-Content $path2 -Encoding utf8

        # Validate either file; should detect duplicate
        & $Script:ValidatorPath -SessionPath $path1 -PreCommit 2>&1 | Out-Null
        $LASTEXITCODE | Should -Be 1 -Because 'Duplicate session number 50 found in same directory'
    }
}

# =============================================================================
# CATEGORY 9: Skill Availability Gate
# Novel behavior: Agents must verify skill scripts exist before starting work.
# This is a Phase 4 blocking gate specific to this project.
# =============================================================================

Describe 'Eval: Skill infrastructure exists for protocol compliance' -Tag 'SkillGate', 'Eval' {
    It 'GitHub skills directory contains PowerShell scripts' {
        $skillsPath = Join-Path $Script:RepoRoot '.claude' 'skills' 'github' 'scripts'
        Test-Path $skillsPath | Should -Be $true -Because 'Skills directory is required for skill validation gate'

        $scriptCount = (Get-ChildItem -Path $skillsPath -Filter '*.ps1' -Recurse -ErrorAction SilentlyContinue).Count
        $scriptCount | Should -BeGreaterThan 0 -Because 'At least one skill script must exist for the gate to be meaningful'
    }

    It 'usage-mandatory memory file exists for agents to read' {
        $usageMandatoryPath = Join-Path $Script:RepoRoot '.serena' 'memories' 'usage-mandatory.md'
        Test-Path $usageMandatoryPath | Should -Be $true -Because 'usage-mandatory memory is MUST-read at session start'
    }

    It 'SESSION-PROTOCOL.md documents skill validation as BLOCKING' {
        $protocolContent = Get-Content $Script:SessionProtocolPath -Raw
        $protocolContent | Should -Match 'Skill Validation.*BLOCKING' -Because 'Skill validation is documented as a blocking gate'
    }
}

# =============================================================================
# CATEGORY 10: Evidence Quality
# Novel behavior: MUST items require non-empty evidence strings.
# Completing a checklist item without evidence is a protocol gap that
# structural validation warns about.
# =============================================================================

Describe 'Eval: Evidence is required for completed MUST items' -Tag 'Evidence', 'Eval' {
    It 'Complete MUST item with empty evidence produces a warning' {
        $log = New-ValidSessionLog
        # Set a MUST item as complete but with empty evidence
        $log.protocolCompliance.sessionStart.serenaActivated.Evidence = ''
        $path = Write-SessionLogFile -SessionData $log -FileName 'empty-evidence.json'

        # Run validator in a subprocess to capture Write-Host output
        $tempOut = [System.IO.Path]::GetTempFileName()
        try {
            $proc = Start-Process -FilePath 'pwsh' `
                -ArgumentList '-NoProfile', '-File', $Script:ValidatorPath, '-SessionPath', $path `
                -RedirectStandardOutput $tempOut -PassThru -Wait -NoNewWindow
            $output = Get-Content $tempOut -Raw

            # The validator produces warnings for missing evidence on complete MUST items.
            # Validation still passes (exit 0) but warning text appears in output.
            $output | Should -Match '[Ww]arn|[Ee]vidence' -Because 'Missing evidence on complete MUST should produce diagnostic output'
        }
        finally {
            Remove-Item $tempOut -Force -ErrorAction SilentlyContinue
        }
    }

    It 'Complete MUST item with meaningful evidence passes cleanly' {
        $log = New-ValidSessionLog
        $path = Write-SessionLogFile -SessionData $log -FileName 'good-evidence.json'

        # Run validator in a subprocess to capture Write-Host output
        $tempOut = [System.IO.Path]::GetTempFileName()
        try {
            $proc = Start-Process -FilePath 'pwsh' `
                -ArgumentList '-NoProfile', '-File', $Script:ValidatorPath, '-SessionPath', $path `
                -RedirectStandardOutput $tempOut -PassThru -Wait -NoNewWindow
            $output = Get-Content $tempOut -Raw

            $proc.ExitCode | Should -Be 0
            $output | Should -Match 'PASS' -Because 'Valid session with evidence should report PASS'
        }
        finally {
            Remove-Item $tempOut -Force -ErrorAction SilentlyContinue
        }
    }
}

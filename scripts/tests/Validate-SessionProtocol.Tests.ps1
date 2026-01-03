#Requires -Modules Pester

<#
.SYNOPSIS
    Pester tests for Validate-SessionProtocol.ps1

.DESCRIPTION
    Tests the session protocol validation functions that implement
    .agents/SESSION-PROTOCOL.md verification-based enforcement.
#>

BeforeAll {
    $scriptPath = Join-Path $PSScriptRoot ".." "Validate-SessionProtocol.ps1"

    # Dot-source the script to get access to functions
    # We need to extract just the functions, not run the main script
    $scriptContent = Get-Content -Path $scriptPath -Raw

    # Extract function definitions
    $functionPattern = '(?ms)(function\s+[\w-]+\s*\{.*?\n\})'
    $matches = [regex]::Matches($scriptContent, $functionPattern)

    # Create a temporary module with just the functions
    $functionsOnly = @"
`$ColorReset = '``e[0m'
`$ColorRed = '``e[31m'
`$ColorYellow = '``e[33m'
`$ColorGreen = '``e[32m'
`$ColorCyan = '``e[36m'
`$ColorMagenta = '``e[35m'
`$Format = 'console'

"@

    foreach ($match in $matches) {
        $functionsOnly += $match.Value + "`n`n"
    }

    # Execute the functions in current scope
    Invoke-Expression $functionsOnly

    # Create temp directory structure for tests
    $script:TestRoot = Join-Path $TestDrive "test-project"
    $script:AgentsPath = Join-Path $TestRoot ".agents"
    $script:SessionsPath = Join-Path $AgentsPath "sessions"

    New-Item -ItemType Directory -Path $SessionsPath -Force | Out-Null
}

Describe "Test-SessionLogExists" {
    It "Passes for existing session log with correct naming" {
        $sessionPath = Join-Path $SessionsPath "2025-12-17-session-01.md"
        New-Item -ItemType File -Path $sessionPath -Force | Out-Null

        $result = Test-SessionLogExists -FilePath $sessionPath
        $result.Passed | Should -BeTrue
        $result.Level | Should -Be 'MUST'
    }

    It "Fails for non-existent session log" {
        $result = Test-SessionLogExists -FilePath "nonexistent.md"
        $result.Passed | Should -BeFalse
        $result.Issues | Should -Match "does not exist"
    }

    It "Fails for incorrect naming pattern - missing session number" {
        $sessionPath = Join-Path $SessionsPath "2025-12-17-session.md"
        New-Item -ItemType File -Path $sessionPath -Force | Out-Null

        $result = Test-SessionLogExists -FilePath $sessionPath
        $result.Passed | Should -BeFalse
        $result.Issues | Should -Match "naming violation"
    }

    It "Fails for incorrect naming pattern - wrong format" {
        $sessionPath = Join-Path $SessionsPath "session-2025-12-17.md"
        New-Item -ItemType File -Path $sessionPath -Force | Out-Null

        $result = Test-SessionLogExists -FilePath $sessionPath
        $result.Passed | Should -BeFalse
        $result.Issues | Should -Match "naming violation"
    }

    It "Accepts valid session numbers 01-99" {
        $sessionPath = Join-Path $SessionsPath "2025-12-17-session-99.md"
        New-Item -ItemType File -Path $sessionPath -Force | Out-Null

        $result = Test-SessionLogExists -FilePath $sessionPath
        $result.Passed | Should -BeTrue
    }
}

Describe "Test-ProtocolComplianceSection" {
    It "Passes when Protocol Compliance section exists" {
        $content = @"
# Session Log

## Protocol Compliance

### Session Start (COMPLETE ALL before work)

| Req | Step | Status |
|-----|------|--------|
| MUST | Initialize Serena | [x] |

### Session End (COMPLETE ALL before closing)

| Req | Step | Status |
|-----|------|--------|
| MUST | Update HANDOFF.md | [ ] |
"@
        $result = Test-ProtocolComplianceSection -Content $content
        $result.Passed | Should -BeTrue
        $result.Level | Should -Be 'MUST'
    }

    It "Fails when Protocol Compliance section is missing" {
        $content = @"
# Session Log

## Work Log

Did some work.
"@
        $result = Test-ProtocolComplianceSection -Content $content
        $result.Passed | Should -BeFalse
        $result.Issues | Should -Contain "Missing 'Protocol Compliance' section"
    }

    It "Detects missing Session Start checklist" {
        $content = @"
# Session Log

## Protocol Compliance

### Session End (COMPLETE ALL before closing)

| Req | Step | Status |
|-----|------|--------|
| MUST | Update HANDOFF.md | [ ] |
"@
        $result = Test-ProtocolComplianceSection -Content $content
        $result.Issues | Should -Match "Session Start"
    }

    It "Detects missing Session End checklist" {
        $content = @"
# Session Log

## Protocol Compliance

### Session Start (COMPLETE ALL before work)

| Req | Step | Status |
|-----|------|--------|
| MUST | Initialize Serena | [x] |
"@
        $result = Test-ProtocolComplianceSection -Content $content
        $result.Issues | Should -Match "Session End"
    }
}

Describe "Test-MustRequirements" {
    It "Passes when all MUST requirements are checked" {
        $content = @"
## Protocol Compliance

| Req | Step | Status |
|-----|------|--------|
| MUST | Initialize Serena | [x] |
| MUST | Read HANDOFF.md | [x] |
| SHOULD | Search memories | [ ] |
"@
        $result = Test-MustRequirements -Content $content
        $result.Passed | Should -BeTrue
        $result.Details.CompletedMust | Should -Be 2
        $result.Details.IncompleteMust.Count | Should -Be 0
    }

    It "Fails when MUST requirements are unchecked" {
        $content = @"
## Protocol Compliance

| Req | Step | Status |
|-----|------|--------|
| MUST | Initialize Serena | [x] |
| MUST | Read HANDOFF.md | [ ] |
| SHOULD | Search memories | [ ] |
"@
        $result = Test-MustRequirements -Content $content
        $result.Passed | Should -BeFalse
        $result.Details.CompletedMust | Should -Be 1
        $result.Details.IncompleteMust.Count | Should -Be 1
    }

    It "Handles bold MUST formatting" {
        $content = @"
## Protocol Compliance

| Req | Step | Status |
|-----|------|--------|
| **MUST** | Initialize Serena | [x] |
| **MUST** | Read HANDOFF.md | [x] |
"@
        $result = Test-MustRequirements -Content $content
        $result.Passed | Should -BeTrue
        $result.Details.TotalMust | Should -Be 2
    }

    It "Counts all incomplete MUST requirements" {
        $content = @"
## Protocol Compliance

| Req | Step | Status |
|-----|------|--------|
| MUST | Step 1 | [ ] |
| MUST | Step 2 | [ ] |
| MUST | Step 3 | [ ] |
"@
        $result = Test-MustRequirements -Content $content
        $result.Passed | Should -BeFalse
        $result.Details.IncompleteMust.Count | Should -Be 3
    }
}

Describe "Test-ShouldRequirements" {
    It "Reports warnings for unchecked SHOULD requirements" {
        $content = @"
## Protocol Compliance

| Req | Step | Status |
|-----|------|--------|
| SHOULD | Search memories | [ ] |
| SHOULD | Verify git status | [ ] |
"@
        $result = Test-ShouldRequirements -Content $content
        $result.Passed | Should -BeTrue  # SHOULD doesn't fail
        $result.Details.IncompleteShould.Count | Should -Be 2
        $result.Issues.Count | Should -Be 1  # Single summary warning
    }

    It "Does not report warnings when SHOULD requirements are checked" {
        $content = @"
## Protocol Compliance

| Req | Step | Status |
|-----|------|--------|
| SHOULD | Search memories | [x] |
| SHOULD | Verify git status | [x] |
"@
        $result = Test-ShouldRequirements -Content $content
        $result.Passed | Should -BeTrue
        $result.Details.IncompleteShould.Count | Should -Be 0
        $result.Issues.Count | Should -Be 0
    }
}

Describe "Test-HandoffUpdated" {
    BeforeEach {
        # Create HANDOFF.md
        $handoffPath = Join-Path $AgentsPath "HANDOFF.md"
        New-Item -ItemType File -Path $handoffPath -Force | Out-Null
        Set-Content -Path $handoffPath -Value "# Handoff"
    }

    It "Fails when HANDOFF.md is updated recently (per protocol v1.4: MUST NOT update)" {
        $sessionPath = Join-Path $SessionsPath "2025-12-17-session-01.md"
        New-Item -ItemType File -Path $sessionPath -Force | Out-Null

        # Touch HANDOFF.md to update timestamp (violates protocol)
        $handoffPath = Join-Path $AgentsPath "HANDOFF.md"
        (Get-Item $handoffPath).LastWriteTime = Get-Date

        $result = Test-HandoffUpdated -SessionPath $sessionPath -BasePath $TestRoot
        $result.Passed | Should -BeFalse
        $result.Issues | Should -Match "MUST NOT update HANDOFF.md"
    }

    It "Passes when HANDOFF.md is older than session (correct behavior per protocol)" {
        $sessionPath = Join-Path $SessionsPath "2025-12-17-session-01.md"
        New-Item -ItemType File -Path $sessionPath -Force | Out-Null

        # Set HANDOFF.md to older date (correct - not updated during session)
        $handoffPath = Join-Path $AgentsPath "HANDOFF.md"
        (Get-Item $handoffPath).LastWriteTime = [DateTime]::Parse("2025-12-16")

        $result = Test-HandoffUpdated -SessionPath $sessionPath -BasePath $TestRoot
        $result.Passed | Should -BeTrue
    }

    It "Passes when HANDOFF.md does not exist (optional per current protocol)" {
        $sessionPath = Join-Path $SessionsPath "2025-12-17-session-01.md"
        New-Item -ItemType File -Path $sessionPath -Force | Out-Null

        # Remove HANDOFF.md (existence not required)
        $handoffPath = Join-Path $AgentsPath "HANDOFF.md"
        Remove-Item $handoffPath -Force

        $result = Test-HandoffUpdated -SessionPath $sessionPath -BasePath $TestRoot
        $result.Passed | Should -BeTrue
    }
}

Describe "Test-GitCommitEvidence" {
    It "Passes when commit SHA is present" {
        $content = @"
## Commits This Session

- `abc1234` - feat: add feature
"@
        $result = Test-GitCommitEvidence -Content $content
        $result.Passed | Should -BeTrue
    }

    It "Detects when Commits section exists but no SHA found" {
        $content = @"
## Commits This Session

- No commits yet
"@
        $result = Test-GitCommitEvidence -Content $content
        $result.Issues | Should -Match "no commit SHA found"
    }

    It "Passes when commit SHA in Commit SHA field" {
        $content = @"
### Session End

| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| MUST | Commit all changes | [x] | Commit SHA: abc1234def |
"@
        $result = Test-GitCommitEvidence -Content $content
        $result.Passed | Should -BeTrue
    }
}

Describe "Test-SessionLogCompleteness" {
    It "Passes when all expected sections present" {
        $content = @"
# Session 01 - 2025-12-17

## Session Info

- **Date**: 2025-12-17

## Protocol Compliance

### Session Start
...

## Work Log

Did some work.

## Session End
...
"@
        $result = Test-SessionLogCompleteness -Content $content
        $result.Passed | Should -BeTrue
        $result.Sections.Found.Count | Should -Be 4
        $result.Sections.Missing.Count | Should -Be 0
    }

    It "Fails when sections are missing" {
        $content = @"
# Session 01 - 2025-12-17

## Session Info

- **Date**: 2025-12-17

## Protocol Compliance

### Session Start
...
"@
        $result = Test-SessionLogCompleteness -Content $content
        $result.Passed | Should -BeFalse
        $result.Sections.Missing | Should -Contain "Work Log"
        $result.Sections.Missing | Should -Contain "Session End"
    }
}

Describe "Get-SessionLogs" {
    BeforeEach {
        # Clean up session files
        Get-ChildItem -Path $SessionsPath -Filter "*.md" -ErrorAction SilentlyContinue | Remove-Item -Force
    }

    It "Finds session logs with correct naming" {
        New-Item -ItemType File -Path (Join-Path $SessionsPath "2025-12-17-session-01.md") -Force | Out-Null
        New-Item -ItemType File -Path (Join-Path $SessionsPath "2025-12-16-session-01.md") -Force | Out-Null

        $sessions = Get-SessionLogs -BasePath $TestRoot
        $sessions.Count | Should -Be 2
    }

    It "Ignores files with wrong naming pattern" {
        New-Item -ItemType File -Path (Join-Path $SessionsPath "2025-12-17-session-01.md") -Force | Out-Null
        New-Item -ItemType File -Path (Join-Path $SessionsPath "README.md") -Force | Out-Null
        New-Item -ItemType File -Path (Join-Path $SessionsPath "notes.md") -Force | Out-Null

        $sessions = Get-SessionLogs -BasePath $TestRoot
        $sessions.Count | Should -Be 1
    }

    It "Filters by recent days" {
        # Create recent session
        $recentPath = Join-Path $SessionsPath "$(Get-Date -Format 'yyyy-MM-dd')-session-01.md"
        New-Item -ItemType File -Path $recentPath -Force | Out-Null

        # Create old session (10 days ago)
        $oldDate = (Get-Date).AddDays(-10).ToString('yyyy-MM-dd')
        $oldPath = Join-Path $SessionsPath "$oldDate-session-01.md"
        New-Item -ItemType File -Path $oldPath -Force | Out-Null

        $sessions = Get-SessionLogs -BasePath $TestRoot -Days 7
        $sessions.Count | Should -Be 1
    }

    It "Returns empty array when no sessions exist" {
        $sessions = Get-SessionLogs -BasePath $TestRoot
        $sessions.Count | Should -Be 0
    }
}

Describe "Invoke-SessionValidation" {
    BeforeEach {
        # Create HANDOFF.md with older timestamp (per protocol v1.4: MUST NOT update)
        $handoffPath = Join-Path $AgentsPath "HANDOFF.md"
        New-Item -ItemType File -Path $handoffPath -Force | Out-Null
        Set-Content -Path $handoffPath -Value "# Handoff"
        # Set to older date to simulate not being updated during session
        (Get-Item $handoffPath).LastWriteTime = [DateTime]::Parse("2025-12-16")
    }

    It "Validates complete session log successfully" {
        $sessionContent = @"
# Session 01 - 2025-12-17

## Session Info

- **Date**: 2025-12-17
- **Branch**: main

## Protocol Compliance

### Session Start (COMPLETE ALL before work)

| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| MUST | Initialize Serena | [x] | Done |
| MUST | Read HANDOFF.md | [x] | Done |
| MUST | Create session log | [x] | This file |
| SHOULD | Search memories | [x] | Searched |
| SHOULD | Verify git status | [x] | Clean |

## Work Log

Did some work.

## Session End (COMPLETE ALL before closing)

| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| MUST NOT | Update HANDOFF.md | [x] | HANDOFF.md unchanged |
| MUST | Run lint | [x] | Passed |
| MUST | Commit changes | [x] | abc1234 |

### Commits This Session

- `abc1234` - feat: add feature
"@
        $sessionPath = Join-Path $SessionsPath "2025-12-17-session-01.md"
        Set-Content -Path $sessionPath -Value $sessionContent

        $result = Invoke-SessionValidation -SessionFile $sessionPath -BasePath $TestRoot
        $result.Passed | Should -BeTrue
        $result.MustPassed | Should -BeTrue
        $result.ShouldPassed | Should -BeTrue
    }

    It "Fails validation for session with incomplete MUST requirements" {
        $sessionContent = @"
# Session 01 - 2025-12-17

## Session Info

- **Date**: 2025-12-17

## Protocol Compliance

### Session Start (COMPLETE ALL before work)

| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| MUST | Initialize Serena | [x] | Done |
| MUST | Read HANDOFF.md | [ ] | Skipped |
| MUST | Create session log | [x] | This file |

## Work Log

Did some work.

## Session End (COMPLETE ALL before closing)

| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| MUST | Update HANDOFF.md | [ ] | Not done |
| MUST | Commit changes | [ ] | Not done |
"@
        $sessionPath = Join-Path $SessionsPath "2025-12-17-session-01.md"
        Set-Content -Path $sessionPath -Value $sessionContent

        $result = Invoke-SessionValidation -SessionFile $sessionPath -BasePath $TestRoot
        $result.Passed | Should -BeFalse
        $result.MustPassed | Should -BeFalse
        $result.Issues.Count | Should -BeGreaterThan 0
    }

    It "Warns but passes for incomplete SHOULD requirements" {
        $sessionContent = @"
# Session 01 - 2025-12-17

## Session Info

- **Date**: 2025-12-17

## Protocol Compliance

### Session Start (COMPLETE ALL before work)

| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| MUST | Initialize Serena | [x] | Done |
| MUST | Read HANDOFF.md | [x] | Done |
| MUST | Create session log | [x] | This file |
| SHOULD | Search memories | [ ] | Skipped |
| SHOULD | Verify git status | [ ] | Skipped |

## Work Log

Did some work.

## Session End (COMPLETE ALL before closing)

| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| MUST NOT | Update HANDOFF.md | [x] | HANDOFF.md unchanged |
| MUST | Run lint | [x] | Done |
| MUST | Commit changes | [x] | abc1234 |

### Commits This Session

- `abc1234` - feat: add feature
"@
        $sessionPath = Join-Path $SessionsPath "2025-12-17-session-01.md"
        Set-Content -Path $sessionPath -Value $sessionContent

        $result = Invoke-SessionValidation -SessionFile $sessionPath -BasePath $TestRoot
        $result.MustPassed | Should -BeTrue
        $result.ShouldPassed | Should -BeFalse
        $result.Warnings.Count | Should -BeGreaterThan 0
    }
}

Describe "RFC 2119 Requirement Level Behavior" {
    <#
    .SYNOPSIS
        Tests that verify RFC 2119 semantics are correctly implemented.
    #>

    Context "MUST Requirements" {
        It "Treats MUST as error (protocol failure)" {
            $content = @"
## Protocol Compliance

| Req | Step | Status |
|-----|------|--------|
| MUST | Critical step | [ ] |
"@
            $result = Test-MustRequirements -Content $content
            $result.Passed | Should -BeFalse
            $result.Level | Should -Be 'MUST'
        }
    }

    Context "SHOULD Requirements" {
        It "Treats SHOULD as warning (not error)" {
            $content = @"
## Protocol Compliance

| Req | Step | Status |
|-----|------|--------|
| SHOULD | Recommended step | [ ] |
"@
            $result = Test-ShouldRequirements -Content $content
            $result.Passed | Should -BeTrue  # SHOULD doesn't cause failure
            $result.Level | Should -Be 'SHOULD'
        }
    }

    Context "Mixed Requirements" {
        It "MUST failures override SHOULD successes" {
            $content = @"
## Protocol Compliance

| Req | Step | Status |
|-----|------|--------|
| MUST | Critical step | [ ] |
| SHOULD | Recommended step | [x] |
"@
            $mustResult = Test-MustRequirements -Content $content
            $mustResult.Passed | Should -BeFalse

            $shouldResult = Test-ShouldRequirements -Content $content
            $shouldResult.Passed | Should -BeTrue
        }
    }
}

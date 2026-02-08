<#
.SYNOPSIS
    Tests for CWE mitigation features in Validate-SessionJson.ps1

.DESCRIPTION
    Pester tests covering:
    - Session number filename/JSON mismatch detection (CWE-362)
    - Duplicate session number detection as error (defense-in-depth)
    - GetFullPath resolution for path comparison

.NOTES
    EXIT CODES:
    0  - Success: All tests passed
    1  - Error: One or more tests failed (set by Pester framework)

    See: ADR-035 Exit Code Standardization
#>

Describe 'Validate-SessionJson - CWE Mitigations' {
  BeforeAll {
    $scriptPath = Join-Path $PSScriptRoot '../scripts/Validate-SessionJson.ps1'
    $tempDir = Join-Path ([System.IO.Path]::GetTempPath()) "validate-session-cwe-tests-$(Get-Random)"
    New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

    # Helper to build a valid session hashtable
    function New-ValidSession {
      param([int]$Number = 1)
      @{
        session = @{
          number = $Number
          date = '2026-01-15'
          branch = 'feat/test-cwe'
          startingCommit = 'abc1234'
          objective = 'CWE test session'
        }
        protocolCompliance = @{
          sessionStart = @{
            serenaActivated = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            serenaInstructions = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            handoffRead = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            sessionLogCreated = @{ level = 'MUST'; Complete = $true; Evidence = 'This file' }
            skillScriptsListed = @{ level = 'MUST'; Complete = $true; Evidence = 'Listed' }
            usageMandatoryRead = @{ level = 'MUST'; Complete = $true; Evidence = 'Read' }
            constraintsRead = @{ level = 'MUST'; Complete = $true; Evidence = 'Read' }
            memoriesLoaded = @{ level = 'MUST'; Complete = $true; Evidence = 'Loaded' }
            branchVerified = @{ level = 'MUST'; Complete = $true; Evidence = 'Verified' }
            notOnMain = @{ level = 'MUST'; Complete = $true; Evidence = 'On feat/test' }
          }
          sessionEnd = @{
            checklistComplete = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            handoffNotUpdated = @{ level = 'MUST NOT'; Complete = $false; Evidence = 'Not updated' }
            serenaMemoryUpdated = @{ level = 'MUST'; Complete = $true; Evidence = 'Updated' }
            markdownLintRun = @{ level = 'MUST'; Complete = $true; Evidence = 'Run' }
            changesCommitted = @{ level = 'MUST'; Complete = $true; Evidence = 'Committed' }
            validationPassed = @{ level = 'MUST'; Complete = $true; Evidence = 'Passed' }
          }
        }
        workLog = @()
        endingCommit = 'def5678'
        nextSteps = @()
      }
    }
  }

  AfterAll {
    if (Test-Path $tempDir) {
      Remove-Item $tempDir -Recurse -Force
    }
  }

  Context 'Session Number Filename/JSON Mismatch (CWE-362)' {
    It 'Should fail when filename session number differs from JSON session number' {
      $session = New-ValidSession -Number 42

      # Filename says session-99 but JSON says number=42
      $sessionPath = Join-Path $tempDir '2026-01-15-session-99.json'
      $session | ConvertTo-Json -Depth 10 | Set-Content $sessionPath -Encoding utf8

      & $scriptPath -SessionPath $sessionPath -PreCommit 2>&1 | Out-Null
      $LASTEXITCODE | Should -Be 1
    }

    It 'Should pass when filename session number matches JSON session number' {
      $session = New-ValidSession -Number 5

      $sessionPath = Join-Path $tempDir '2026-01-15-session-5.json'
      $session | ConvertTo-Json -Depth 10 | Set-Content $sessionPath -Encoding utf8

      $result = & $scriptPath -SessionPath $sessionPath -PreCommit
      $LASTEXITCODE | Should -Be 0
    }

    It 'Should skip mismatch check for filenames without session pattern' {
      $session = New-ValidSession -Number 1

      # Filename doesn't match session-(\d+) pattern, so mismatch check is skipped
      $sessionPath = Join-Path $tempDir 'custom-log.json'
      $session | ConvertTo-Json -Depth 10 | Set-Content $sessionPath -Encoding utf8

      $result = & $scriptPath -SessionPath $sessionPath -PreCommit
      $LASTEXITCODE | Should -Be 0
    }
  }

  Context 'Duplicate Session Number Detection (CWE-362 defense-in-depth)' {
    It 'Should fail when another file in the directory has the same session number' {
      # Create first session file
      $session1 = New-ValidSession -Number 10
      $path1 = Join-Path $tempDir '2026-01-15-session-10.json'
      $session1 | ConvertTo-Json -Depth 10 | Set-Content $path1 -Encoding utf8

      # Create duplicate with different date prefix but same session number
      $session2 = New-ValidSession -Number 10
      $path2 = Join-Path $tempDir '2026-01-16-session-10.json'
      $session2 | ConvertTo-Json -Depth 10 | Set-Content $path2 -Encoding utf8

      # Validate the second file; should fail because session-10 already exists
      & $scriptPath -SessionPath $path2 -PreCommit 2>&1 | Out-Null
      $LASTEXITCODE | Should -Be 1

      # Cleanup to avoid affecting other tests
      Remove-Item $path1, $path2 -Force
    }

    It 'Should pass when no duplicates exist' {
      $session = New-ValidSession -Number 777

      $sessionPath = Join-Path $tempDir '2026-01-15-session-777.json'
      $session | ConvertTo-Json -Depth 10 | Set-Content $sessionPath -Encoding utf8

      $result = & $scriptPath -SessionPath $sessionPath -PreCommit
      $LASTEXITCODE | Should -Be 0

      Remove-Item $sessionPath -Force
    }

    It 'Should not flag the file against itself' {
      $session = New-ValidSession -Number 888

      $sessionPath = Join-Path $tempDir '2026-01-15-session-888.json'
      $session | ConvertTo-Json -Depth 10 | Set-Content $sessionPath -Encoding utf8

      # Validating the only file with this number should pass
      $result = & $scriptPath -SessionPath $sessionPath -PreCommit
      $LASTEXITCODE | Should -Be 0

      Remove-Item $sessionPath -Force
    }
  }

  Context 'Path Resolution (GetFullPath)' {
    It 'Should correctly resolve relative paths for self-exclusion' {
      $session = New-ValidSession -Number 555

      $sessionPath = Join-Path $tempDir '2026-01-15-session-555.json'
      $session | ConvertTo-Json -Depth 10 | Set-Content $sessionPath -Encoding utf8

      # Use a relative path with ../ to test GetFullPath resolution
      $relativePath = Join-Path $tempDir '..' (Split-Path $tempDir -Leaf) '2026-01-15-session-555.json'

      $result = & $scriptPath -SessionPath $relativePath -PreCommit
      $LASTEXITCODE | Should -Be 0

      Remove-Item $sessionPath -Force
    }
  }
}

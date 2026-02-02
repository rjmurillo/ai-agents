Describe 'Validate-SessionJson' {
  BeforeAll {
    $scriptPath = Join-Path $PSScriptRoot '../scripts/Validate-SessionJson.ps1'
    $tempDir = Join-Path ([System.IO.Path]::GetTempPath()) "validate-session-tests-$(Get-Random)"
    New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
  }

  AfterAll {
    if (Test-Path $tempDir) {
      Remove-Item $tempDir -Recurse -Force
    }
  }

  Context 'Valid Session Structure' {
    It 'Should pass validation for a complete valid session' {
      $validSession = @{
        session = @{
          number = 1
          date = '2026-01-09'
          branch = 'feat/test-branch'
          startingCommit = 'abc1234'
          objective = 'Test objective'
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

      $sessionPath = Join-Path $tempDir 'valid-session.json'
      $validSession | ConvertTo-Json -Depth 10 | Set-Content $sessionPath -Encoding utf8

      $result = & $scriptPath -SessionPath $sessionPath -PreCommit
      $LASTEXITCODE | Should -Be 0
    }
  }

  Context 'Missing Required Sections' {
    It 'Should fail when session section is missing' {
      $invalidSession = @{
        protocolCompliance = @{
          sessionStart = @{}
          sessionEnd = @{}
        }
      }

      $sessionPath = Join-Path $tempDir 'missing-session.json'
      $invalidSession | ConvertTo-Json -Depth 10 | Set-Content $sessionPath -Encoding utf8

      & $scriptPath -SessionPath $sessionPath -PreCommit 2>&1 | Out-Null
      $LASTEXITCODE | Should -Be 1
    }

    It 'Should fail when protocolCompliance section is missing' {
      $invalidSession = @{
        session = @{
          number = 1
          date = '2026-01-09'
          branch = 'feat/test'
          startingCommit = 'abc1234'
          objective = 'Test'
        }
      }

      $sessionPath = Join-Path $tempDir 'missing-protocol.json'
      $invalidSession | ConvertTo-Json -Depth 10 | Set-Content $sessionPath -Encoding utf8

      & $scriptPath -SessionPath $sessionPath -PreCommit 2>&1 | Out-Null
      $LASTEXITCODE | Should -Be 1
    }

    It 'Should fail when sessionStart is missing' {
      $invalidSession = @{
        session = @{
          number = 1
          date = '2026-01-09'
          branch = 'feat/test'
          startingCommit = 'abc1234'
          objective = 'Test'
        }
        protocolCompliance = @{
          sessionEnd = @{}
        }
      }

      $sessionPath = Join-Path $tempDir 'missing-start.json'
      $invalidSession | ConvertTo-Json -Depth 10 | Set-Content $sessionPath -Encoding utf8

      & $scriptPath -SessionPath $sessionPath -PreCommit 2>&1 | Out-Null
      $LASTEXITCODE | Should -Be 1
    }

    It 'Should fail when sessionEnd is missing' {
      $invalidSession = @{
        session = @{
          number = 1
          date = '2026-01-09'
          branch = 'feat/test'
          startingCommit = 'abc1234'
          objective = 'Test'
        }
        protocolCompliance = @{
          sessionStart = @{}
        }
      }

      $sessionPath = Join-Path $tempDir 'missing-end.json'
      $invalidSession | ConvertTo-Json -Depth 10 | Set-Content $sessionPath -Encoding utf8

      & $scriptPath -SessionPath $sessionPath -PreCommit 2>&1 | Out-Null
      $LASTEXITCODE | Should -Be 1
    }
  }

  Context 'Missing Required Fields' {
    It 'Should fail when session.number is missing' {
      $invalidSession = @{
        session = @{
          date = '2026-01-09'
          branch = 'feat/test'
          startingCommit = 'abc1234'
          objective = 'Test'
        }
        protocolCompliance = @{
          sessionStart = @{}
          sessionEnd = @{}
        }
      }

      $sessionPath = Join-Path $tempDir 'missing-number.json'
      $invalidSession | ConvertTo-Json -Depth 10 | Set-Content $sessionPath -Encoding utf8

      & $scriptPath -SessionPath $sessionPath -PreCommit 2>&1 | Out-Null
      $LASTEXITCODE | Should -Be 1
    }

    It 'Should fail when session.branch is empty' {
      $invalidSession = @{
        session = @{
          number = 1
          date = '2026-01-09'
          branch = ''
          startingCommit = 'abc1234'
          objective = 'Test'
        }
        protocolCompliance = @{
          sessionStart = @{}
          sessionEnd = @{}
        }
      }

      $sessionPath = Join-Path $tempDir 'empty-branch.json'
      $invalidSession | ConvertTo-Json -Depth 10 | Set-Content $sessionPath -Encoding utf8

      & $scriptPath -SessionPath $sessionPath -PreCommit 2>&1 | Out-Null
      $LASTEXITCODE | Should -Be 1
    }
  }

  Context 'MUST Requirements Validation' {
    It 'Should fail when MUST item in sessionStart is incomplete' {
      $invalidSession = @{
        session = @{
          number = 1
          date = '2026-01-09'
          branch = 'feat/test'
          startingCommit = 'abc1234'
          objective = 'Test'
        }
        protocolCompliance = @{
          sessionStart = @{
            serenaActivated = @{ level = 'MUST'; Complete = $false; Evidence = '' }
          }
          sessionEnd = @{
            checklistComplete = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            handoffNotUpdated = @{ level = 'MUST NOT'; Complete = $false; Evidence = '' }
            serenaMemoryUpdated = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            markdownLintRun = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            changesCommitted = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            validationPassed = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
          }
        }
      }

      $sessionPath = Join-Path $tempDir 'incomplete-must.json'
      $invalidSession | ConvertTo-Json -Depth 10 | Set-Content $sessionPath -Encoding utf8

      & $scriptPath -SessionPath $sessionPath -PreCommit 2>&1 | Out-Null
      $LASTEXITCODE | Should -Be 1
    }

    It 'Should fail when MUST item in sessionEnd is incomplete' {
      $invalidSession = @{
        session = @{
          number = 1
          date = '2026-01-09'
          branch = 'feat/test'
          startingCommit = 'abc1234'
          objective = 'Test'
        }
        protocolCompliance = @{
          sessionStart = @{
            serenaActivated = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            serenaInstructions = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            handoffRead = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            sessionLogCreated = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            skillScriptsListed = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            usageMandatoryRead = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            constraintsRead = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            memoriesLoaded = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            branchVerified = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            notOnMain = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
          }
          sessionEnd = @{
            checklistComplete = @{ level = 'MUST'; Complete = $false; Evidence = '' }
            handoffNotUpdated = @{ level = 'MUST NOT'; Complete = $false; Evidence = '' }
          }
        }
      }

      $sessionPath = Join-Path $tempDir 'incomplete-end-must.json'
      $invalidSession | ConvertTo-Json -Depth 10 | Set-Content $sessionPath -Encoding utf8

      & $scriptPath -SessionPath $sessionPath -PreCommit 2>&1 | Out-Null
      $LASTEXITCODE | Should -Be 1
    }
  }

  Context 'MUST NOT Validation' {
    It 'Should fail when handoffNotUpdated (MUST NOT) is violated' {
      $invalidSession = @{
        session = @{
          number = 1
          date = '2026-01-09'
          branch = 'feat/test'
          startingCommit = 'abc1234'
          objective = 'Test'
        }
        protocolCompliance = @{
          sessionStart = @{
            serenaActivated = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
          }
          sessionEnd = @{
            checklistComplete = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            handoffNotUpdated = @{ level = 'MUST NOT'; Complete = $true; Evidence = 'Updated HANDOFF.md' }
            serenaMemoryUpdated = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            markdownLintRun = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            changesCommitted = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            validationPassed = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
          }
        }
      }

      $sessionPath = Join-Path $tempDir 'must-not-violated.json'
      $invalidSession | ConvertTo-Json -Depth 10 | Set-Content $sessionPath -Encoding utf8

      & $scriptPath -SessionPath $sessionPath -PreCommit 2>&1 | Out-Null
      $LASTEXITCODE | Should -Be 1
    }
  }

  Context 'Commit SHA Format Validation' {
    It 'Should fail for invalid commit SHA (too short)' {
      $invalidSession = @{
        session = @{
          number = 1
          date = '2026-01-09'
          branch = 'feat/test'
          startingCommit = 'abc12'  # Only 5 chars, minimum is 7
          objective = 'Test'
        }
        protocolCompliance = @{
          sessionStart = @{}
          sessionEnd = @{}
        }
      }

      $sessionPath = Join-Path $tempDir 'invalid-sha-short.json'
      $invalidSession | ConvertTo-Json -Depth 10 | Set-Content $sessionPath -Encoding utf8

      & $scriptPath -SessionPath $sessionPath -PreCommit 2>&1 | Out-Null
      $LASTEXITCODE | Should -Be 1
    }

    It 'Should fail for invalid commit SHA (invalid characters)' {
      $invalidSession = @{
        session = @{
          number = 1
          date = '2026-01-09'
          branch = 'feat/test'
          startingCommit = 'xyz1234'  # 'x', 'y', 'z' are not valid hex
          objective = 'Test'
        }
        protocolCompliance = @{
          sessionStart = @{}
          sessionEnd = @{}
        }
      }

      $sessionPath = Join-Path $tempDir 'invalid-sha-chars.json'
      $invalidSession | ConvertTo-Json -Depth 10 | Set-Content $sessionPath -Encoding utf8

      & $scriptPath -SessionPath $sessionPath -PreCommit 2>&1 | Out-Null
      $LASTEXITCODE | Should -Be 1
    }

    It 'Should pass for valid 7-char commit SHA' {
      $validSession = @{
        session = @{
          number = 1
          date = '2026-01-09'
          branch = 'feat/test'
          startingCommit = 'abc1234'  # Valid 7-char SHA
          objective = 'Test'
        }
        protocolCompliance = @{
          sessionStart = @{
            serenaActivated = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            serenaInstructions = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            handoffRead = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            sessionLogCreated = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            skillScriptsListed = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            usageMandatoryRead = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            constraintsRead = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            memoriesLoaded = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            branchVerified = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            notOnMain = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
          }
          sessionEnd = @{
            checklistComplete = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            handoffNotUpdated = @{ level = 'MUST NOT'; Complete = $false; Evidence = '' }
            serenaMemoryUpdated = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            markdownLintRun = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            changesCommitted = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            validationPassed = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
          }
        }
      }

      $sessionPath = Join-Path $tempDir 'valid-sha-7.json'
      $validSession | ConvertTo-Json -Depth 10 | Set-Content $sessionPath -Encoding utf8

      $result = & $scriptPath -SessionPath $sessionPath -PreCommit
      $LASTEXITCODE | Should -Be 0
    }

    It 'Should pass for valid 40-char commit SHA' {
      $validSession = @{
        session = @{
          number = 1
          date = '2026-01-09'
          branch = 'feat/test'
          startingCommit = 'abc1234567890abcdef1234567890abcdef12340'  # Valid 40-char SHA
          objective = 'Test'
        }
        protocolCompliance = @{
          sessionStart = @{
            serenaActivated = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            serenaInstructions = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            handoffRead = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            sessionLogCreated = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            skillScriptsListed = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            usageMandatoryRead = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            constraintsRead = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            memoriesLoaded = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            branchVerified = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            notOnMain = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
          }
          sessionEnd = @{
            checklistComplete = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            handoffNotUpdated = @{ level = 'MUST NOT'; Complete = $false; Evidence = '' }
            serenaMemoryUpdated = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            markdownLintRun = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            changesCommitted = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            validationPassed = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
          }
        }
      }

      $sessionPath = Join-Path $tempDir 'valid-sha-40.json'
      $validSession | ConvertTo-Json -Depth 10 | Set-Content $sessionPath -Encoding utf8

      $result = & $scriptPath -SessionPath $sessionPath -PreCommit
      $LASTEXITCODE | Should -Be 0
    }
  }

  Context 'Branch Naming Validation' {
    It 'Should pass with warning for non-conventional branch name' -Tag 'Warning' {
      # Note: This test just verifies that non-conventional branches pass validation (no error exit code)
      # The warning is displayed but doesn't cause failure
      $sessionWithWarning = @{
        session = @{
          number = 1
          date = '2026-01-09'
          branch = 'my-custom-branch'  # Doesn't follow feat/, fix/, etc.
          startingCommit = 'abc1234'
          objective = 'Test'
        }
        protocolCompliance = @{
          sessionStart = @{
            serenaActivated = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            serenaInstructions = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            handoffRead = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            sessionLogCreated = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            skillScriptsListed = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            usageMandatoryRead = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            constraintsRead = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            memoriesLoaded = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            branchVerified = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            notOnMain = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
          }
          sessionEnd = @{
            checklistComplete = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            handoffNotUpdated = @{ level = 'MUST NOT'; Complete = $false; Evidence = '' }
            serenaMemoryUpdated = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            markdownLintRun = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            changesCommitted = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            validationPassed = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
          }
        }
      }

      $sessionPath = Join-Path $tempDir 'non-conventional-branch.json'
      $sessionWithWarning | ConvertTo-Json -Depth 10 | Set-Content $sessionPath -Encoding utf8

      # Should pass (exit 0) even with non-conventional branch
      $result = & $scriptPath -SessionPath $sessionPath -PreCommit
      $LASTEXITCODE | Should -Be 0
    }
  }

  Context 'Invalid JSON Handling' {
    It 'Should fail gracefully for malformed JSON' {
      $sessionPath = Join-Path $tempDir 'malformed.json'
      '{invalid json' | Set-Content $sessionPath -Encoding utf8

      # Script should fail (exit non-zero)
      { & $scriptPath -SessionPath $sessionPath -PreCommit -ErrorAction Stop } | Should -Throw
    }

    It 'Should fail when session file does not exist' {
      $nonExistentPath = Join-Path $tempDir 'does-not-exist.json'

      # Script should fail (exit non-zero)
      { & $scriptPath -SessionPath $nonExistentPath -PreCommit -ErrorAction Stop } | Should -Throw
    }
  }

  Context 'Case-Insensitive Key Lookup' {
    It 'Should handle property names with different casing (Complete vs complete)' {
      # Test that the validator handles both PascalCase and lowercase property names
      $mixedCaseSession = @{
        session = @{
          number = 1
          date = '2026-01-09'
          branch = 'feat/test'
          startingCommit = 'abc1234'
          objective = 'Test'
        }
        protocolCompliance = @{
          sessionStart = @{
            serenaActivated = @{ level = 'MUST'; complete = $true; evidence = 'Done' }  # lowercase
          }
          sessionEnd = @{
            checklistComplete = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }  # PascalCase
            handoffNotUpdated = @{ level = 'MUST NOT'; complete = $false; evidence = '' }  # lowercase
            serenaMemoryUpdated = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }  # PascalCase
            markdownLintRun = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            changesCommitted = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
            validationPassed = @{ level = 'MUST'; Complete = $true; Evidence = 'Done' }
          }
        }
      }

      $sessionPath = Join-Path $tempDir 'mixed-case.json'
      $mixedCaseSession | ConvertTo-Json -Depth 10 | Set-Content $sessionPath -Encoding utf8

      # Should still pass due to case-insensitive key lookup
      $result = & $scriptPath -SessionPath $sessionPath -PreCommit
      $LASTEXITCODE | Should -Be 0
    }
  }
}

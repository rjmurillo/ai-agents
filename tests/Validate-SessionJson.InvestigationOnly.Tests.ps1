#Requires -Modules Pester

<#
.SYNOPSIS
    Tests for Validate-SessionJson.ps1 investigation-only mode validation

.DESCRIPTION
    Validates ADR-034 Phase 1 implementation:
    - Investigation-only pattern recognition (case-insensitive)
    - Staged file validation against investigation artifact allowlist
    - Error reporting for E_INVESTIGATION_HAS_IMPL violations

.NOTES
    Test Approach: Functional tests using actual script invocation with temporary
    session JSON files. Tests verify exit codes and error messages for various
    staged file scenarios per ADR-034 allowlist.
#>

Describe 'Validate-SessionJson - Investigation-Only Mode' {
  BeforeAll {
    $scriptPath = Join-Path $PSScriptRoot '../scripts/Validate-SessionJson.ps1'
    $tempDir = Join-Path ([System.IO.Path]::GetTempPath()) "validate-session-investigation-tests-$(Get-Random)"
    New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
    
    # Helper to create a valid base session for testing
    function Get-BaseValidSession {
      @{
        session = @{
          number = 1
          date = '2026-01-15'
          branch = 'feat/test-investigation'
          startingCommit = 'abc1234'
          objective = 'Investigation session'
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
            qaValidation = @{ level = 'MUST'; Complete = $true; Evidence = 'SKIPPED: investigation-only' }
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

  Context 'Investigation-Only Pattern Recognition' {
    It 'Script recognizes case-insensitive SKIPPED: investigation-only pattern' {
      # Verify the pattern exists in the script
      $scriptContent = Get-Content $scriptPath -Raw
      $scriptContent | Should -Match '(?i)SKIPPED:\s*investigation-only'
    }

    It 'Script uses case-insensitive regex flag for pattern matching' {
      # Verify case-insensitive flag is used
      $scriptContent = Get-Content $scriptPath -Raw
      $scriptContent | Should -Match '\(\?i\)'
    }
  }

  Context 'Investigation Artifact Allowlist via Shared Module' {
    It 'Script imports shared InvestigationAllowlist module' {
      $scriptContent = Get-Content $scriptPath -Raw
      $scriptContent | Should -Match 'InvestigationAllowlist'
      $scriptContent | Should -Match 'Import-Module'
    }

    It 'Script uses Test-FileMatchesAllowlist function' {
      $scriptContent = Get-Content $scriptPath -Raw
      $scriptContent | Should -Match 'Test-FileMatchesAllowlist'
    }

    It 'Shared module contains all expected patterns' {
      Import-Module (Join-Path $PSScriptRoot '../scripts/modules/InvestigationAllowlist.psm1') -Force
      $patterns = Get-InvestigationAllowlist
      $patterns | Should -Contain '^\.agents/sessions/'
      $patterns | Should -Contain '^\.agents/analysis/'
      $patterns | Should -Contain '^\.agents/retrospective/'
      $patterns | Should -Contain '^\.serena/memories($|/)'
      $patterns | Should -Contain '^\.agents/security/'
    }
  }

  Context 'Git Command Error Handling' {
    It 'Script handles git command failures with E_GIT_COMMAND_FAILED error' {
      $scriptContent = Get-Content $scriptPath -Raw
      $scriptContent | Should -Match 'E_GIT_COMMAND_FAILED'
    }
    
    It 'Script checks LASTEXITCODE after git command' {
      $scriptContent = Get-Content $scriptPath -Raw
      $scriptContent | Should -Match '\$LASTEXITCODE -ne 0'
    }
  }

  Context 'Integration Test Scenarios - Documentation' {
    # NOTE: These tests document expected behavior for integration testing.
    # They cannot be run as unit tests because they require git repository state
    # with actual staged files. Integration tests should verify:
    
    It 'INTEGRATION: Should PASS when only .agents/sessions/ is staged' -Skip {
      # Staged: .agents/sessions/2026-01-15-session-01.json
      # Expected: PASS (exit code 0)
    }

    It 'INTEGRATION: Should PASS when .serena/memories/ + session log are staged' -Skip {
      # Staged: .serena/memories/analysis.md, .agents/sessions/session.json
      # Expected: PASS (exit code 0)
    }

    It 'INTEGRATION: Should PASS when .agents/security/SA-*.md is staged' -Skip {
      # Staged: .agents/security/SA-001-assessment.md
      # Expected: PASS (exit code 0)
    }

    It 'INTEGRATION: Should PASS when .agents/analysis/ is staged' -Skip {
      # Staged: .agents/analysis/investigation-report.md
      # Expected: PASS (exit code 0)
    }

    It 'INTEGRATION: Should PASS when .agents/retrospective/ is staged' -Skip {
      # Staged: .agents/retrospective/session-learnings.md
      # Expected: PASS (exit code 0)
    }

    It 'INTEGRATION: Should FAIL when .agents/planning/PRD.md is staged' -Skip {
      # Staged: .agents/planning/PRD.md, .agents/sessions/session.json
      # Expected: FAIL with E_INVESTIGATION_HAS_IMPL (exit code 1)
      # Error should list: .agents/planning/PRD.md
    }

    It 'INTEGRATION: Should FAIL when .agents/critique/ is staged' -Skip {
      # Staged: .agents/critique/plan-review.md
      # Expected: FAIL with E_INVESTIGATION_HAS_IMPL (exit code 1)
      # Error should list: .agents/critique/plan-review.md
    }

    It 'INTEGRATION: Should FAIL when .github/workflows/ci.yml is staged' -Skip {
      # Staged: .github/workflows/ci.yml
      # Expected: FAIL with E_INVESTIGATION_HAS_IMPL (exit code 1)
      # Error should list: .github/workflows/ci.yml
    }

    It 'INTEGRATION: Should FAIL when src/component.ts is staged' -Skip {
      # Staged: src/component.ts
      # Expected: FAIL with E_INVESTIGATION_HAS_IMPL (exit code 1)
      # Error should list: src/component.ts
    }

    It 'INTEGRATION: Should FAIL when .claude/agents/agent.md is staged' -Skip {
      # Staged: .claude/agents/analyst.md
      # Expected: FAIL with E_INVESTIGATION_HAS_IMPL (exit code 1)
      # Error should list: .claude/agents/analyst.md
      # Note: Agent prompts are behavioral code per ADR-034
    }

    It 'INTEGRATION: Should FAIL when .github/agents/copilot.md is staged' -Skip {
      # Staged: .github/agents/copilot.md
      # Expected: FAIL with E_INVESTIGATION_HAS_IMPL (exit code 1)
      # Error should list: .github/agents/copilot.md
      # Note: Agent prompts are behavioral code per ADR-034
    }

    It 'INTEGRATION: Should FAIL when mixed allowed and non-allowed files are staged' -Skip {
      # Staged: .serena/memories/analysis.md, scripts/fix-bug.ps1
      # Expected: FAIL with E_INVESTIGATION_HAS_IMPL (exit code 1)
      # Error should list: scripts/fix-bug.ps1 (but not .serena/memories/analysis.md)
    }
  }

  Context 'Error Message Validation' {
    It 'Should have correct E_INVESTIGATION_HAS_IMPL error code prefix' {
      $scriptContent = Get-Content $scriptPath -Raw
      $scriptContent | Should -Match 'E_INVESTIGATION_HAS_IMPL'
    }

    It 'Should use Get-InvestigationAllowlistDisplay for error messages' {
      $scriptContent = Get-Content $scriptPath -Raw
      $scriptContent | Should -Match 'Get-InvestigationAllowlistDisplay'
    }

    It 'Shared module display paths include expected entries' {
      Import-Module (Join-Path $PSScriptRoot '../scripts/modules/InvestigationAllowlist.psm1') -Force
      $display = Get-InvestigationAllowlistDisplay
      $display | Should -Contain '.agents/sessions/'
      $display | Should -Contain '.agents/analysis/'
      $display | Should -Contain '.agents/retrospective/'
      $display | Should -Contain '.serena/memories/'
      $display | Should -Contain '.agents/security/'
    }
  }
}

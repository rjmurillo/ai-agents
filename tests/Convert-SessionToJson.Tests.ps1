<#
.SYNOPSIS
  Pester tests for Convert-SessionToJson.ps1

.DESCRIPTION
  Tests markdown to JSON session log migration functionality.
#>

BeforeAll {
  $ScriptPath = Join-Path $PSScriptRoot '..' 'scripts' 'Convert-SessionToJson.ps1'

  # Create temp directory for test files
  $TestRoot = Join-Path ([System.IO.Path]::GetTempPath()) "session-migration-tests-$(Get-Random)"
  New-Item -ItemType Directory -Path $TestRoot -Force | Out-Null
}

AfterAll {
  # Cleanup test directory
  if (Test-Path $TestRoot) {
    Remove-Item $TestRoot -Recurse -Force
  }
}

Describe 'Convert-SessionToJson.ps1' {
  Context 'Parameter Validation' {
    It 'Requires -Path parameter' {
      { & $ScriptPath } | Should -Throw
    }

    It 'Fails on non-existent path' {
      { & $ScriptPath -Path '/nonexistent/path' } | Should -Throw
    }
  }

  Context 'Single File Migration' {
    BeforeEach {
      $TestFile = Join-Path $TestRoot '2026-01-09-session-999.md'
      $TestContent = @'
# Session 999

**Branch**: feat/test-branch
**Starting Commit**: abc1234

## Objective

Test objective for migration

## Session Start Checklist

| Check | Done | Evidence |
|-------|------|----------|
| activate_project | [x] | Tool output |
| initial_instructions | [x] | Read |
| HANDOFF.md | [x] | In context |
| Create session log | [x] | This file |
| usage-mandatory | [x] | Memory read |
| CONSTRAINTS | [x] | Read |
| memory loaded | [x] | Loaded |
| verify branch | [x] | feat/test-branch |
| not main | [x] | Confirmed |

## Session End Checklist

| Check | Done | Evidence |
|-------|------|----------|
| Complete session log | [x] | All sections |
| Serena memory | [x] | Updated |
| markdownlint | [x] | Ran |
| Commit changes | [x] | abc1234 |
| Validate Session | [x] | Passed |
'@
      Set-Content -Path $TestFile -Value $TestContent -Encoding utf8
    }

    It 'Creates JSON file alongside markdown' {
      & $ScriptPath -Path $TestFile | Out-Null
      $JsonPath = $TestFile -replace '\.md$', '.json'
      Test-Path $JsonPath | Should -Be $true
    }

    It 'Extracts session number from filename' {
      & $ScriptPath -Path $TestFile -Force | Out-Null
      $JsonPath = $TestFile -replace '\.md$', '.json'
      $json = Get-Content $JsonPath -Raw | ConvertFrom-Json
      $json.session.number | Should -Be 999
    }

    It 'Extracts date from filename' {
      & $ScriptPath -Path $TestFile -Force | Out-Null
      $JsonPath = $TestFile -replace '\.md$', '.json'
      $json = Get-Content $JsonPath -Raw | ConvertFrom-Json
      $json.session.date | Should -Be '2026-01-09'
    }

    It 'Extracts branch from content' {
      & $ScriptPath -Path $TestFile -Force | Out-Null
      $JsonPath = $TestFile -replace '\.md$', '.json'
      $json = Get-Content $JsonPath -Raw | ConvertFrom-Json
      $json.session.branch | Should -Be 'feat/test-branch'
    }

    It 'Extracts starting commit from content' {
      & $ScriptPath -Path $TestFile -Force | Out-Null
      $JsonPath = $TestFile -replace '\.md$', '.json'
      $json = Get-Content $JsonPath -Raw | ConvertFrom-Json
      $json.session.startingCommit | Should -Be 'abc1234'
    }

    It 'Extracts objective from content' {
      & $ScriptPath -Path $TestFile -Force | Out-Null
      $JsonPath = $TestFile -replace '\.md$', '.json'
      $json = Get-Content $JsonPath -Raw | ConvertFrom-Json
      $json.session.objective | Should -Be 'Test objective for migration'
    }

    It 'Marks completed checklist items as complete' {
      & $ScriptPath -Path $TestFile -Force | Out-Null
      $JsonPath = $TestFile -replace '\.md$', '.json'
      $json = Get-Content $JsonPath -Raw | ConvertFrom-Json
      $json.protocolCompliance.sessionStart.serenaActivated.complete | Should -Be $true
    }
  }

  Context 'DryRun Mode' {
    BeforeEach {
      $TestFile = Join-Path $TestRoot '2026-01-09-session-998.md'
      Set-Content -Path $TestFile -Value '# Session 998' -Encoding utf8
    }

    It 'Does not create JSON file with -DryRun' {
      & $ScriptPath -Path $TestFile -DryRun | Out-Null
      $JsonPath = $TestFile -replace '\.md$', '.json'
      Test-Path $JsonPath | Should -Be $false
    }

    It 'Returns would-be migrated paths' {
      $result = & $ScriptPath -Path $TestFile -DryRun
      $result | Should -Not -BeNullOrEmpty
    }
  }

  Context 'Force Mode' {
    BeforeEach {
      $TestFile = Join-Path $TestRoot '2026-01-09-session-997.md'
      $JsonFile = Join-Path $TestRoot '2026-01-09-session-997.json'
      Set-Content -Path $TestFile -Value '# Session 997' -Encoding utf8
      Set-Content -Path $JsonFile -Value '{"old": true}' -Encoding utf8
    }

    It 'Skips existing JSON without -Force' {
      $result = & $ScriptPath -Path $TestFile
      $content = Get-Content $JsonFile -Raw
      $content | Should -Match 'old'
    }

    It 'Overwrites existing JSON with -Force' {
      & $ScriptPath -Path $TestFile -Force | Out-Null
      $content = Get-Content $JsonFile -Raw | ConvertFrom-Json
      $content.PSObject.Properties.Name | Should -Contain 'session'
    }
  }

  Context 'Directory Migration' {
    BeforeEach {
      $SubDir = Join-Path $TestRoot 'batch'
      New-Item -ItemType Directory -Path $SubDir -Force | Out-Null

      1..3 | ForEach-Object {
        $file = Join-Path $SubDir "2026-01-0$_-session-$_.md"
        Set-Content -Path $file -Value "# Session $_`n**Branch**: feat/test" -Encoding utf8
      }
    }

    It 'Migrates all session files in directory' {
      $result = & $ScriptPath -Path $SubDir
      $result.Count | Should -Be 3
    }

    It 'Only processes files matching session pattern' {
      # Add non-session file
      Set-Content -Path (Join-Path $SubDir 'README.md') -Value '# Readme' -Encoding utf8
      $result = & $ScriptPath -Path $SubDir -Force
      $result.Count | Should -Be 3
    }
  }

  Context 'Protocol Compliance Structure' {
    BeforeEach {
      $TestFile = Join-Path $TestRoot '2026-01-09-session-996.md'
      Set-Content -Path $TestFile -Value '# Session 996' -Encoding utf8
    }

    It 'Creates sessionStart section' {
      & $ScriptPath -Path $TestFile -Force | Out-Null
      $JsonPath = $TestFile -replace '\.md$', '.json'
      $json = Get-Content $JsonPath -Raw | ConvertFrom-Json
      $json.protocolCompliance.PSObject.Properties.Name | Should -Contain 'sessionStart'
    }

    It 'Creates sessionEnd section' {
      & $ScriptPath -Path $TestFile -Force | Out-Null
      $JsonPath = $TestFile -replace '\.md$', '.json'
      $json = Get-Content $JsonPath -Raw | ConvertFrom-Json
      $json.protocolCompliance.PSObject.Properties.Name | Should -Contain 'sessionEnd'
    }

    It 'Assigns MUST level to required start items' {
      & $ScriptPath -Path $TestFile -Force | Out-Null
      $JsonPath = $TestFile -replace '\.md$', '.json'
      $json = Get-Content $JsonPath -Raw | ConvertFrom-Json
      $json.protocolCompliance.sessionStart.serenaActivated.level | Should -Be 'MUST'
    }

    It 'Assigns SHOULD level to optional start items' {
      & $ScriptPath -Path $TestFile -Force | Out-Null
      $JsonPath = $TestFile -replace '\.md$', '.json'
      $json = Get-Content $JsonPath -Raw | ConvertFrom-Json
      $json.protocolCompliance.sessionStart.gitStatusVerified.level | Should -Be 'SHOULD'
    }
  }
}

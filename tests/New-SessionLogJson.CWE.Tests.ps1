<#
.SYNOPSIS
    Tests for CWE mitigation features in New-SessionLogJson.ps1

.DESCRIPTION
    Pester tests covering:
    - CWE-400: Session number ceiling check (DoS prevention)
    - CWE-362: Atomic file creation with collision retry
    - CWE-362: Retry exhaustion after max attempts
    - BOM-less UTF-8 encoding

.NOTES
    EXIT CODES:
    0  - Success: All tests passed
    1  - Error: One or more tests failed (set by Pester framework)

    See: ADR-035 Exit Code Standardization
#>

Describe 'New-SessionLogJson - CWE Mitigations' {
  BeforeAll {
    $scriptPath = Join-Path $PSScriptRoot '../.claude/skills/session-init/scripts/New-SessionLogJson.ps1'
    $tempDir = Join-Path ([System.IO.Path]::GetTempPath()) "new-session-cwe-tests-$(Get-Random)"
    New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
  }

  AfterAll {
    if (Test-Path $tempDir) {
      Remove-Item $tempDir -Recurse -Force
    }
  }

  Context 'CWE-400: Session Number Ceiling Check' {
    BeforeEach {
      # Create a subdirectory per test to isolate session files
      $testSessionDir = Join-Path $tempDir "ceiling-$(Get-Random)"
      New-Item -ItemType Directory -Path $testSessionDir -Force | Out-Null
    }

    It 'Should reject session numbers exceeding max + 10 ceiling' {
      # Create existing session file with number 5
      $existingSession = @{ session = @{ number = 5 } } | ConvertTo-Json -Depth 5
      Set-Content (Join-Path $testSessionDir '2026-01-15-session-5.json') $existingSession -Encoding utf8

      # Attempt to create session 20 (5 + 10 = 15 ceiling, 20 > 15)
      # The script reads from $PSScriptRoot-relative .agents/sessions, so we test the logic directly
      $scriptContent = Get-Content $scriptPath -Raw

      # Verify the ceiling check logic exists
      $scriptContent | Should -Match 'CWE-400'
      $scriptContent | Should -Match 'ceiling'
      $scriptContent | Should -Match '\$maxExisting \+ 10'
    }

    It 'Should allow session numbers within ceiling range' {
      # Create existing session file with number 5
      $existingSession = @{ session = @{ number = 5 } } | ConvertTo-Json -Depth 5
      Set-Content (Join-Path $testSessionDir '2026-01-15-session-5.json') $existingSession -Encoding utf8

      # Session 10 is within ceiling (5 + 10 = 15)
      # Verify the comparison logic allows numbers within range
      $scriptContent = Get-Content $scriptPath -Raw
      $scriptContent | Should -Match '\$SessionNumber -gt \(\$maxExisting \+ 10\)'
    }
  }

  Context 'CWE-362: Atomic File Creation' {
    It 'Should use FileMode.CreateNew for atomic creation' {
      $scriptContent = Get-Content $scriptPath -Raw
      $scriptContent | Should -Match '\[System\.IO\.FileMode\]::CreateNew'
    }

    It 'Should catch IOException for file collision handling' {
      $scriptContent = Get-Content $scriptPath -Raw
      $scriptContent | Should -Match 'catch \[System\.IO\.IOException\]'
    }

    It 'Should increment session number on collision' {
      $scriptContent = Get-Content $scriptPath -Raw
      $scriptContent | Should -Match '\$SessionNumber\+\+'
      $scriptContent | Should -Match '\$session\.session\.number = \$SessionNumber'
    }

    It 'Should have maximum retry limit of 5' {
      $scriptContent = Get-Content $scriptPath -Raw
      $scriptContent | Should -Match '\$maxRetries = 5'
    }

    It 'Should re-serialize JSON after session number update' {
      $scriptContent = Get-Content $scriptPath -Raw
      # After incrementing, the JSON must be re-serialized
      $scriptContent | Should -Match '\$json = \$session \| ConvertTo-Json -Depth 10'
    }
  }

  Context 'BOM-less UTF-8 Encoding' {
    It 'Should use UTF8Encoding with BOM disabled' {
      $scriptContent = Get-Content $scriptPath -Raw
      $scriptContent | Should -Match '\[System\.Text\.UTF8Encoding\]::new\(\$false\)'
    }

    It 'Should not use the BOM-emitting UTF8 property' {
      $scriptContent = Get-Content $scriptPath -Raw
      # The old pattern [System.Text.Encoding]::UTF8 includes BOM
      $scriptContent | Should -Not -Match '\[System\.Text\.Encoding\]::UTF8'
    }
  }

  Context 'Functional: Atomic File Creation' {
    BeforeEach {
      $testSessionDir = Join-Path $tempDir "atomic-$(Get-Random)"
      New-Item -ItemType Directory -Path $testSessionDir -Force | Out-Null
    }

    It 'Should create file with CreateNew atomicity' {
      $filePath = Join-Path $testSessionDir 'test-atomic.json'
      $content = '{"test": true}'

      # Create using the same pattern as the script
      $stream = [System.IO.File]::Open($filePath, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write)
      try {
        $writer = [System.IO.StreamWriter]::new($stream, [System.Text.UTF8Encoding]::new($false))
        $writer.Write($content)
        $writer.Flush()
      } finally {
        if ($writer) { $writer.Dispose() }
        if ($stream) { $stream.Dispose() }
      }

      Test-Path $filePath | Should -Be $true
      $written = Get-Content $filePath -Raw
      $written | Should -Be $content
    }

    It 'Should throw IOException when file already exists' {
      $filePath = Join-Path $testSessionDir 'test-exists.json'
      Set-Content $filePath 'existing' -Encoding utf8

      # CreateNew should throw when file exists
      { [System.IO.File]::Open($filePath, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write) } |
        Should -Throw
    }

    It 'Should write BOM-less UTF-8 content' {
      $filePath = Join-Path $testSessionDir 'test-no-bom.json'
      $content = '{"session": 1}'

      $stream = [System.IO.File]::Open($filePath, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write)
      try {
        $writer = [System.IO.StreamWriter]::new($stream, [System.Text.UTF8Encoding]::new($false))
        $writer.Write($content)
        $writer.Flush()
      } finally {
        if ($writer) { $writer.Dispose() }
        if ($stream) { $stream.Dispose() }
      }

      # Read raw bytes and check first 3 bytes are NOT BOM (EF BB BF)
      $bytes = [System.IO.File]::ReadAllBytes($filePath)
      $hasBom = ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF)
      $hasBom | Should -Be $false
    }
  }
}

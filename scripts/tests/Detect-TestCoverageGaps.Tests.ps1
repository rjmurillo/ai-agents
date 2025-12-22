Describe "Detect-TestCoverageGaps" {
  BeforeAll {
    $script:scriptPath = Join-Path $PSScriptRoot ".." "Detect-TestCoverageGaps.ps1"
    
    # Ensure we're in a git repo
    if (-not (Test-Path ".git")) {
      git init | Out-Null
    }
  }
  
  Context "When checking for test coverage" {
    It "Should exist" {
      Test-Path $script:scriptPath | Should -Be $true
    }
    
    It "Should have valid PowerShell syntax" {
      { 
        $null = [System.Management.Automation.PSParser]::Tokenize(
          (Get-Content $script:scriptPath -Raw), 
          [ref]$null
        )
      } | Should -Not -Throw
    }
    
    It "Should accept -StagedOnly parameter" {
      $params = (Get-Command $script:scriptPath).Parameters
      $params.ContainsKey('StagedOnly') | Should -Be $true
    }
    
    It "Should accept -Path parameter" {
      $params = (Get-Command $script:scriptPath).Parameters
      $params.ContainsKey('Path') | Should -Be $true
    }
    
    It "Should accept -IgnoreFile parameter" {
      $params = (Get-Command $script:scriptPath).Parameters
      $params.ContainsKey('IgnoreFile') | Should -Be $true
    }
    
    It "Should exit 0 when no gaps found" {
      # Run with -StagedOnly when nothing is staged
      & pwsh -NoProfile -File $script:scriptPath -StagedOnly
      $LASTEXITCODE | Should -Be 0
    }
  }
  
  Context "When detecting missing test files" {
    BeforeAll {
      # Create a temp PowerShell file without tests
      $script:tempDir = Join-Path ([System.IO.Path]::GetTempPath()) "test-coverage-$(Get-Random)"
      New-Item -ItemType Directory -Path $script:tempDir -Force | Out-Null
      
      $script:tempFile = Join-Path $script:tempDir "TestScript.ps1"
      Set-Content -Path $script:tempFile -Value "# Test script`nWrite-Host 'Hello'"
    }
    
    AfterAll {
      # Clean up
      if ($script:tempDir -and (Test-Path $script:tempDir)) {
        Remove-Item $script:tempDir -Recurse -Force -ErrorAction SilentlyContinue
      }
    }
    
    It "Should detect missing test file" {
      $output = & pwsh -NoProfile -File $script:scriptPath -Path $script:tempDir 2>&1 | Out-String
      $output | Should -Match "TestScript\.ps1"
    }
    
    It "Should ignore test files themselves" {
      $testFile = Join-Path $script:tempDir "Something.Tests.ps1"
      Set-Content -Path $testFile -Value "# Test file"
      
      $output = & pwsh -NoProfile -File $script:scriptPath -Path $script:tempDir 2>&1 | Out-String
      $output | Should -Not -Match "Something\.Tests\.ps1.*Missing"
    }
  }
}

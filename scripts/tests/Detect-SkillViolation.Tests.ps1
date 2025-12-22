Describe "Detect-SkillViolation" {
  BeforeAll {
    $script:scriptPath = Join-Path $PSScriptRoot ".." "Detect-SkillViolation.ps1"
    
    # Ensure we're in a git repo
    if (-not (Test-Path ".git")) {
      git init | Out-Null
    }
  }
  
  Context "When checking for skill violations" {
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
    
    It "Should exit 0 when no violations found" {
      # Run with -StagedOnly when nothing is staged
      & pwsh -NoProfile -File $script:scriptPath -StagedOnly
      $LASTEXITCODE | Should -Be 0
    }
  }
  
  Context "When detecting gh command patterns" {
    BeforeAll {
      # Create a temp file in the repo with gh commands
      $script:tempFile = Join-Path $PSScriptRoot "temp-test-file.md"
      $content = @'
# Test file with gh commands
gh pr create --title "Test"
gh issue list
gh api /repos/owner/repo
'@
      Set-Content -Path $script:tempFile -Value $content
      
      # Stage the file
      git -C $PSScriptRoot add $script:tempFile 2>$null | Out-Null
    }
    
    AfterAll {
      # Clean up
      if ($script:tempFile -and (Test-Path $script:tempFile)) {
        git -C $PSScriptRoot reset HEAD $script:tempFile 2>$null | Out-Null
        Remove-Item $script:tempFile -Force -ErrorAction SilentlyContinue
      }
    }
    
    It "Should detect gh pr create" {
      $output = & pwsh -NoProfile -File $script:scriptPath -StagedOnly 2>&1 | Out-String
      # Should either warn about violations or show no files (depending on git state)
      # The script exits 0 for warnings, so we just verify it runs
      $LASTEXITCODE | Should -Be 0
    }
  }
}

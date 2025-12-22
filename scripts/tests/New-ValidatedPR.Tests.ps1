Describe "New-ValidatedPR" {
  BeforeAll {
    $script:scriptPath = Join-Path $PSScriptRoot ".." "New-ValidatedPR.ps1"
  }
  
  Context "When creating a validated PR" {
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
    
    It "Should accept -Title parameter" {
      $params = (Get-Command $script:scriptPath).Parameters
      $params.ContainsKey('Title') | Should -Be $true
    }
    
    It "Should accept -Body parameter" {
      $params = (Get-Command $script:scriptPath).Parameters
      $params.ContainsKey('Body') | Should -Be $true
    }
    
    It "Should accept -BodyFile parameter" {
      $params = (Get-Command $script:scriptPath).Parameters
      $params.ContainsKey('BodyFile') | Should -Be $true
    }
    
    It "Should accept -Force parameter" {
      $params = (Get-Command $script:scriptPath).Parameters
      $params.ContainsKey('Force') | Should -Be $true
    }
    
    It "Should accept -Web parameter" {
      $params = (Get-Command $script:scriptPath).Parameters
      $params.ContainsKey('Web') | Should -Be $true
    }
    
    It "Should accept -Draft parameter" {
      $params = (Get-Command $script:scriptPath).Parameters
      $params.ContainsKey('Draft') | Should -Be $true
    }
    
    It "Should accept -Base parameter" {
      $params = (Get-Command $script:scriptPath).Parameters
      $params.ContainsKey('Base') | Should -Be $true
    }
    
    It "Should accept -Head parameter" {
      $params = (Get-Command $script:scriptPath).Parameters
      $params.ContainsKey('Head') | Should -Be $true
    }
  }
  
  Context "When Force flag is used" {
    It "Should create audit trail" {
      # This test would require mocking gh CLI and git commands
      # For now, just verify the script structure
      $content = Get-Content $script:scriptPath -Raw
      $content | Should -Match "Force MODE.*audit"
      $content | Should -Match "\.agents/audit"
    }
  }
}

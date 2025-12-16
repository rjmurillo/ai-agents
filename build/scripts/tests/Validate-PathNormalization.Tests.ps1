<#
.SYNOPSIS
    Pester tests for Validate-PathNormalization.ps1 script.

.DESCRIPTION
    Comprehensive unit tests for the path normalization validation script.
    Tests cover:
    - Pattern detection (Windows, macOS, Linux absolute paths)
    - File scanning and filtering
    - Violation reporting
    - Exit code behavior
    - Exclusion paths

.NOTES
    Requires Pester 5.x or later.
    Run with: pwsh build/scripts/Invoke-PesterTests.ps1 -TestPath "./build/scripts/tests/Validate-PathNormalization.Tests.ps1"
#>

BeforeAll {
    # Create test temp directory
    $Script:TestTempDir = Join-Path $env:TEMP "Validate-PathNormalization-Tests-$(Get-Random)"
    New-Item -ItemType Directory -Path $Script:TestTempDir -Force | Out-Null

    # Store repository root and script path
    $Script:RepoRoot = Split-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) -Parent
    $Script:ScriptPath = Join-Path $Script:RepoRoot "build" "scripts" "Validate-PathNormalization.ps1"
    
    # Verify script exists
    if (-not (Test-Path $Script:ScriptPath)) {
        throw "Script not found at: $Script:ScriptPath"
    }
}

AfterAll {
    # Cleanup test temp directory
    if (Test-Path $Script:TestTempDir) {
        Remove-Item -Path $Script:TestTempDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Describe "Validate-PathNormalization" {
    
    Context "Pattern Detection" {
        
        It "Should detect Windows absolute path (C:\)" {
            $testFile = Join-Path $Script:TestTempDir "test-windows.md"
            Set-Content -Path $testFile -Value @"
# Test Document

See the file at C:\Users\username\repo\docs\guide.md
"@
            
            $output = pwsh -File $Script:ScriptPath -Path $Script:TestTempDir 2>&1 | Out-String
            $output | Should -Match "Windows Absolute Path"
            $output | Should -Match "violation"
        }
        
        It "Should detect macOS absolute path (/Users/)" {
            $testFile = Join-Path $Script:TestTempDir "test-macos.md"
            Set-Content -Path $testFile -Value @"
# Test Document

Reference: /Users/developer/projects/file.md
"@
            
            $output = pwsh -File $Script:ScriptPath -Path $Script:TestTempDir 2>&1 | Out-String
            $output | Should -Match "macOS User Path"
            $output | Should -Match "violation"
        }
        
        It "Should detect Linux absolute path (/home/)" {
            $testFile = Join-Path $Script:TestTempDir "test-linux.md"
            Set-Content -Path $testFile -Value @"
# Test Document

Config at /home/runner/config.md
"@
            
            $output = pwsh -File $Script:ScriptPath -Path $Script:TestTempDir 2>&1 | Out-String
            $output | Should -Match "Linux Home Path"
            $output | Should -Match "violation"
        }
        
        It "Should NOT detect relative paths" {
            $testFile = Join-Path $Script:TestTempDir "test-relative.md"
            Set-Content -Path $testFile -Value @"
# Test Document

See: docs/guide.md
See: ../architecture/design.md
See: .agents/planning/PRD-feature.md
"@
            
            $output = pwsh -File $Script:ScriptPath -Path $Script:TestTempDir 2>&1 | Out-String
            $output | Should -Match "SUCCESS"
            $output | Should -Not -Match "FAILURE"
        }
        
        It "Should detect multiple violations in one file" {
            $testFile = Join-Path $Script:TestTempDir "test-multiple.md"
            Set-Content -Path $testFile -Value @"
# Test Document

Windows: C:\path\to\file.md
macOS: /Users/dev/file.md
Linux: /home/user/file.md
"@
            
            $output = pwsh -File $Script:ScriptPath -Path $Script:TestTempDir 2>&1 | Out-String
            $output | Should -Match "3 absolute path violations"
        }
    }
    
    Context "File Filtering" {
        
        BeforeEach {
            # Clean test directory before each test
            Get-ChildItem -Path $Script:TestTempDir -Recurse | Remove-Item -Force -Recurse -ErrorAction SilentlyContinue
        }
        
        It "Should only scan .md files by default" {
            $mdFile = Join-Path $Script:TestTempDir "test.md"
            $txtFile = Join-Path $Script:TestTempDir "test.txt"
            
            Set-Content -Path $mdFile -Value "Path: C:\test\file.md"
            Set-Content -Path $txtFile -Value "Path: C:\test\file.txt"
            
            $output = pwsh -File $Script:ScriptPath -Path $Script:TestTempDir 2>&1 | Out-String
            $output | Should -Match "Files to scan: 1"
        }
        
        It "Should scan custom extensions when specified" {
            $txtFile = Join-Path $Script:TestTempDir "test-custom.txt"
            Set-Content -Path $txtFile -Value "Path: C:\test\file.txt"
            
            $output = pwsh -File $Script:ScriptPath -Path $Script:TestTempDir -Extensions @('.txt') 2>&1 | Out-String
            $output | Should -Match "violation"
        }
        
        It "Should exclude specified paths" {
            $excludeDir = Join-Path $Script:TestTempDir "node_modules"
            New-Item -ItemType Directory -Path $excludeDir -Force | Out-Null
            $excludeFile = Join-Path $excludeDir "test.md"
            $normalFile = Join-Path $Script:TestTempDir "normal.md"
            Set-Content -Path $excludeFile -Value "Path: C:\excluded\file.md"
            Set-Content -Path $normalFile -Value "Clean file"
            
            $output = pwsh -File $Script:ScriptPath -Path $Script:TestTempDir 2>&1 | Out-String
            $output | Should -Match "SUCCESS"
        }
    }
    
    Context "Exit Code Behavior" {
        
        BeforeEach {
            # Clean test directory before each test
            Get-ChildItem -Path $Script:TestTempDir -Recurse | Remove-Item -Force -Recurse -ErrorAction SilentlyContinue
        }
        
        It "Should exit 0 when no violations found" {
            $testFile = Join-Path $Script:TestTempDir "test-clean.md"
            Set-Content -Path $testFile -Value "# Clean document`nRelative: docs/file.md"
            
            pwsh -File $Script:ScriptPath -Path $Script:TestTempDir
            $LASTEXITCODE | Should -Be 0
        }
        
        It "Should exit 0 when violations found without -FailOnViolation" {
            $testFile = Join-Path $Script:TestTempDir "test-violation.md"
            Set-Content -Path $testFile -Value "Path: C:\violation\file.md"
            
            pwsh -File $Script:ScriptPath -Path $Script:TestTempDir
            $LASTEXITCODE | Should -Be 0
        }
        
        It "Should exit 1 when violations found with -FailOnViolation" {
            $testFile = Join-Path $Script:TestTempDir "test-fail.md"
            Set-Content -Path $testFile -Value "Path: C:\fail\file.md"
            
            pwsh -File $Script:ScriptPath -Path $Script:TestTempDir -FailOnViolation 2>&1 | Out-Null
            $LASTEXITCODE | Should -Be 1
        }
    }
    
    Context "Reporting" {
        
        BeforeEach {
            # Clean test directory before each test
            Get-ChildItem -Path $Script:TestTempDir -Recurse | Remove-Item -Force -Recurse -ErrorAction SilentlyContinue
        }
        
        It "Should report file count" {
            $testFile = Join-Path $Script:TestTempDir "test-count.md"
            Set-Content -Path $testFile -Value "# Test"
            
            $output = pwsh -File $Script:ScriptPath -Path $Script:TestTempDir 2>&1 | Out-String
            $output | Should -Match "Files to scan: 1"
        }
        
        It "Should report line numbers for violations" {
            $testFile = Join-Path $Script:TestTempDir "test-lines.md"
            Set-Content -Path $testFile -Value @"
Line 1: Normal text
Line 2: C:\violation\here.md
Line 3: Normal text
"@
            
            $output = pwsh -File $Script:ScriptPath -Path $Script:TestTempDir 2>&1 | Out-String
            $output | Should -Match "Line 2"
        }
        
        It "Should provide remediation steps on failure" {
            $testFile = Join-Path $Script:TestTempDir "test-remediation.md"
            Set-Content -Path $testFile -Value "Path: C:\test\file.md"
            
            $output = pwsh -File $Script:ScriptPath -Path $Script:TestTempDir 2>&1 | Out-String
            $output | Should -Match "Remediation Steps"
            $output | Should -Match "relative paths"
        }
    }
    
    Context "Edge Cases" {
        
        BeforeEach {
            # Clean test directory before each test
            Get-ChildItem -Path $Script:TestTempDir -Recurse | Remove-Item -Force -Recurse -ErrorAction SilentlyContinue
        }
        
        It "Should handle empty files" {
            $testFile = Join-Path $Script:TestTempDir "test-empty.md"
            Set-Content -Path $testFile -Value ""
            
            $output = pwsh -File $Script:ScriptPath -Path $Script:TestTempDir 2>&1 | Out-String
            $LASTEXITCODE | Should -Be 0
        }
        
        It "Should handle files with only whitespace" {
            $testFile = Join-Path $Script:TestTempDir "test-whitespace.md"
            Set-Content -Path $testFile -Value "   `n   `n   "
            
            $output = pwsh -File $Script:ScriptPath -Path $Script:TestTempDir 2>&1 | Out-String
            $LASTEXITCODE | Should -Be 0
        }
    }
}

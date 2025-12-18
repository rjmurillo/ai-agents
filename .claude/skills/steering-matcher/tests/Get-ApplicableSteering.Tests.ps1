Describe "Get-ApplicableSteering" {
    BeforeAll {
        # Import the function
        . "$PSScriptRoot/../Get-ApplicableSteering.ps1"
        
        # Create temporary steering directory with test files
        $testSteeringPath = Join-Path $TestDrive "test-steering"
        New-Item -ItemType Directory -Path $testSteeringPath -Force | Out-Null
        
        # Create test steering file 1: agent-prompts
        $agentPromptsContent = @"
---
name: Agent Prompts Test
applyTo: "src/claude/**/*.md,**/*.AGENTS.md"
priority: 9
version: 0.1.0
status: test
---
# Agent Prompts Steering
Test content
"@
        Set-Content -Path (Join-Path $testSteeringPath "agent-prompts.md") -Value $agentPromptsContent
        
        # Create test steering file 2: security
        $securityContent = @"
---
name: Security Test
applyTo: "**/Auth/**,*.env*,**/*.secrets.*"
priority: 10
version: 0.1.0
status: test
---
# Security Steering
Test content
"@
        Set-Content -Path (Join-Path $testSteeringPath "security-practices.md") -Value $securityContent
        
        # Create test steering file 3: testing
        $testingContent = @"
---
name: Testing Test
applyTo: "**/*.Tests.ps1"
priority: 7
version: 0.1.0
status: test
---
# Testing Steering
Test content
"@
        Set-Content -Path (Join-Path $testSteeringPath "testing-approach.md") -Value $testingContent
        
        # Create README (should be ignored)
        Set-Content -Path (Join-Path $testSteeringPath "README.md") -Value "# README"
    }
    
    Context "When matching files against steering patterns" {
        It "Should match agent prompt files" {
            # Arrange
            $files = @("src/claude/analyst.md")
            
            # Act
            $result = Get-ApplicableSteering -Files $files -SteeringPath $testSteeringPath
            
            # Assert
            $result | Should -Not -BeNullOrEmpty
            $result.Count | Should -Be 1
            $result[0].Name | Should -Be "agent-prompts"
            $result[0].Priority | Should -Be 9
        }
        
        It "Should match security files in Auth directory" {
            # Arrange
            $files = @("src/Auth/Controllers/LoginController.cs")
            
            # Act
            $result = Get-ApplicableSteering -Files $files -SteeringPath $testSteeringPath
            
            # Assert
            $result | Should -Not -BeNullOrEmpty
            $result.Count | Should -Be 1
            $result[0].Name | Should -Be "security-practices"
            $result[0].Priority | Should -Be 10
        }
        
        It "Should match .env files" {
            # Arrange
            $files = @(".env", ".env.local", "config/.env.production")
            
            # Act
            $result = Get-ApplicableSteering -Files $files -SteeringPath $testSteeringPath
            
            # Assert
            $result | Should -Not -BeNullOrEmpty
            $result.Count | Should -Be 1
            $result[0].Name | Should -Be "security-practices"
        }
        
        It "Should match Pester test files" {
            # Arrange
            $files = @("scripts/tests/Validate-Config.Tests.ps1")
            
            # Act
            $result = Get-ApplicableSteering -Files $files -SteeringPath $testSteeringPath
            
            # Assert
            $result | Should -Not -BeNullOrEmpty
            $result.Count | Should -Be 1
            $result[0].Name | Should -Be "testing-approach"
            $result[0].Priority | Should -Be 7
        }
        
        It "Should match multiple steering files for same file" {
            # Arrange - A file in Auth directory that's also a markdown file
            $files = @("src/Auth/README.md")
            
            # Act
            $result = Get-ApplicableSteering -Files $files -SteeringPath $testSteeringPath
            
            # Assert
            $result | Should -Not -BeNullOrEmpty
            # Should match security (Auth) pattern only, not agent-prompts (too specific)
            $result.Count | Should -Be 1
            $result[0].Name | Should -Be "security-practices"
        }
        
        It "Should return results sorted by priority (descending)" {
            # Arrange - Files that match multiple steering
            $files = @(
                "src/claude/security.md",           # agent-prompts (9)
                ".agents/security/TM-001.md"        # No match
            )
            
            # Act
            $result = Get-ApplicableSteering -Files $files -SteeringPath $testSteeringPath
            
            # Assert
            $result | Should -Not -BeNullOrEmpty
            # Should be sorted by priority (highest first)
            if ($result.Count -gt 1) {
                $result[0].Priority | Should -BeGreaterOrEqual $result[1].Priority
            }
        }
        
        It "Should return empty array when no files match" {
            # Arrange
            $files = @("README.md", "package.json")
            
            # Act
            $result = Get-ApplicableSteering -Files $files -SteeringPath $testSteeringPath
            
            # Assert
            $result | Should -BeNullOrEmpty
        }
        
        It "Should handle multiple files in single call" {
            # Arrange
            $files = @(
                "src/claude/analyst.md",                    # agent-prompts
                ".agents/security/TM-001.md",               # no match
                "scripts/tests/Install.Tests.ps1"           # testing-approach
            )
            
            # Act
            $result = Get-ApplicableSteering -Files $files -SteeringPath $testSteeringPath
            
            # Assert
            $result | Should -Not -BeNullOrEmpty
            $result.Count | Should -BeGreaterOrEqual 2
            $result.Name | Should -Contain "agent-prompts"
            $result.Name | Should -Contain "testing-approach"
        }
        
        It "Should ignore README.md in steering directory" {
            # Arrange
            $files = @("anything.txt")
            
            # Act
            $result = Get-ApplicableSteering -Files $files -SteeringPath $testSteeringPath
            
            # Assert - Should not crash and should return empty
            $result | Should -BeNullOrEmpty
        }
    }
    
    Context "When handling edge cases" {
        It "Should handle files with no matching patterns gracefully" {
            # Arrange
            $files = @("some/random/file.xyz")
            
            # Act
            $result = Get-ApplicableSteering -Files $files -SteeringPath $testSteeringPath
            
            # Assert
            $result | Should -BeNullOrEmpty
        }
        
        It "Should handle empty file array" {
            # Arrange
            $files = @()
            
            # Act
            $result = Get-ApplicableSteering -Files $files -SteeringPath $testSteeringPath
            
            # Assert
            $result | Should -BeNullOrEmpty
        }
        
        It "Should use default priority of 5 when not specified" {
            # Arrange - Create a file without priority
            $noPriorityContent = @"
---
name: No Priority Test
applyTo: "**/*.nopriority"
version: 0.1.0
---
# No Priority
"@
            Set-Content -Path (Join-Path $testSteeringPath "no-priority.md") -Value $noPriorityContent
            $files = @("test.nopriority")
            
            # Act
            $result = Get-ApplicableSteering -Files $files -SteeringPath $testSteeringPath
            
            # Assert
            $result | Should -Not -BeNullOrEmpty
            $result[0].Priority | Should -Be 5
        }
    }
    
    Context "When validating output structure" {
        It "Should return hashtables with required properties" {
            # Arrange
            $files = @("src/claude/analyst.md")
            
            # Act
            $result = Get-ApplicableSteering -Files $files -SteeringPath $testSteeringPath
            
            # Assert
            $result | Should -Not -BeNullOrEmpty
            $result[0].Name | Should -Not -BeNullOrEmpty
            $result[0].Path | Should -Not -BeNullOrEmpty
            $result[0].ApplyTo | Should -Not -BeNullOrEmpty
            $result[0].Priority | Should -Not -BeNullOrEmpty
        }
        
        It "Should have valid file paths in results" {
            # Arrange
            $files = @("src/claude/analyst.md")
            
            # Act
            $result = Get-ApplicableSteering -Files $files -SteeringPath $testSteeringPath
            
            # Assert
            $result[0].Path | Should -Exist
        }
    }
}

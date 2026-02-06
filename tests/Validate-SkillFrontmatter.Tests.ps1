#Requires -Modules Pester

<#
.SYNOPSIS
    Pester tests for Validate-SkillFrontmatter.ps1

.DESCRIPTION
    Tests the skill frontmatter validation functions that implement
    frontmatter requirements from .agents/analysis/claude-code-skill-frontmatter-2026.md:
    - YAML syntax validation
    - Required fields: name, description
    - Name format: lowercase alphanumeric + hyphens, max 64 chars
    - Description: non-empty, max 1024 chars, no XML tags
    - Model: valid identifiers (aliases or dated snapshots)
    - Allowed-tools: valid tool names

.NOTES
    Related: Issue #4, ADR-040 (Skill Frontmatter Standardization)

    EXIT CODES:
    0  - Success: All tests passed
    1  - Error: One or more tests failed (set by Pester framework)

    See: ADR-035 Exit Code Standardization
#>

BeforeAll {
    $script:ScriptPath = Join-Path $PSScriptRoot ".." "scripts" "Validate-SkillFrontmatter.ps1"
    $script:TestSkillsPath = Join-Path $TestDrive ".claude" "skills"

    # Create test directory structure
    New-Item -ItemType Directory -Path $TestSkillsPath -Force | Out-Null

    # Helper function to create a test skill directory with SKILL.md
    function New-TestSkill {
        [CmdletBinding(SupportsShouldProcess)]
        param(
            [string]$SkillName,
            [string]$Frontmatter,
            [string]$Content = "# Test Skill`n`nThis is a test skill."
        )

        if ($PSCmdlet.ShouldProcess("$SkillName", "Create test skill")) {
            $skillDir = Join-Path $script:TestSkillsPath $SkillName
            New-Item -ItemType Directory -Path $skillDir -Force | Out-Null
            
            $skillFile = Join-Path $skillDir "SKILL.md"
            $fullContent = $Frontmatter + "`n" + $Content
            Set-Content -Path $skillFile -Value $fullContent -NoNewline
            
            return $skillFile
        }
    }

    # Helper function to run the script and capture all output
    function Invoke-ValidationScript {
        param(
            [string]$Path,
            [switch]$CI,
            [switch]$StagedOnly,
            [string[]]$ChangedFiles
        )

        $params = @()
        if ($Path) { $params += "-Path", "`"$Path`"" }
        if ($CI) { $params += "-CI" }
        if ($StagedOnly) { $params += "-StagedOnly" }
        if ($ChangedFiles) { 
            $filesArg = ($ChangedFiles | ForEach-Object { "`"$_`"" }) -join ","
            $params += "-ChangedFiles", "@($filesArg)" 
        }

        # Run in a new PowerShell process to get proper exit code
        $paramString = $params -join ' '
        $command = "& '$script:ScriptPath' $paramString; exit `$LASTEXITCODE"
        
        $output = pwsh -NoProfile -Command $command 2>&1
        $exitCode = $LASTEXITCODE

        return @{
            Output = ($output | Out-String)
            ExitCode = $exitCode
        }
    }
}

Describe "Validate-SkillFrontmatter.ps1" {

    AfterEach {
        # Clean up test skill directories after each test
        Get-ChildItem -Path $TestSkillsPath -Directory -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
    }

    Context "YAML Syntax Validation" {

        It "Accepts valid frontmatter with proper delimiters" {
            # Arrange
            $frontmatter = @"
---
name: test-skill
description: A test skill for validation
---
"@
            $skillFile = New-TestSkill -SkillName "valid-skill" -Frontmatter $frontmatter

            # Act
            $result = Invoke-ValidationScript -Path (Split-Path $skillFile) -CI

            # Assert
            $result.ExitCode | Should -Be 0
            $result.Output | Should -Match "PASS"
        }

        It "Rejects frontmatter without starting delimiter" {
            # Arrange
            $frontmatter = @"
name: test-skill
description: A test skill
---
"@
            $skillFile = New-TestSkill -SkillName "no-start-delimiter" -Frontmatter $frontmatter

            # Act
            $result = Invoke-ValidationScript -Path (Split-Path $skillFile) -CI

            # Assert
            $result.ExitCode | Should -Be 1
            $result.Output | Should -Match "must start with '---'"
        }

        It "Rejects frontmatter without ending delimiter" {
            # Arrange
            $frontmatter = @"
---
name: test-skill
description: A test skill
"@
            $skillFile = New-TestSkill -SkillName "no-end-delimiter" -Frontmatter $frontmatter

            # Act
            $result = Invoke-ValidationScript -Path (Split-Path $skillFile) -CI

            # Assert
            $result.ExitCode | Should -Be 1
            $result.Output | Should -Match "must end with '---'"
        }

        It "Rejects frontmatter with tab characters" {
            # Arrange
            $frontmatter = "---`nname:`ttest-skill`ndescription: A test skill`n---"
            $skillFile = New-TestSkill -SkillName "tabs-skill" -Frontmatter $frontmatter

            # Act
            $result = Invoke-ValidationScript -Path (Split-Path $skillFile) -CI

            # Assert
            $result.ExitCode | Should -Be 1
            $result.Output | Should -Match "spaces for indentation"
        }
    }

    Context "Required Fields Validation" {

        It "Rejects frontmatter missing 'name' field" {
            # Arrange
            $frontmatter = @"
---
description: A test skill without name
---
"@
            $skillFile = New-TestSkill -SkillName "no-name" -Frontmatter $frontmatter

            # Act
            $result = Invoke-ValidationScript -Path (Split-Path $skillFile) -CI

            # Assert
            $result.ExitCode | Should -Be 1
            $result.Output | Should -Match "Missing required field: 'name'"
        }

        It "Rejects frontmatter missing 'description' field" {
            # Arrange
            $frontmatter = @"
---
name: test-skill
---
"@
            $skillFile = New-TestSkill -SkillName "no-description" -Frontmatter $frontmatter

            # Act
            $result = Invoke-ValidationScript -Path (Split-Path $skillFile) -CI

            # Assert
            $result.ExitCode | Should -Be 1
            $result.Output | Should -Match "Missing required field: 'description'"
        }

        It "Accepts frontmatter with only required fields" {
            # Arrange
            $frontmatter = @"
---
name: minimal-skill
description: Minimal valid skill
---
"@
            $skillFile = New-TestSkill -SkillName "minimal-skill" -Frontmatter $frontmatter

            # Act
            $result = Invoke-ValidationScript -Path (Split-Path $skillFile) -CI

            # Assert
            $result.ExitCode | Should -Be 0
            $result.Output | Should -Match "PASS"
        }
    }

    Context "Name Format Validation" {

        It "Accepts valid lowercase name with hyphens" {
            # Arrange
            $frontmatter = @"
---
name: my-test-skill-123
description: Valid name format
---
"@
            $skillFile = New-TestSkill -SkillName "valid-name" -Frontmatter $frontmatter

            # Act
            $result = Invoke-ValidationScript -Path (Split-Path $skillFile) -CI

            # Assert
            $result.ExitCode | Should -Be 0
        }

        It "Rejects name with uppercase letters" {
            # Arrange
            $frontmatter = @"
---
name: My-Test-Skill
description: Name with uppercase
---
"@
            $skillFile = New-TestSkill -SkillName "uppercase-name" -Frontmatter $frontmatter

            # Act
            $result = Invoke-ValidationScript -Path (Split-Path $skillFile) -CI

            # Assert
            $result.ExitCode | Should -Be 1
            $result.Output | Should -Match "Invalid name format"
            $result.Output | Should -Match "uppercase"
        }

        It "Rejects name with special characters" {
            # Arrange
            $frontmatter = @"
---
name: test_skill!
description: Name with special chars
---
"@
            $skillFile = New-TestSkill -SkillName "special-chars" -Frontmatter $frontmatter

            # Act
            $result = Invoke-ValidationScript -Path (Split-Path $skillFile) -CI

            # Assert
            $result.ExitCode | Should -Be 1
            $result.Output | Should -Match "Invalid name format"
            $result.Output | Should -Match "invalid characters"
        }

        It "Rejects name exceeding 64 characters" {
            # Arrange
            $longName = "a" * 65  # 65 characters
            $frontmatter = @"
---
name: $longName
description: Name too long
---
"@
            $skillFile = New-TestSkill -SkillName "long-name" -Frontmatter $frontmatter

            # Act
            $result = Invoke-ValidationScript -Path (Split-Path $skillFile) -CI

            # Assert
            $result.ExitCode | Should -Be 1
            $result.Output | Should -Match "exceeds 64 characters"
        }

        It "Accepts name at exactly 64 characters" {
            # Arrange
            $maxName = "a" * 64  # Exactly 64 characters
            $frontmatter = @"
---
name: $maxName
description: Name at max length
---
"@
            $skillFile = New-TestSkill -SkillName "max-name" -Frontmatter $frontmatter

            # Act
            $result = Invoke-ValidationScript -Path (Split-Path $skillFile) -CI

            # Assert
            $result.ExitCode | Should -Be 0
        }

        It "Accepts name with only numbers" {
            # Arrange
            $frontmatter = @"
---
name: 12345
description: Numeric name
---
"@
            $skillFile = New-TestSkill -SkillName "numeric-name" -Frontmatter $frontmatter

            # Act
            $result = Invoke-ValidationScript -Path (Split-Path $skillFile) -CI

            # Assert
            $result.ExitCode | Should -Be 0
        }

        It "Accepts name with hyphens at start and end" {
            # Arrange
            $frontmatter = @"
---
name: -test-skill-
description: Hyphens at boundaries
---
"@
            $skillFile = New-TestSkill -SkillName "hyphen-boundaries" -Frontmatter $frontmatter

            # Act
            $result = Invoke-ValidationScript -Path (Split-Path $skillFile) -CI

            # Assert
            $result.ExitCode | Should -Be 0
        }
    }

    Context "Description Validation" {

        It "Accepts description under 1024 characters" {
            # Arrange
            $description = "A" * 1000  # 1000 characters
            $frontmatter = @"
---
name: test-skill
description: $description
---
"@
            $skillFile = New-TestSkill -SkillName "valid-desc" -Frontmatter $frontmatter

            # Act
            $result = Invoke-ValidationScript -Path (Split-Path $skillFile) -CI

            # Assert
            $result.ExitCode | Should -Be 0
        }

        It "Accepts description at exactly 1024 characters" {
            # Arrange
            $description = "A" * 1024  # Exactly 1024 characters
            $frontmatter = @"
---
name: test-skill
description: $description
---
"@
            $skillFile = New-TestSkill -SkillName "max-desc" -Frontmatter $frontmatter

            # Act
            $result = Invoke-ValidationScript -Path (Split-Path $skillFile) -CI

            # Assert
            $result.ExitCode | Should -Be 0
        }

        It "Rejects description exceeding 1024 characters" {
            # Arrange
            $description = "A" * 1025  # 1025 characters
            $frontmatter = @"
---
name: test-skill
description: $description
---
"@
            $skillFile = New-TestSkill -SkillName "long-desc" -Frontmatter $frontmatter

            # Act
            $result = Invoke-ValidationScript -Path (Split-Path $skillFile) -CI

            # Assert
            $result.ExitCode | Should -Be 1
            $result.Output | Should -Match "exceeds 1024 characters"
            $result.Output | Should -Match "found 1025"
        }

        It "Rejects description with XML tags" {
            # Arrange
            $frontmatter = @"
---
name: test-skill
description: This has <b>XML tags</b> in it
---
"@
            $skillFile = New-TestSkill -SkillName "xml-desc" -Frontmatter $frontmatter

            # Act
            $result = Invoke-ValidationScript -Path (Split-Path $skillFile) -CI

            # Assert
            $result.ExitCode | Should -Be 1
            $result.Output | Should -Match "contains XML tags"
        }

        It "Accepts multiline description with YAML > syntax" {
            # Arrange
            $frontmatter = @"
---
name: test-skill
description: >
  This is a multiline description
  that spans multiple lines
  using YAML syntax
---
"@
            $skillFile = New-TestSkill -SkillName "multiline-desc" -Frontmatter $frontmatter

            # Act
            $result = Invoke-ValidationScript -Path (Split-Path $skillFile) -CI

            # Assert
            $result.ExitCode | Should -Be 0
        }

        It "Rejects empty description" {
            # Arrange
            $frontmatter = @"
---
name: test-skill
description: 
---
"@
            $skillFile = New-TestSkill -SkillName "empty-desc" -Frontmatter $frontmatter

            # Act
            $result = Invoke-ValidationScript -Path (Split-Path $skillFile) -CI

            # Assert
            $result.ExitCode | Should -Be 1
            $result.Output | Should -Match "Missing required field: 'description'"
        }
    }

    Context "Model Identifier Validation" {

        It "Accepts valid model alias: claude-sonnet-4-5" {
            # Arrange
            $frontmatter = @"
---
name: test-skill
description: Test skill with model
model: claude-sonnet-4-5
---
"@
            $skillFile = New-TestSkill -SkillName "model-alias" -Frontmatter $frontmatter

            # Act
            $result = Invoke-ValidationScript -Path (Split-Path $skillFile) -CI

            # Assert
            $result.ExitCode | Should -Be 0
        }

        It "Accepts valid model alias: claude-opus-4-5" {
            # Arrange
            $frontmatter = @"
---
name: test-skill
description: Test skill
model: claude-opus-4-5
---
"@
            $skillFile = New-TestSkill -SkillName "opus-model" -Frontmatter $frontmatter

            # Act
            $result = Invoke-ValidationScript -Path (Split-Path $skillFile) -CI

            # Assert
            $result.ExitCode | Should -Be 0
        }

        It "Accepts CLI shortcut: sonnet" {
            # Arrange
            $frontmatter = @"
---
name: test-skill
description: Test skill
model: sonnet
---
"@
            $skillFile = New-TestSkill -SkillName "shortcut-model" -Frontmatter $frontmatter

            # Act
            $result = Invoke-ValidationScript -Path (Split-Path $skillFile) -CI

            # Assert
            $result.ExitCode | Should -Be 0
        }

        It "Accepts dated snapshot: claude-sonnet-4-5-20250929" {
            # Arrange
            $frontmatter = @"
---
name: test-skill
description: Test skill
model: claude-sonnet-4-5-20250929
---
"@
            $skillFile = New-TestSkill -SkillName "dated-model" -Frontmatter $frontmatter

            # Act
            $result = Invoke-ValidationScript -Path (Split-Path $skillFile) -CI

            # Assert
            $result.ExitCode | Should -Be 0
        }

        It "Rejects invalid model identifier" {
            # Arrange
            $frontmatter = @"
---
name: test-skill
description: Test skill
model: invalid-model-name
---
"@
            $skillFile = New-TestSkill -SkillName "invalid-model" -Frontmatter $frontmatter

            # Act
            $result = Invoke-ValidationScript -Path (Split-Path $skillFile) -CI

            # Assert
            $result.ExitCode | Should -Be 1
            $result.Output | Should -Match "Invalid model identifier"
        }

        It "Accepts skill without model field (optional)" {
            # Arrange
            $frontmatter = @"
---
name: test-skill
description: Test skill without model
---
"@
            $skillFile = New-TestSkill -SkillName "no-model" -Frontmatter $frontmatter

            # Act
            $result = Invoke-ValidationScript -Path (Split-Path $skillFile) -CI

            # Assert
            $result.ExitCode | Should -Be 0
        }
    }

    Context "Allowed-Tools Validation" {

        It "Accepts valid tool names" {
            # Arrange
            $frontmatter = @"
---
name: test-skill
description: Test skill
allowed-tools:
  - bash
  - view
  - edit
---
"@
            $skillFile = New-TestSkill -SkillName "valid-tools" -Frontmatter $frontmatter

            # Act
            $result = Invoke-ValidationScript -Path (Split-Path $skillFile) -CI

            # Assert
            $result.ExitCode | Should -Be 0
        }

        It "Accepts wildcard in allowed-tools" {
            # Arrange
            $frontmatter = @"
---
name: test-skill
description: Test skill
allowed-tools:
  - bash
  - mcp*
---
"@
            $skillFile = New-TestSkill -SkillName "wildcard-tools" -Frontmatter $frontmatter

            # Act
            $result = Invoke-ValidationScript -Path (Split-Path $skillFile) -CI

            # Assert
            $result.ExitCode | Should -Be 0
        }

        It "Rejects unknown tool names" {
            # Arrange
            $frontmatter = @"
---
name: test-skill
description: Test skill
allowed-tools:
  - bash
  - invalid-tool-name
---
"@
            $skillFile = New-TestSkill -SkillName "invalid-tools" -Frontmatter $frontmatter

            # Act
            $result = Invoke-ValidationScript -Path (Split-Path $skillFile) -CI

            # Assert
            $result.ExitCode | Should -Be 1
            $result.Output | Should -Match "Unknown tools"
            $result.Output | Should -Match "invalid-tool-name"
        }

        It "Accepts skill without allowed-tools field (optional)" {
            # Arrange
            $frontmatter = @"
---
name: test-skill
description: Test skill without tools
---
"@
            $skillFile = New-TestSkill -SkillName "no-tools" -Frontmatter $frontmatter

            # Act
            $result = Invoke-ValidationScript -Path (Split-Path $skillFile) -CI

            # Assert
            $result.ExitCode | Should -Be 0
        }
    }

    Context "CI Mode vs Local Mode" {

        It "Exits with code 1 in CI mode on validation failure" {
            # Arrange
            $frontmatter = @"
---
name: Invalid-Name
description: Test
---
"@
            $skillFile = New-TestSkill -SkillName "fail-ci" -Frontmatter $frontmatter

            # Act
            $result = Invoke-ValidationScript -Path (Split-Path $skillFile) -CI

            # Assert
            $result.ExitCode | Should -Be 1
        }

        It "Exits with code 0 in local mode even on validation failure" {
            # Arrange
            $frontmatter = @"
---
name: Invalid-Name
description: Test
---
"@
            $skillFile = New-TestSkill -SkillName "fail-local" -Frontmatter $frontmatter

            # Act - NOT in CI mode
            $result = Invoke-ValidationScript -Path (Split-Path $skillFile)

            # Assert
            $result.ExitCode | Should -Be 0
            $result.Output | Should -Match "not running in CI mode"
        }

        It "Exits with code 0 in CI mode on validation success" {
            # Arrange
            $frontmatter = @"
---
name: valid-name
description: Test skill
---
"@
            $skillFile = New-TestSkill -SkillName "pass-ci" -Frontmatter $frontmatter

            # Act
            $result = Invoke-ValidationScript -Path (Split-Path $skillFile) -CI

            # Assert
            $result.ExitCode | Should -Be 0
        }
    }

    Context "Multiple Violations" {

        It "Reports all violations in a single file" {
            # Arrange
            $frontmatter = @"
---
name: Invalid-Name-With-CAPS
description: <b>Has XML</b> $("A" * 1025)
model: invalid-model
---
"@
            $skillFile = New-TestSkill -SkillName "multiple-errors" -Frontmatter $frontmatter

            # Act
            $result = Invoke-ValidationScript -Path (Split-Path $skillFile) -CI

            # Assert
            $result.ExitCode | Should -Be 1
            $result.Output | Should -Match "Invalid name format"
            $result.Output | Should -Match "exceeds 1024 characters"
            $result.Output | Should -Match "contains XML tags"
            $result.Output | Should -Match "Invalid model identifier"
        }
    }

    Context "Multiple Files" {

        It "Validates multiple SKILL.md files" {
            # Arrange
            $frontmatter1 = @"
---
name: skill-one
description: First test skill
---
"@
            $frontmatter2 = @"
---
name: skill-two
description: Second test skill
---
"@
            New-TestSkill -SkillName "skill-one" -Frontmatter $frontmatter1
            New-TestSkill -SkillName "skill-two" -Frontmatter $frontmatter2

            # Act
            $result = Invoke-ValidationScript -Path $TestSkillsPath -CI

            # Assert
            $result.ExitCode | Should -Be 0
            $result.Output | Should -Match "Found 2 SKILL.md file\(s\)"
            $result.Output | Should -Match "Passed: 2"
        }

        It "Reports summary with mixed results" {
            # Arrange
            $validFrontmatter = @"
---
name: valid-skill
description: Valid test skill
---
"@
            $invalidFrontmatter = @"
---
name: Invalid-Skill
description: Invalid test skill
---
"@
            New-TestSkill -SkillName "valid-skill" -Frontmatter $validFrontmatter
            New-TestSkill -SkillName "invalid-skill" -Frontmatter $invalidFrontmatter

            # Act
            $result = Invoke-ValidationScript -Path $TestSkillsPath -CI

            # Assert
            $result.ExitCode | Should -Be 1
            $result.Output | Should -Match "Passed: 1"
            $result.Output | Should -Match "Failed: 1"
        }
    }

    Context "Edge Cases" {

        It "Handles empty file" {
            # Arrange
            $skillDir = Join-Path $TestSkillsPath "empty-skill"
            New-Item -ItemType Directory -Path $skillDir -Force | Out-Null
            $skillFile = Join-Path $skillDir "SKILL.md"
            Set-Content -Path $skillFile -Value "" -NoNewline

            # Act
            $result = Invoke-ValidationScript -Path $skillDir -CI

            # Assert
            $result.ExitCode | Should -Be 1
            $result.Output | Should -Match "empty or unreadable"
        }

        It "Handles file with only frontmatter (no content)" {
            # Arrange
            $frontmatter = @"
---
name: no-content
description: Skill with no content after frontmatter
---
"@
            $skillFile = New-TestSkill -SkillName "no-content" -Frontmatter $frontmatter -Content ""

            # Act
            $result = Invoke-ValidationScript -Path (Split-Path $skillFile) -CI

            # Assert
            $result.ExitCode | Should -Be 0
        }

        It "Skips validation when no SKILL.md files found" {
            # Arrange - empty directory

            # Act
            $result = Invoke-ValidationScript -Path $TestSkillsPath -CI

            # Assert
            $result.ExitCode | Should -Be 0
            $result.Output | Should -Match "No SKILL.md file"
        }
    }
}

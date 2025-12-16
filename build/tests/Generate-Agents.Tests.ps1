<#
.SYNOPSIS
    Pester tests for Generate-Agents.ps1 script.

.DESCRIPTION
    Comprehensive unit tests for the agent generation script.
    Tests cover frontmatter parsing, transformation, handoff syntax conversion,
    and path validation security.

.NOTES
    Requires Pester 5.x or later.
    Run with: pwsh build/scripts/Invoke-PesterTests.ps1 -TestPath "./build/tests"
#>

BeforeAll {
    # Import functions from the script by dot-sourcing
    $ScriptPath = Join-Path $PSScriptRoot "..\Generate-Agents.ps1"

    # Create a module scope to hold the functions
    $Script:TestTempDir = Join-Path $env:TEMP "Generate-Agents-Tests-$(Get-Random)"
    New-Item -ItemType Directory -Path $Script:TestTempDir -Force | Out-Null

    # Define test functions (copies from script for unit testing)
    function Test-PathWithinRoot {
        param([string]$Path, [string]$Root)
        $resolvedPath = [System.IO.Path]::GetFullPath($Path)
        $resolvedRoot = [System.IO.Path]::GetFullPath($Root).TrimEnd('\', '/')
        # Append directory separator to ensure only true descendants match
        $resolvedRoot += [System.IO.Path]::DirectorySeparatorChar

        # Path equals root (without trailing separator) is valid
        $pathWithoutTrailing = $resolvedPath.TrimEnd('\', '/')
        $rootWithoutTrailing = $resolvedRoot.TrimEnd('\', '/')
        if ($pathWithoutTrailing -eq $rootWithoutTrailing) {
            return $true
        }

        return $resolvedPath.StartsWith($resolvedRoot, [StringComparison]::OrdinalIgnoreCase)
    }

    function Read-YamlFrontmatter {
        param([string]$Content)
        if ($Content -match '^---\r?\n([\s\S]*?)\r?\n---\r?\n([\s\S]*)$') {
            return [PSCustomObject]@{
                FrontmatterRaw = $Matches[1]
                Body           = $Matches[2]
            }
        }
        return $null
    }

    function ConvertFrom-SimpleFrontmatter {
        param([string]$FrontmatterRaw)
        $result = @{}
        $lines = $FrontmatterRaw -split '\r?\n'
        foreach ($line in $lines) {
            if ($line -match '^(\w+):\s*(.*)$') {
                $key = $Matches[1]
                $value = $Matches[2].Trim()
                if ($value -match "^\[.*\]$") {
                    $result[$key] = $value
                }
                elseif ($value -eq '' -or $value -eq 'null') {
                    $result[$key] = $null
                }
                else {
                    if ($value -match '^"(.*)"$' -or $value -match "^'(.*)'$") {
                        $value = $Matches[1]
                    }
                    $result[$key] = $value
                }
            }
        }
        return $result
    }

    function Convert-HandoffSyntax {
        param([string]$Body, [string]$TargetSyntax)
        $result = $Body
        switch ($TargetSyntax) {
            "#runSubagent" {
                $result = $result -replace '`/agent\s+(\w+)`', '`#runSubagent with subagentType=$1`'
                $result = $result -replace '/agent\s+\[agent_name\]', '#runSubagent with subagentType={agent_name}'
            }
            "/agent" {
                $result = $result -replace '`#runSubagent with subagentType=(\w+)`', '`/agent $1`'
                $result = $result -replace '#runSubagent with subagentType=\{agent_name\}', '/agent [agent_name]'
            }
        }
        return $result
    }

    function Convert-FrontmatterForPlatform {
        param([hashtable]$Frontmatter, [hashtable]$PlatformConfig, [string]$AgentName)
        $result = @{}
        foreach ($key in $Frontmatter.Keys) {
            $value = $Frontmatter[$key]
            if ($value -notmatch '^\{\{PLATFORM_') {
                $result[$key] = $value
            }
        }
        $fm = $PlatformConfig['frontmatter']
        if ($fm -and $fm['includeNameField'] -eq $true) {
            $result['name'] = $AgentName
        }
        else {
            $result.Remove('name')
        }
        if ($fm -and $fm['model']) {
            $result['model'] = $fm['model']
        }
        else {
            $result.Remove('model')
        }
        return $result
    }
}

AfterAll {
    # Clean up test artifacts
    if (Test-Path $Script:TestTempDir) {
        Remove-Item -Path $Script:TestTempDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Describe "Test-PathWithinRoot" {
    Context "Security validation" {
        It "Returns true for path within root" {
            $root = $Script:TestTempDir
            $path = Join-Path $root "subfolder/file.md"

            Test-PathWithinRoot -Path $path -Root $root | Should -Be $true
        }

        It "Returns false for path outside root" {
            $root = $Script:TestTempDir
            $path = Join-Path (Split-Path $root -Parent) "other/file.md"

            Test-PathWithinRoot -Path $path -Root $root | Should -Be $false
        }

        It "Returns false for path traversal attempt" {
            $root = $Script:TestTempDir
            $path = Join-Path $root "..\..\..\etc\passwd"

            Test-PathWithinRoot -Path $path -Root $root | Should -Be $false
        }

        It "Handles relative paths correctly" {
            $root = $Script:TestTempDir
            $path = Join-Path $root "."

            Test-PathWithinRoot -Path $path -Root $root | Should -Be $true
        }

        It "Returns false for similar prefix paths (security edge case)" {
            # This test prevents prefix-matching attacks where C:\repo_evil
            # would incorrectly match C:\repo without proper separator handling
            $root = $Script:TestTempDir
            $path = "${root}_evil/file.md"

            Test-PathWithinRoot -Path $path -Root $root | Should -Be $false
        }
    }
}

Describe "Read-YamlFrontmatter" {
    Context "Valid frontmatter parsing" {
        It "Extracts frontmatter from valid markdown" {
            $content = @"
---
description: Test description
tools: ['tool1', 'tool2']
model: Claude Opus 4.5 (anthropic)
---
# Body content

Some markdown here.
"@
            $result = Read-YamlFrontmatter -Content $content

            $result | Should -Not -BeNullOrEmpty
            $result.FrontmatterRaw | Should -Match "description: Test description"
            $result.FrontmatterRaw | Should -Match "tools:"
            $result.Body | Should -Match "# Body content"
        }

        It "Handles multiline frontmatter" {
            $content = @"
---
description: A longer description
  that spans multiple lines
tools: ['tool1']
---
Body here
"@
            $result = Read-YamlFrontmatter -Content $content

            $result | Should -Not -BeNullOrEmpty
            $result.Body | Should -Be "Body here"
        }

        It "Returns null for content without frontmatter" {
            $content = "# Just a heading`n`nNo frontmatter here."

            $result = Read-YamlFrontmatter -Content $content

            $result | Should -BeNullOrEmpty
        }

        It "Returns null for malformed frontmatter" {
            $content = @"
---
description: Unclosed frontmatter
# Missing closing ---
"@
            $result = Read-YamlFrontmatter -Content $content

            $result | Should -BeNullOrEmpty
        }
    }
}

Describe "ConvertFrom-SimpleFrontmatter" {
    Context "Key-value parsing" {
        It "Parses simple key-value pairs" {
            $yaml = @"
description: Test description
model: Claude Opus 4.5 (anthropic)
"@
            $result = ConvertFrom-SimpleFrontmatter -FrontmatterRaw $yaml

            $result['description'] | Should -Be "Test description"
            $result['model'] | Should -Be "Claude Opus 4.5 (anthropic)"
        }

        It "Parses arrays in bracket notation" {
            $yaml = @"
tools: ['tool1', 'tool2', 'tool3']
"@
            $result = ConvertFrom-SimpleFrontmatter -FrontmatterRaw $yaml

            $result['tools'] | Should -Be "['tool1', 'tool2', 'tool3']"
        }

        It "Handles null values" {
            $yaml = @"
model: null
name:
"@
            $result = ConvertFrom-SimpleFrontmatter -FrontmatterRaw $yaml

            $result['model'] | Should -BeNullOrEmpty
            $result['name'] | Should -BeNullOrEmpty
        }

        It "Removes surrounding quotes from values" {
            $yaml = @"
description: "Quoted description"
name: 'Single quoted'
"@
            $result = ConvertFrom-SimpleFrontmatter -FrontmatterRaw $yaml

            $result['description'] | Should -Be "Quoted description"
            $result['name'] | Should -Be "Single quoted"
        }
    }
}

Describe "Convert-HandoffSyntax" {
    Context "VS Code syntax (#runSubagent)" {
        It "Converts /agent placeholder to #runSubagent" {
            $body = 'Invoke /agent [agent_name] with task'
            $result = Convert-HandoffSyntax -Body $body -TargetSyntax "#runSubagent"

            $result | Should -Match '#runSubagent with subagentType=\{agent_name\}'
        }

        It "Preserves content without handoff patterns" {
            $body = 'Use the implementer agent for implementation'
            $result = Convert-HandoffSyntax -Body $body -TargetSyntax "#runSubagent"

            $result | Should -Be $body
        }
    }

    Context "Copilot CLI syntax (/agent)" {
        It "Converts #runSubagent placeholder to /agent" {
            $body = 'Invoke #runSubagent with subagentType={agent_name} with task'
            $result = Convert-HandoffSyntax -Body $body -TargetSyntax "/agent"

            $result | Should -Match '/agent \[agent_name\]'
        }

        It "Preserves content without handoff patterns" {
            $body = 'Use the implementer agent for implementation'
            $result = Convert-HandoffSyntax -Body $body -TargetSyntax "/agent"

            $result | Should -Be $body
        }
    }

    Context "Preserves non-handoff content" {
        It "Does not modify unrelated content" {
            $body = "# Header`n`nSome regular content with code`nNo handoffs here."
            $result = Convert-HandoffSyntax -Body $body -TargetSyntax "#runSubagent"

            $result | Should -Be $body
        }
    }
}

Describe "Convert-FrontmatterForPlatform" {
    Context "VS Code transformation" {
        It "Adds model field and removes name field" {
            $frontmatter = @{
                description = "Test agent"
                tools       = "['tool1', 'tool2']"
            }
            $platformConfig = @{
                platform   = "vscode"
                frontmatter = @{
                    model           = "Claude Opus 4.5 (anthropic)"
                    includeNameField = $false
                }
            }

            $result = Convert-FrontmatterForPlatform -Frontmatter $frontmatter -PlatformConfig $platformConfig -AgentName "test"

            $result['model'] | Should -Be "Claude Opus 4.5 (anthropic)"
            $result.ContainsKey('name') | Should -Be $false
            $result['description'] | Should -Be "Test agent"
        }
    }

    Context "Copilot CLI transformation" {
        It "Adds name field and removes model field" {
            $frontmatter = @{
                description = "Test agent"
                tools       = "['tool1', 'tool2']"
            }
            $platformConfig = @{
                platform   = "copilot-cli"
                frontmatter = @{
                    model           = $null
                    includeNameField = $true
                }
            }

            $result = Convert-FrontmatterForPlatform -Frontmatter $frontmatter -PlatformConfig $platformConfig -AgentName "test"

            $result['name'] | Should -Be "test"
            $result.ContainsKey('model') | Should -Be $false
            $result['description'] | Should -Be "Test agent"
        }
    }

    Context "Placeholder handling" {
        It "Removes placeholder values from output" {
            $frontmatter = @{
                description = "Test agent"
                model       = "{{PLATFORM_MODEL}}"
                tools       = "{{PLATFORM_TOOLS}}"
            }
            $platformConfig = @{
                platform   = "vscode"
                frontmatter = @{
                    model           = "Claude Opus 4.5 (anthropic)"
                    includeNameField = $false
                }
            }

            $result = Convert-FrontmatterForPlatform -Frontmatter $frontmatter -PlatformConfig $platformConfig -AgentName "test"

            # Placeholder values should not be in output
            $result.Values | ForEach-Object { $_ | Should -Not -Match '\{\{PLATFORM_' }
        }
    }
}

Describe "Integration Tests" {
    Context "End-to-end generation" {
        BeforeAll {
            # Create test directory structure
            $Script:IntegrationTestDir = Join-Path $Script:TestTempDir "integration"
            $templatesDir = Join-Path $Script:IntegrationTestDir "templates"
            $agentsDir = Join-Path $templatesDir "agents"
            $platformsDir = Join-Path $templatesDir "platforms"
            $outputDir = Join-Path $Script:IntegrationTestDir "src"

            New-Item -ItemType Directory -Path $agentsDir -Force | Out-Null
            New-Item -ItemType Directory -Path $platformsDir -Force | Out-Null
            New-Item -ItemType Directory -Path $outputDir -Force | Out-Null

            # Create test shared source
            $sharedSource = @"
---
description: Test agent for integration testing
tools: ['tool1', 'tool2']
---
# Test Agent

## Core Mission

Test content with /agent [agent_name] handoff.
"@
            Set-Content -Path (Join-Path $agentsDir "test.shared.md") -Value $sharedSource

            # Create test platform configs
            $vscodeConfig = @"
platform: vscode
outputDir: src/vs-code-agents
fileExtension: .agent.md
frontmatter:
  model: "Claude Opus 4.5 (anthropic)"
  includeNameField: false
handoffSyntax: "#runSubagent"
"@
            Set-Content -Path (Join-Path $platformsDir "vscode.yaml") -Value $vscodeConfig

            $copilotConfig = @"
platform: copilot-cli
outputDir: src/copilot-cli
fileExtension: .agent.md
frontmatter:
  model: null
  includeNameField: true
handoffSyntax: "/agent"
"@
            Set-Content -Path (Join-Path $platformsDir "copilot-cli.yaml") -Value $copilotConfig
        }

        It "Script file exists" {
            $ScriptPath = Join-Path $PSScriptRoot "..\Generate-Agents.ps1"
            Test-Path $ScriptPath | Should -Be $true
        }

        It "Script has required parameters" {
            $ScriptPath = Join-Path $PSScriptRoot "..\Generate-Agents.ps1"
            $scriptContent = Get-Content $ScriptPath -Raw

            $scriptContent | Should -Match '\[switch\]\$Validate'
            $scriptContent | Should -Match 'SupportsShouldProcess'
        }
    }
}

Describe "Performance" {
    Context "Execution time" {
        It "Functions execute quickly" {
            $content = @"
---
description: Test
tools: ['tool1']
---
Body
"@
            $measure = Measure-Command {
                for ($i = 0; $i -lt 100; $i++) {
                    $parsed = Read-YamlFrontmatter -Content $content
                    $fm = ConvertFrom-SimpleFrontmatter -FrontmatterRaw $parsed.FrontmatterRaw
                }
            }

            # Should complete 100 iterations in under 1 second
            $measure.TotalSeconds | Should -BeLessThan 1
        }
    }
}

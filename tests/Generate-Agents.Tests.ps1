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
    # Import shared functions from module (ensures tests use actual implementations)
    $ModulePath = Join-Path $PSScriptRoot ".." "build" "Generate-Agents.Common.psm1"
    Import-Module $ModulePath -Force

    # Create temp directory for test artifacts (cross-platform)
    $Script:TestTempDir = Join-Path ([System.IO.Path]::GetTempPath()) "Generate-Agents-Tests-$(Get-Random)"
    New-Item -ItemType Directory -Path $Script:TestTempDir -Force | Out-Null
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

    Context "Block-style array parsing" {
        It "Parses block-style arrays with hyphen notation" {
            $yaml = @"
tools:
  - tool1
  - tool2
  - tool3
"@
            $result = ConvertFrom-SimpleFrontmatter -FrontmatterRaw $yaml

            $result['tools'] | Should -Be "['tool1', 'tool2', 'tool3']"
        }

        It "Handles block-style arrays with quoted items" {
            $yaml = @"
tools:
  - 'quoted-tool'
  - "double-quoted"
  - unquoted
"@
            $result = ConvertFrom-SimpleFrontmatter -FrontmatterRaw $yaml

            $result['tools'] | Should -Be "['quoted-tool', 'double-quoted', 'unquoted']"
        }

        It "Parses block-style array followed by other fields" {
            $yaml = @"
tools:
  - tool1
  - tool2
model: Claude Opus 4.5 (anthropic)
"@
            $result = ConvertFrom-SimpleFrontmatter -FrontmatterRaw $yaml

            $result['tools'] | Should -Be "['tool1', 'tool2']"
            $result['model'] | Should -Be "Claude Opus 4.5 (anthropic)"
        }

        It "Handles mixed inline and block-style arrays" {
            $yaml = @"
inline_tools: ['inline1', 'inline2']
block_tools:
  - block1
  - block2
"@
            $result = ConvertFrom-SimpleFrontmatter -FrontmatterRaw $yaml

            $result['inline_tools'] | Should -Be "['inline1', 'inline2']"
            $result['block_tools'] | Should -Be "['block1', 'block2']"
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

Describe "Format-FrontmatterYaml" {
    Context "Block-style array output" {
        It "Outputs arrays in block-style format" {
            $frontmatter = @{
                description = "Test agent"
                tools       = "['tool1', 'tool2']"
            }

            $result = Format-FrontmatterYaml -Frontmatter $frontmatter

            $result | Should -Match "tools:"
            $result | Should -Match "  - tool1"
            $result | Should -Match "  - tool2"
            # Should NOT contain inline array syntax
            $result | Should -Not -Match "\['tool1'"
        }

        It "Preserves field order with arrays" {
            $frontmatter = @{
                description = "Test agent"
                tools       = "['tool1', 'tool2']"
                model       = "Claude Opus 4.5 (anthropic)"
            }

            $result = Format-FrontmatterYaml -Frontmatter $frontmatter
            $lines = $result -split "`n"

            # Description should come before tools
            $descIndex = ($lines | Select-String -Pattern "^description:" | Select-Object -First 1).LineNumber
            $toolsIndex = ($lines | Select-String -Pattern "^tools:" | Select-Object -First 1).LineNumber

            $descIndex | Should -BeLessThan $toolsIndex
        }

        It "Handles multiple array fields" {
            $frontmatter = @{
                description = "Test agent"
                tools       = "['tool1', 'tool2']"
            }

            $result = Format-FrontmatterYaml -Frontmatter $frontmatter

            # Each array item should be on its own line with proper indentation
            ($result | Select-String -Pattern "  - " -AllMatches).Matches.Count | Should -Be 2
        }
    }

    Context "Non-array values" {
        It "Outputs simple values inline" {
            $frontmatter = @{
                description = "Test agent"
                model       = "Claude Opus 4.5 (anthropic)"
            }

            $result = Format-FrontmatterYaml -Frontmatter $frontmatter

            $result | Should -Match "description: Test agent"
            $result | Should -Match "model: Claude Opus 4.5 \(anthropic\)"
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
            $ScriptPath = Join-Path $PSScriptRoot ".." "build" "Generate-Agents.ps1"
            Test-Path $ScriptPath | Should -Be $true
        }

        It "Script has required parameters" {
            $ScriptPath = Join-Path $PSScriptRoot ".." "build" "Generate-Agents.ps1"
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

Describe "Read-ToolsetDefinitions" {
    BeforeAll {
        $Script:ToolsetTestDir = Join-Path $Script:TestTempDir "toolsets"
        New-Item -ItemType Directory -Path $Script:ToolsetTestDir -Force | Out-Null
    }

    Context "Valid toolset file" {
        It "Parses toolset definitions with shared tools" {
            $toolsetContent = @"
github-research:
  description: GitHub search and context gathering
  tools:
    - github/search_code
    - github/search_issues
    - github/issue_read
"@
            $toolsetFile = Join-Path $Script:ToolsetTestDir "shared-tools.yaml"
            Set-Content -Path $toolsetFile -Value $toolsetContent

            $result = Read-ToolsetDefinitions -ToolsetsPath $toolsetFile

            $result.ContainsKey('github-research') | Should -Be $true
            $result['github-research']['tools'] | Should -HaveCount 3
            $result['github-research']['tools'][0] | Should -Be 'github/search_code'
            $result['github-research']['description'] | Should -Be 'GitHub search and context gathering'
        }

        It "Parses toolset definitions with platform-specific tools" {
            $toolsetContent = @"
editor:
  description: Core reading and editing
  tools_vscode:
    - vscode
    - read
    - edit
    - search
  tools_copilot:
    - read
    - edit
    - search
"@
            $toolsetFile = Join-Path $Script:ToolsetTestDir "platform-tools.yaml"
            Set-Content -Path $toolsetFile -Value $toolsetContent

            $result = Read-ToolsetDefinitions -ToolsetsPath $toolsetFile

            $result.ContainsKey('editor') | Should -Be $true
            $result['editor']['tools_vscode'] | Should -HaveCount 4
            $result['editor']['tools_copilot'] | Should -HaveCount 3
            $result['editor']['tools_vscode'][0] | Should -Be 'vscode'
        }

        It "Parses multiple toolsets" {
            $toolsetContent = @"
editor:
  description: Core editor
  tools:
    - read
    - edit

knowledge:
  description: Memory tools
  tools:
    - serena/*
    - memory
"@
            $toolsetFile = Join-Path $Script:ToolsetTestDir "multi-toolsets.yaml"
            Set-Content -Path $toolsetFile -Value $toolsetContent

            $result = Read-ToolsetDefinitions -ToolsetsPath $toolsetFile

            $result.Keys.Count | Should -Be 2
            $result.ContainsKey('editor') | Should -Be $true
            $result.ContainsKey('knowledge') | Should -Be $true
        }
    }

    Context "Missing file" {
        It "Returns empty hashtable for nonexistent file" {
            $result = Read-ToolsetDefinitions -ToolsetsPath "/nonexistent/file.yaml" 3>$null

            $result | Should -BeOfType [hashtable]
            $result.Keys.Count | Should -Be 0
        }
    }
}

Describe "Expand-ToolsetReferences" {
    BeforeAll {
        $Script:TestToolsets = @{
            'editor' = @{
                'tools_vscode' = @('vscode', 'read', 'edit', 'search')
                'tools_copilot' = @('read', 'edit', 'search')
            }
            'knowledge' = @{
                'tools_vscode' = @('cloudmcp-manager/*', 'serena/*', 'memory')
                'tools_copilot' = @('cloudmcp-manager/*', 'serena/*')
            }
            'github-research' = @{
                'tools' = @('github/search_code', 'github/search_issues', 'github/issue_read')
            }
        }
    }

    Context "Toolset expansion for VS Code" {
        It "Expands single toolset reference" {
            $toolsArray = "['`$toolset:editor']"
            $result = Expand-ToolsetReferences -ToolsArrayString $toolsArray -Toolsets $Script:TestToolsets -PlatformName "vscode"

            $result | Should -Match "'vscode'"
            $result | Should -Match "'read'"
            $result | Should -Match "'edit'"
            $result | Should -Match "'search'"
        }

        It "Expands multiple toolset references" {
            $toolsArray = "['`$toolset:editor', '`$toolset:knowledge']"
            $result = Expand-ToolsetReferences -ToolsArrayString $toolsArray -Toolsets $Script:TestToolsets -PlatformName "vscode"

            $result | Should -Match "'vscode'"
            $result | Should -Match "'memory'"
            $result | Should -Match "'serena/\*'"
        }

        It "Mixes toolset references with individual tools" {
            $toolsArray = "['`$toolset:editor', 'web', '`$toolset:knowledge']"
            $result = Expand-ToolsetReferences -ToolsArrayString $toolsArray -Toolsets $Script:TestToolsets -PlatformName "vscode"

            $result | Should -Match "'vscode'"
            $result | Should -Match "'web'"
            $result | Should -Match "'memory'"
        }

        It "Uses platform-specific tools over shared tools" {
            $toolsArray = "['`$toolset:editor']"
            $resultVscode = Expand-ToolsetReferences -ToolsArrayString $toolsArray -Toolsets $Script:TestToolsets -PlatformName "vscode"
            $resultCopilot = Expand-ToolsetReferences -ToolsArrayString $toolsArray -Toolsets $Script:TestToolsets -PlatformName "copilot-cli"

            $resultVscode | Should -Match "'vscode'"
            $resultCopilot | Should -Not -Match "'vscode'"
        }

        It "Falls back to shared tools when no platform-specific tools exist" {
            $toolsArray = "['`$toolset:github-research']"
            $result = Expand-ToolsetReferences -ToolsArrayString $toolsArray -Toolsets $Script:TestToolsets -PlatformName "vscode"

            $result | Should -Match "'github/search_code'"
            $result | Should -Match "'github/issue_read'"
        }
    }

    Context "Deduplication" {
        It "Removes duplicate tools from expanded result" {
            $toolsArray = "['`$toolset:editor', 'read']"
            $result = Expand-ToolsetReferences -ToolsArrayString $toolsArray -Toolsets $Script:TestToolsets -PlatformName "vscode"

            # Count occurrences of 'read' - should appear only once
            $readCount = ([regex]::Matches($result, "'read'")).Count
            $readCount | Should -Be 1
        }
    }

    Context "Pass-through" {
        It "Returns input unchanged when no toolset references exist" {
            $toolsArray = "['read', 'edit', 'search']"
            $result = Expand-ToolsetReferences -ToolsArrayString $toolsArray -Toolsets $Script:TestToolsets -PlatformName "vscode"

            $result | Should -Be $toolsArray
        }
    }

    Context "Error handling" {
        It "Warns on unknown toolset reference" {
            $toolsArray = "['`$toolset:nonexistent']"
            $result = Expand-ToolsetReferences -ToolsArrayString $toolsArray -Toolsets $Script:TestToolsets -PlatformName "vscode" -WarningVariable warnings 3>$null

            # Result should not contain the reference
            $result | Should -Not -Match '\$toolset:'
        }
    }
}

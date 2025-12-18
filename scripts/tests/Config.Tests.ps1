<#
.SYNOPSIS
    Pester tests for Config.psd1 configuration validation.

.DESCRIPTION
    Validates that the configuration file is properly structured and
    contains all required entries for all environment/scope combinations.

.NOTES
    Requires Pester 5.x or later.
#>

BeforeAll {
    $Script:ConfigPath = Join-Path $PSScriptRoot "..\lib\Config.psd1"
    $Script:Config = Import-PowerShellDataFile -Path $Script:ConfigPath
}

Describe "Config.psd1 Structure" {
    Context "Root Level Keys" {
        It "Contains _Common configuration" {
            $Script:Config._Common | Should -Not -BeNullOrEmpty
        }

        It "Contains Claude configuration" {
            $Script:Config.Claude | Should -Not -BeNullOrEmpty
        }

        It "Contains Copilot configuration" {
            $Script:Config.Copilot | Should -Not -BeNullOrEmpty
        }

        It "Contains VSCode configuration" {
            $Script:Config.VSCode | Should -Not -BeNullOrEmpty
        }
    }
}

Describe "_Common Configuration" {
    Context "Required Keys" {
        It "Has BeginMarker" {
            $Script:Config._Common.BeginMarker | Should -Not -BeNullOrEmpty
            $Script:Config._Common.BeginMarker | Should -Match "BEGIN"
        }

        It "Has EndMarker" {
            $Script:Config._Common.EndMarker | Should -Not -BeNullOrEmpty
            $Script:Config._Common.EndMarker | Should -Match "END"
        }

        It "Has AgentsDirs" {
            $Script:Config._Common.AgentsDirs | Should -Not -BeNullOrEmpty
            # Note: Import-PowerShellDataFile may return Object[] which passes -is [array]
            @($Script:Config._Common.AgentsDirs).Count | Should -BeGreaterThan 0
        }
    }

    Context "AgentsDirs Content" {
        It "Contains analysis directory" {
            $Script:Config._Common.AgentsDirs | Should -Contain ".agents/analysis"
        }

        It "Contains architecture directory" {
            $Script:Config._Common.AgentsDirs | Should -Contain ".agents/architecture"
        }

        It "Contains planning directory" {
            $Script:Config._Common.AgentsDirs | Should -Contain ".agents/planning"
        }

        It "Contains qa directory" {
            $Script:Config._Common.AgentsDirs | Should -Contain ".agents/qa"
        }

        It "Contains retrospective directory" {
            $Script:Config._Common.AgentsDirs | Should -Contain ".agents/retrospective"
        }

        It "Contains security directory" {
            $Script:Config._Common.AgentsDirs | Should -Contain ".agents/security"
        }

        It "Has at least 8 directories" {
            @($Script:Config._Common.AgentsDirs).Count | Should -BeGreaterOrEqual 8
        }
    }

    Context "Marker Format" {
        It "BeginMarker is HTML comment format" {
            $Script:Config._Common.BeginMarker | Should -Match "^<!--.*-->$"
        }

        It "EndMarker is HTML comment format" {
            $Script:Config._Common.EndMarker | Should -Match "^<!--.*-->$"
        }

        It "Markers are markdown-compatible" {
            $Script:Config._Common.BeginMarker | Should -Match "ai-agents installer"
            $Script:Config._Common.EndMarker | Should -Match "ai-agents installer"
        }
    }
}

Describe "Claude Configuration" {
    BeforeAll {
        $Script:ClaudeConfig = $Script:Config.Claude
    }

    Context "Environment Properties" {
        It "Has DisplayName" {
            $Script:ClaudeConfig.DisplayName | Should -Be "Claude Code"
        }

        It "Has SourceDir" {
            $Script:ClaudeConfig.SourceDir | Should -Be "src/claude"
        }

        It "Has FilePattern" {
            $Script:ClaudeConfig.FilePattern | Should -Be "*.md"
        }
    }

    Context "Global Scope" {
        It "Has DestDir" {
            $Script:ClaudeConfig.Global.DestDir | Should -Not -BeNullOrEmpty
            $Script:ClaudeConfig.Global.DestDir | Should -Match "\.claude"
        }

        It "Has InstructionsFile" {
            $Script:ClaudeConfig.Global.InstructionsFile | Should -Be "CLAUDE.md"
        }

        It "Has InstructionsDest" {
            $Script:ClaudeConfig.Global.InstructionsDest | Should -Not -BeNullOrEmpty
        }

        It "Has CommandsDir" {
            $Script:ClaudeConfig.Global.CommandsDir | Should -Not -BeNullOrEmpty
            $Script:ClaudeConfig.Global.CommandsDir | Should -Match "\.claude.*commands"
        }

        It "Has CommandFiles array" {
            $Script:ClaudeConfig.Global.CommandFiles | Should -Not -BeNullOrEmpty
            @($Script:ClaudeConfig.Global.CommandFiles).Count | Should -BeGreaterThan 0
        }

        It "CommandFiles contains pr-comment-responder.md" {
            $Script:ClaudeConfig.Global.CommandFiles | Should -Contain "pr-comment-responder.md"
        }
    }

    Context "Repo Scope" {
        It "Has DestDir" {
            $Script:ClaudeConfig.Repo.DestDir | Should -Be ".claude/agents"
        }

        It "Has InstructionsFile" {
            $Script:ClaudeConfig.Repo.InstructionsFile | Should -Be "CLAUDE.md"
        }

        It "Has InstructionsDest defined (empty string valid for repo root)" {
            # Empty string is valid - means repo root
            $Script:ClaudeConfig.Repo.Keys | Should -Contain "InstructionsDest"
        }

        It "Has CommandsDir" {
            $Script:ClaudeConfig.Repo.CommandsDir | Should -Be ".claude/commands"
        }

        It "Has CommandFiles array" {
            $Script:ClaudeConfig.Repo.CommandFiles | Should -Not -BeNullOrEmpty
            @($Script:ClaudeConfig.Repo.CommandFiles).Count | Should -BeGreaterThan 0
        }

        It "CommandFiles contains pr-comment-responder.md" {
            $Script:ClaudeConfig.Repo.CommandFiles | Should -Contain "pr-comment-responder.md"
        }
    }
}

Describe "Copilot Configuration" {
    BeforeAll {
        $Script:CopilotConfig = $Script:Config.Copilot
    }

    Context "Environment Properties" {
        It "Has DisplayName" {
            $Script:CopilotConfig.DisplayName | Should -Be "GitHub Copilot CLI"
        }

        It "Has SourceDir" {
            $Script:CopilotConfig.SourceDir | Should -Be "src/copilot-cli"
        }

        It "Has FilePattern for agent files" {
            $Script:CopilotConfig.FilePattern | Should -Be "*.agent.md"
        }
    }

    Context "Known Bug Documentation" {
        It "Has KnownBug hashtable" {
            $Script:CopilotConfig.KnownBug | Should -Not -BeNullOrEmpty
        }

        It "KnownBug has Id" {
            $Script:CopilotConfig.KnownBug.Id | Should -Not -BeNullOrEmpty
        }

        It "KnownBug has Description" {
            $Script:CopilotConfig.KnownBug.Description | Should -Not -BeNullOrEmpty
        }

        It "KnownBug has Url" {
            $Script:CopilotConfig.KnownBug.Url | Should -Not -BeNullOrEmpty
            $Script:CopilotConfig.KnownBug.Url | Should -Match "^https?://"
        }
    }

    Context "Global Scope" {
        It "Has DestDir" {
            $Script:CopilotConfig.Global.DestDir | Should -Not -BeNullOrEmpty
            $Script:CopilotConfig.Global.DestDir | Should -Match "\.copilot"
        }

        It "Has null InstructionsFile (no global instructions)" {
            # Copilot CLI doesn't support global instructions file
            $Script:CopilotConfig.Global.InstructionsFile | Should -BeNullOrEmpty
        }

        It "Has PromptFiles array" {
            $Script:CopilotConfig.Global.PromptFiles | Should -Not -BeNullOrEmpty
            @($Script:CopilotConfig.Global.PromptFiles).Count | Should -BeGreaterThan 0
        }

        It "PromptFiles contains pr-comment-responder.agent.md" {
            $Script:CopilotConfig.Global.PromptFiles | Should -Contain "pr-comment-responder.agent.md"
        }
    }

    Context "Repo Scope" {
        It "Has DestDir" {
            $Script:CopilotConfig.Repo.DestDir | Should -Be ".github/agents"
        }

        It "Has InstructionsFile" {
            $Script:CopilotConfig.Repo.InstructionsFile | Should -Be "copilot-instructions.md"
        }

        It "Has InstructionsDest" {
            $Script:CopilotConfig.Repo.InstructionsDest | Should -Be ".github"
        }

        It "Has PromptFiles array" {
            $Script:CopilotConfig.Repo.PromptFiles | Should -Not -BeNullOrEmpty
            @($Script:CopilotConfig.Repo.PromptFiles).Count | Should -BeGreaterThan 0
        }

        It "PromptFiles contains pr-comment-responder.agent.md" {
            $Script:CopilotConfig.Repo.PromptFiles | Should -Contain "pr-comment-responder.agent.md"
        }
    }
}

Describe "VSCode Configuration" {
    BeforeAll {
        $Script:VSCodeConfig = $Script:Config.VSCode
    }

    Context "Environment Properties" {
        It "Has DisplayName" {
            $Script:VSCodeConfig.DisplayName | Should -Be "VS Code / Copilot Chat"
        }

        It "Has SourceDir" {
            $Script:VSCodeConfig.SourceDir | Should -Be "src/vs-code-agents"
        }

        It "Has FilePattern for agent files" {
            $Script:VSCodeConfig.FilePattern | Should -Be "*.agent.md"
        }
    }

    Context "Global Scope" {
        It "Has DestDir with Code/User/prompts" {
            $Script:VSCodeConfig.Global.DestDir | Should -Match "Code.*User.*prompts"
        }

        It "Has InstructionsFile" {
            $Script:VSCodeConfig.Global.InstructionsFile | Should -Be "copilot-instructions.md"
        }

        It "Has InstructionsDest" {
            $Script:VSCodeConfig.Global.InstructionsDest | Should -Not -BeNullOrEmpty
        }

        It "Has PromptFiles array" {
            $Script:VSCodeConfig.Global.PromptFiles | Should -Not -BeNullOrEmpty
            @($Script:VSCodeConfig.Global.PromptFiles).Count | Should -BeGreaterThan 0
        }

        It "PromptFiles contains pr-comment-responder.agent.md" {
            $Script:VSCodeConfig.Global.PromptFiles | Should -Contain "pr-comment-responder.agent.md"
        }
    }

    Context "Repo Scope" {
        It "Has DestDir" {
            $Script:VSCodeConfig.Repo.DestDir | Should -Be ".github/agents"
        }

        It "Has InstructionsFile" {
            $Script:VSCodeConfig.Repo.InstructionsFile | Should -Be "copilot-instructions.md"
        }

        It "Has InstructionsDest" {
            $Script:VSCodeConfig.Repo.InstructionsDest | Should -Be ".github"
        }

        It "Has PromptFiles array" {
            $Script:VSCodeConfig.Repo.PromptFiles | Should -Not -BeNullOrEmpty
            @($Script:VSCodeConfig.Repo.PromptFiles).Count | Should -BeGreaterThan 0
        }

        It "PromptFiles contains pr-comment-responder.agent.md" {
            $Script:VSCodeConfig.Repo.PromptFiles | Should -Contain "pr-comment-responder.agent.md"
        }
    }
}

Describe "Cross-Environment Consistency" {
    Context "Source Directory Structure" {
        It "Claude SourceDir starts with 'src/'" {
            $Script:Config.Claude.SourceDir | Should -Match "^src/"
        }

        It "Copilot SourceDir starts with 'src/'" {
            $Script:Config.Copilot.SourceDir | Should -Match "^src/"
        }

        It "VSCode SourceDir starts with 'src/'" {
            $Script:Config.VSCode.SourceDir | Should -Match "^src/"
        }
    }

    Context "Repo Scope Consistency" {
        It "All Repo scopes have DestDir" {
            $Script:Config.Claude.Repo.DestDir | Should -Not -BeNullOrEmpty
            $Script:Config.Copilot.Repo.DestDir | Should -Not -BeNullOrEmpty
            $Script:Config.VSCode.Repo.DestDir | Should -Not -BeNullOrEmpty
        }

        It "All Repo scopes have InstructionsFile" {
            $Script:Config.Claude.Repo.InstructionsFile | Should -Not -BeNullOrEmpty
            $Script:Config.Copilot.Repo.InstructionsFile | Should -Not -BeNullOrEmpty
            $Script:Config.VSCode.Repo.InstructionsFile | Should -Not -BeNullOrEmpty
        }
    }

    Context "File Pattern Consistency" {
        It "Copilot and VSCode use same file pattern" {
            $Script:Config.Copilot.FilePattern | Should -Be $Script:Config.VSCode.FilePattern
        }

        It "Claude uses different file pattern (*.md vs *.agent.md)" {
            $Script:Config.Claude.FilePattern | Should -Not -Be $Script:Config.Copilot.FilePattern
        }
    }
}

Describe "Path Expression Validity" {
    Context "Global Paths Use Environment Variables" {
        It "Claude Global DestDir uses `$HOME" {
            $Script:Config.Claude.Global.DestDir | Should -Match '\$HOME'
        }

        It "Copilot Global DestDir uses `$HOME" {
            $Script:Config.Copilot.Global.DestDir | Should -Match '\$HOME'
        }

        It "VSCode Global DestDir uses `$env:APPDATA or similar" {
            $Script:Config.VSCode.Global.DestDir | Should -Match '\$env:'
        }
    }

    Context "Repo Paths Are Relative" {
        It "Claude Repo DestDir is relative" {
            $Script:Config.Claude.Repo.DestDir | Should -Not -Match '^\$'
            $Script:Config.Claude.Repo.DestDir | Should -Not -Match '^[A-Za-z]:'
        }

        It "Copilot Repo DestDir is relative" {
            $Script:Config.Copilot.Repo.DestDir | Should -Not -Match '^\$'
        }

        It "VSCode Repo DestDir is relative" {
            $Script:Config.VSCode.Repo.DestDir | Should -Not -Match '^\$'
        }
    }
}

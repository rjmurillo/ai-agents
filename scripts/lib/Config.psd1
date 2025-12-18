<#
.SYNOPSIS
    Configuration data for ai-agents installer.

.DESCRIPTION
    Contains environment-specific settings for Claude, Copilot CLI, and VSCode agent installations.
    Referenced by Install-Common.psm1 and install.ps1.
#>
@{
    # Shared configuration (referenced by all environments)
    _Common = @{
        # Markdown-compatible markers for upgradeable content blocks
        BeginMarker = "<!-- BEGIN: ai-agents installer -->"
        EndMarker   = "<!-- END: ai-agents installer -->"

        # Consistent .agents directories across all environments
        AgentsDirs  = @(
            ".agents/analysis"
            ".agents/architecture"
            ".agents/planning"
            ".agents/critique"
            ".agents/qa"
            ".agents/retrospective"
            ".agents/roadmap"
            ".agents/devops"
            ".agents/security"
            ".agents/sessions"
        )
    }

    Claude = @{
        DisplayName = "Claude Code"
        SourceDir   = "src/claude"
        FilePattern = "*.md"
        Global      = @{
            DestDir          = '$HOME/.claude/agents'
            InstructionsFile = "CLAUDE.md"
            InstructionsDest = '$HOME/.claude'
            # Claude commands (slash commands)
            CommandsDir      = '$HOME/.claude/commands'
            CommandFiles     = @(
                "pr-comment-responder.md"
            )
        }
        Repo        = @{
            DestDir          = '.claude/agents'
            InstructionsFile = "CLAUDE.md"
            InstructionsDest = ''  # Root of repo
            # Claude commands for repo scope
            CommandsDir      = '.claude/commands'
            CommandFiles     = @(
                "pr-comment-responder.md"
            )
        }
    }

    Copilot = @{
        DisplayName = "GitHub Copilot CLI"
        SourceDir   = "src/copilot-cli"
        FilePattern = "*.agent.md"
        KnownBug    = @{
            Id          = "#452"
            Description = "User-level agents not loaded"
            Url         = "https://github.com/github/copilot-cli/issues/452"
        }
        Global      = @{
            # XDG_CONFIG_HOME takes precedence, then USERPROFILE, then HOME
            DestDir          = '$HOME/.copilot/agents'
            InstructionsFile = $null  # No global instructions file
            InstructionsDest = $null
            # Prompt files (copied alongside agents with .prompt.md extension)
            PromptFiles      = @(
                "pr-comment-responder.agent.md"
            )
        }
        Repo        = @{
            DestDir          = '.github/agents'
            InstructionsFile = "copilot-instructions.md"
            InstructionsDest = '.github'
            # Prompt files (copied alongside agents with .prompt.md extension)
            PromptFiles      = @(
                "pr-comment-responder.agent.md"
            )
        }
    }

    VSCode = @{
        DisplayName = "VS Code / Copilot Chat"
        SourceDir   = "src/vs-code-agents"
        FilePattern = "*.agent.md"
        Global      = @{
            # APPDATA on Windows, .config/Code on Unix
            DestDir          = '$env:APPDATA/Code/User/prompts'
            InstructionsFile = "copilot-instructions.md"
            InstructionsDest = '$env:APPDATA/Code/User/prompts'
            # Prompt files (copied alongside agents with .prompt.md extension)
            PromptFiles      = @(
                "pr-comment-responder.agent.md"
            )
        }
        Repo        = @{
            DestDir          = '.github/agents'
            InstructionsFile = "copilot-instructions.md"
            InstructionsDest = '.github'
            # Prompt files (copied alongside agents with .prompt.md extension)
            PromptFiles      = @(
                "pr-comment-responder.agent.md"
            )
        }
    }
}

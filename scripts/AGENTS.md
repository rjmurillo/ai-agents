# Installation & Utility Agents

This document describes the automated actors in the scripts system that handle agent installation, configuration sync, and validation utilities.

## Overview

The `scripts/` directory contains PowerShell scripts that automate installation of AI agents to different platforms, synchronize MCP configurations, and validate session protocol compliance.

## Architecture

```mermaid
flowchart TD
    subgraph Sources["Source Files"]
        SC[src/claude/*.md]
        SV[src/vs-code-agents/*.agent.md]
        SCP[src/copilot-cli/*.agent.md]
        MCP[.mcp.json]
    end

    subgraph Scripts["Script Agents"]
        INS[install.ps1]
        SYN[Sync-McpConfig.ps1]
        CHK[Check-SkillExists.ps1]
        VCS[Validate-Consistency.ps1]
        VSP[Validate-SessionProtocol.ps1]
    end

    subgraph Lib["Shared Library"]
        COM[lib/Install-Common.psm1]
        CFG[lib/Config.psd1]
    end

    subgraph Targets["Installation Targets"]
        CLG[~/.claude/agents]
        VSG[%APPDATA%/Code/User/prompts]
        CPG[~/.copilot/agents]
        REP[.claude/agents or .github/agents]
    end

    SC --> INS
    SV --> INS
    SCP --> INS
    COM --> INS
    CFG --> INS
    INS --> CLG
    INS --> VSG
    INS --> CPG
    INS --> REP

    MCP --> SYN
    SYN --> VSC[.vscode/mcp.json]

    style Sources fill:#e1f5fe
    style Scripts fill:#fff3e0
    style Lib fill:#fce4ec
    style Targets fill:#e8f5e9
```

## Agent Catalog

### install.ps1 (Unified Installer)

**Role**: Single entry point for all agent installations

| Attribute | Value |
|-----------|-------|
| **Input** | Environment, scope parameters |
| **Output** | Installed agent files |
| **Trigger** | Manual, remote execution |
| **Dependencies** | `lib/Install-Common.psm1`, `lib/Config.psd1` |

**Parameters**:

| Parameter | Type | Description |
|-----------|------|-------------|
| `-Environment` | String | `Claude`, `Copilot`, or `VSCode` |
| `-Global` | Switch | Install to user-level location |
| `-RepoPath` | String | Install to specified repository |
| `-Force` | Switch | Overwrite without prompting |

**Invocation**:

```powershell
# Remote installation (one-liner)
iex ((New-Object System.Net.WebClient).DownloadString(
  'https://raw.githubusercontent.com/rjmurillo/ai-agents/main/scripts/install.ps1'))

# Local installation
.\install.ps1 -Environment Claude -Global
.\install.ps1 -Environment VSCode -RepoPath "C:\MyRepo"
.\install.ps1 -Environment Copilot -RepoPath "." -Force
```

**Installation Matrix**:

| Environment | Global Location | Repo Location |
|-------------|-----------------|---------------|
| Claude | `~/.claude/agents` | `.claude/agents` |
| VSCode | `%APPDATA%/Code/User/prompts` | `.github/agents` |
| Copilot | `~/.copilot/agents` | `.github/agents` |

---

### Legacy Installation Scripts

For backward compatibility, individual scripts wrap the unified installer:

| Script | Equivalent |
|--------|------------|
| `install-claude-global.ps1` | `install.ps1 -Environment Claude -Global` |
| `install-claude-repo.ps1` | `install.ps1 -Environment Claude -RepoPath <path>` |
| `install-copilot-cli-global.ps1` | `install.ps1 -Environment Copilot -Global` |
| `install-copilot-cli-repo.ps1` | `install.ps1 -Environment Copilot -RepoPath <path>` |
| `install-vscode-global.ps1` | `install.ps1 -Environment VSCode -Global` |
| `install-vscode-repo.ps1` | `install.ps1 -Environment VSCode -RepoPath <path>` |

---

### Sync-McpConfig.ps1

**Role**: MCP configuration synchronizer between Claude and VS Code

| Attribute | Value |
|-----------|-------|
| **Input** | `.mcp.json` (Claude Code format) |
| **Output** | `.vscode/mcp.json` (VS Code format) |
| **Trigger** | Manual |
| **Dependencies** | PowerShell 7.0+ |

**Transformations Applied**:

| From (Claude) | To (VS Code) |
|---------------|--------------|
| Root key `mcpServers` | Root key `servers` |
| Serena `--context "claude-code"` | `--context "ide"` |
| Serena `--port "24282"` | `--port "24283"` |

**Invocation**:

```powershell
# Sync with default paths
.\Sync-McpConfig.ps1

# Preview changes
.\Sync-McpConfig.ps1 -WhatIf

# Force overwrite
.\Sync-McpConfig.ps1 -Force
```

---

### Check-SkillExists.ps1

**Role**: Skill existence verification for Phase 1.5 BLOCKING gate

| Attribute | Value |
|-----------|-------|
| **Input** | Operation type, action name |
| **Output** | Boolean result or skill list |
| **Trigger** | Session protocol validation |
| **Dependencies** | `.claude/skills/` directory |

**Invocation**:

```powershell
# Check for specific skill
.\Check-SkillExists.ps1 -Operation "pr" -Action "PRContext"  # Returns: $true

# List all available skills
.\Check-SkillExists.ps1 -ListAvailable
```

**Parameters**:

| Parameter | Values | Description |
|-----------|--------|-------------|
| `-Operation` | `pr`, `issue`, `reactions`, `label`, `milestone` | Skill category |
| `-Action` | String | Substring match against script names |
| `-ListAvailable` | Switch | List all skills organized by type |

---

### Validate-Consistency.ps1

**Role**: Cross-document consistency validator

| Attribute | Value |
|-----------|-------|
| **Input** | `.agents/` directory artifacts |
| **Output** | Consistency report |
| **Trigger** | Manual, CI |
| **Dependencies** | PowerShell 7.0+ |

**Validations**:

- Naming convention compliance
- Cross-reference integrity
- Requirement coverage

---

### Validate-SessionProtocol.ps1

**Role**: Session protocol compliance checker with comprehensive validation features

| Attribute | Value |
|-----------|-------|
| **Input** | Session logs in `.agents/sessions/` |
| **Output** | Protocol compliance report (console/markdown/json) |
| **Trigger** | Pre-commit hook, CI on session log changes |
| **Dependencies** | PowerShell 7.0+ |
| **Status** | Consolidated - all features from `Validate-Session.ps1` merged |

**Checks Performed**:

| Check | Level | Description |
|-------|-------|-------------|
| Session log exists | MUST | File at correct path with naming |
| Protocol Compliance section | MUST | Section present in log |
| MUST requirements completed | MUST | All mandatory items checked |
| Template enforcement | MUST | Exact row order matches SESSION-PROTOCOL.md |
| Memory evidence validation | MUST | Memory names exist in `.serena/memories/` (ADR-007) |
| QA skip validation | MUST | Docs-only/investigation-only claims validated |
| Branch verification | MUST | Branch name matches session log declaration |
| Git commit validation | MUST | Commit SHA verification |
| HANDOFF.md updated | MUST | Modified timestamp recent |
| SHOULD requirements | SHOULD | Warnings (not errors) |

**Invocation**:

```powershell
# Validate specific session
.\Validate-SessionProtocol.ps1 -SessionPath ".agents/sessions/2025-12-18-session-24.md"

# Pre-commit mode (validates staged files)
.\Validate-SessionProtocol.ps1 -SessionPath ".agents/sessions/2025-12-18-session-24.md" -PreCommit

# Validate all recent sessions
.\Validate-SessionProtocol.ps1 -All -Recent 7

# CI mode with markdown output
.\Validate-SessionProtocol.ps1 -All -CI -Format markdown

# JSON output
.\Validate-SessionProtocol.ps1 -SessionPath ".agents/sessions/2025-12-18-session-24.md" -Format json
```

**Note**: `Validate-Session.ps1` is deprecated. All features have been merged into this consolidated script.

---

## Shared Library

### lib/Install-Common.psm1

Shared functions used by all installation scripts:

| Function | Purpose |
|----------|---------|
| `Get-InstallConfig` | Load environment/scope configuration |
| `Resolve-DestinationPath` | Expand path expressions |
| `Test-SourceDirectory` | Validate source exists |
| `Get-AgentFiles` | Find agent files by pattern |
| `Initialize-Destination` | Create destination directory |
| `Test-GitRepository` | Check if path is git repo |
| `Initialize-AgentsDirectories` | Create `.agents/` subdirectories |
| `Copy-AgentFile` | Copy single agent with prompting |
| `Install-InstructionsFile` | Install/upgrade instructions |
| `Write-InstallHeader` | Display installation header |
| `Write-InstallComplete` | Display completion message |

### lib/Config.psd1

Environment-specific configuration:

```powershell
@{
    _Common = @{
        BeginMarker = "<!-- BEGIN: ai-agents installer -->"
        EndMarker = "<!-- END: ai-agents installer -->"
        AgentsDirs = @(".agents/analysis", ".agents/planning", ...)
    }

    Claude = @{
        DisplayName = "Claude Code"
        SourceDir = "src/claude"
        FilePattern = "*.md"
        Global = @{ DestDir = '$HOME/.claude/agents' }
        Repo = @{ DestDir = '.claude/agents' }
    }

    # VSCode, Copilot configurations...
}
```

---

## Data Flow

```mermaid
sequenceDiagram
    participant User
    participant Install as install.ps1
    participant Config as lib/Config.psd1
    participant Common as lib/Install-Common.psm1
    participant Source as src/*
    participant Target as Installation Target

    User->>Install: Specify environment + scope
    Install->>Config: Load configuration
    Config-->>Install: Environment settings
    Install->>Common: Initialize
    Install->>Source: Get agent files
    Source-->>Install: File list
    loop For each agent
        Install->>Common: Copy-AgentFile
        Common->>Target: Write file
    end
    Install->>Common: Install-InstructionsFile
    Common->>Target: Update instructions
    Install-->>User: Installation complete
```

## Error Handling

| Agent | Error Scenario | Behavior |
|-------|---------------|----------|
| install.ps1 | Source not found | Exit with path error |
| install.ps1 | Permission denied | Prompt for elevated permissions |
| install.ps1 | File exists | Prompt unless `-Force` |
| Sync-McpConfig.ps1 | Source missing | Exit with path error |
| Validate-SessionProtocol.ps1 | Session not found | Warning, continue |

## Security Considerations

| Agent | Security Control |
|-------|-----------------|
| install.ps1 | Path validation prevents traversal |
| install.ps1 | Remote execution uses HTTPS only |
| Sync-McpConfig.ps1 | No external network access |
| All scripts | No credential handling |

## Testing

Tests are located in `scripts/tests/`:

| Test File | Coverage |
|-----------|----------|
| `Install-Common.Tests.ps1` | All 11 module functions |
| `Config.Tests.ps1` | Configuration validation |
| `install.Tests.ps1` | Entry point parameter validation |
| `Sync-McpConfig.Tests.ps1` | MCP sync transformations |
| `Validate-SessionProtocol.Tests.ps1` | Protocol validation logic |

**Running Tests**:

```powershell
# All tests
Invoke-Pester -Path .\scripts\tests

# Specific file
Invoke-Pester -Path .\scripts\tests\Install-Common.Tests.ps1

# Detailed output
Invoke-Pester -Path .\scripts\tests -Output Detailed
```

## Monitoring

| Agent | CI Workflow | Trigger |
|-------|------------|---------|
| install.ps1 | `pester-tests.yml` | PR to `scripts/**` |
| Sync-McpConfig.ps1 | `pester-tests.yml` | PR to `scripts/**` |
| Validate-SessionProtocol.ps1 | `ai-session-protocol.yml` | PR to `.agents/**` |

## Related Documentation

- [scripts/README.md](README.md) - Installation guide
- [build/AGENTS.md](../build/AGENTS.md) - Build automation agents
- [.github/AGENTS.md](../.github/AGENTS.md) - GitHub Actions agents

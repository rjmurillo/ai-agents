# Scripts Directory: Agents and Coding Standards

> **Scope**: Scripts directory. Auto-loaded when working in `scripts/`.
> **Primary Reference**: Root CLAUDE.md and AGENTS.md take precedence.

This document contains PowerShell coding standards and describes the automated actors that handle agent installation, configuration sync, and validation utilities.

---

## PowerShell Coding Standards

### Language Constraint

**PowerShell only** (.ps1/.psm1) per ADR-005.

No bash or Python scripts in this directory. Cross-platform consistency via PowerShell.

### Script Structure

```powershell
<#
.SYNOPSIS
Brief description

.PARAMETER ParamName
Parameter description

.EXAMPLE
Example usage

.NOTES
    EXIT CODES:
    0  - Success: Operation completed
    1  - Error: Validation/logic failure
    2  - Error: Missing required parameter
    3  - Error: GitHub API error
    4  - Error: Authentication failure

    See ADR-035 for complete reference.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$RequiredParam,

    [string]$OptionalParam
)

$ErrorActionPreference = 'Stop'

# Functions
function Verb-Noun {
    [CmdletBinding()]
    param()

    # Implementation
}

# Main logic
try {
    Verb-Noun
    exit 0
} catch {
    Write-Error $_.Exception.Message
    exit 1
}
```

### Naming Conventions

- Scripts: `Verb-Noun.ps1` (PascalCase, approved verbs)
- Functions: `Verb-Noun` (PascalCase, approved verbs)
- Variables: `$camelCase` or `$PascalCase` for exported
- Parameters: `$PascalCase`

### Error Handling Pattern

```powershell
$ErrorActionPreference = 'Stop'  # Fail fast

try {
    # Operations
    exit 0  # Success
} catch {
    Write-Error $_.Exception.Message
    exit 1  # Failure
}
```

### Cross-Platform Patterns

```powershell
# Path separators
$path = Join-Path $dir $file  # Not "$dir/$file"

# Line endings
Get-Content -Raw  # Preserves line endings

# Case sensitivity
Use [StringComparison]::OrdinalIgnoreCase for comparisons
```

### Testing Standards

- Pester tests in `tests/` or adjacent to scripts
- Test isolation: No global state
- Parameterized tests: `@()` arrays
- CI validation: All tests run on push

### Module Structure

```powershell
# {Module}.psm1
function Export-Function1 { }
function Export-Function2 { }

Export-ModuleMember -Function Export-Function1, Export-Function2
```

### Security

- No secrets in scripts (use environment variables or parameters)
- Validate input at system boundaries
- Use approved parameter sets for mutually exclusive options

### Related References

- Exit codes: `.agents/architecture/ADR-035-exit-code-standardization.md`
- Skill development: `.claude/skills/CLAUDE.md`
- ADR-005: PowerShell-only architecture

---

## Installation & Utility Agents

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
        SYN[Sync-McpConfig.ps1]
        CHK[check_skill_exists.py]
        VCS[Validate-Consistency.ps1]
        VSP[validate_session_json.py]
    end

    MCP --> SYN
    SYN --> VSC[.vscode/mcp.json]

    style Sources fill:#e1f5fe
    style Scripts fill:#fff3e0
```

> **Note**: Agent installation is handled by [skill-installer](https://github.com/rjmurillo/skill-installer).
> See [docs/installation.md](../docs/installation.md) for installation instructions.

## Agent Catalog

### Sync-McpConfig.ps1

**Role**: MCP configuration synchronizer between Claude and VS Code

| Attribute | Value |
|-----------|-------|
| **Input** | `.mcp.json` (Claude Code format) |
| **Output** | `.vscode/mcp.json` (VS Code format) |
| **Trigger** | Manual |
| **Dependencies** | PowerShell 7.5.4+ |

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
| **Dependencies** | PowerShell 7.5.4+ |

**Validations**:

- Naming convention compliance
- Cross-reference integrity
- Requirement coverage

---

### validate_session_json.py

**Role**: Session protocol compliance checker

| Attribute | Value |
|-----------|-------|
| **Input** | Session logs in `.agents/sessions/` |
| **Output** | Protocol compliance report |
| **Trigger** | CI on session log changes |
| **Dependencies** | Python 3.10+ |

**Checks Performed**:

| Check | Level | Description |
|-------|-------|-------------|
| Session log exists | MUST | File at correct path with naming |
| Protocol Compliance section | MUST | Section present in log |
| MUST requirements completed | MUST | All mandatory items checked |
| HANDOFF.md updated | MUST | Modified timestamp recent |
| SHOULD requirements | SHOULD | Warnings (not errors) |

**Invocation**:

```bash
# Validate specific session
python3 scripts/validate_session_json.py .agents/sessions/2025-12-18-session-24.json

# Pre-commit mode
python3 scripts/validate_session_json.py .agents/sessions/2025-12-18-session-24.json --pre-commit
```

---

## Error Handling

| Agent | Error Scenario | Behavior |
|-------|---------------|----------|
| Sync-McpConfig.ps1 | Source missing | Exit with path error |
| validate_session_json.py | Session not found | Warning, continue |
| Validate-*.ps1 | Validation failure | Exit with error code |

## Security Considerations

| Agent | Security Control |
|-------|-----------------|
| Sync-McpConfig.ps1 | No external network access |
| All scripts | No credential handling |
| All scripts | Path validation prevents traversal |

## Testing

Tests are located in `tests/`:

| Test File | Coverage |
|-----------|----------|
| `Sync-McpConfig.Tests.ps1` | MCP sync transformations |
| `Validate-SessionJson.Tests.ps1` | Session protocol validation |

**Running Tests**:

```powershell
# All tests
Invoke-Pester -Path .\tests

# Specific file
Invoke-Pester -Path .\tests\Sync-McpConfig.Tests.ps1

# Detailed output
Invoke-Pester -Path .\tests -Output Detailed
```

## Monitoring

| Agent | CI Workflow | Trigger |
|-------|------------|---------|
| Sync-McpConfig.ps1 | `pester-tests.yml` | PR to `scripts/**` |
| validate_session_json.py | `ai-session-protocol.yml` | PR to `.agents/**` |

## Related Documentation

- [scripts/README.md](README.md) - Installation guide
- [build/AGENTS.md](../build/AGENTS.md) - Build automation agents
- [.github/AGENTS.md](../.github/AGENTS.md) - GitHub Actions agents

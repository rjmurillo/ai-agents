# Agent Templates

This directory contains the shared agent template system for generating platform-specific agent definitions.

> **Governing ADR**: [ADR-036: Two-Source Agent Template Architecture](../.agents/architecture/ADR-036-two-source-agent-template-architecture.md)

## Directory Structure

```text
templates/
  agents/                    # Shared agent definitions (SOURCE OF TRUTH)
    analyst.shared.md        # Analyst agent template
    architect.shared.md      # Architect agent template
    implementer.shared.md    # Implementer agent template
    orchestrator.shared.md   # Orchestrator agent template
    ...                      # Other agent templates
  platforms/                 # Platform-specific configurations
    vscode.yaml              # VS Code / GitHub Copilot settings
    copilot-cli.yaml         # Copilot CLI settings
  README.md                  # This file
```

## How It Works

### Template System

The template system maintains a single source of truth for agent behavior while generating platform-specific outputs:

1. **Shared Templates** (`agents/*.shared.md`): Define agent behavior, responsibilities, and content
2. **Platform Configs** (`platforms/*.yaml`): Specify platform-specific settings (model, tools, syntax)
3. **Generation Script** (`build/Generate-Agents.ps1`): Transforms templates into platform-specific files

### Generation Flow

```text
templates/agents/*.shared.md     Source of truth
           |
           v
build/Generate-Agents.ps1        Transformation
           |
           +---> src/vs-code-agents/*.agent.md    VS Code output
           +---> src/copilot-cli/*.agent.md       Copilot CLI output
```

### Platform Transformations

The generation script applies platform-specific transformations:

| Feature | VS Code | Copilot CLI |
|---------|---------|-------------|
| Model field | `Claude Opus 4.5 (anthropic)` | Not included |
| Name field | Not included | Required |
| Handoff syntax | `#runSubagent` | `/agent` |
| File extension | `.agent.md` | `.agent.md` |
| Tools array | `tools_vscode` | `tools_copilot` |

## Usage

### Generate Platform Files

```powershell
# Generate all agents
pwsh build/Generate-Agents.ps1

# Preview without writing
pwsh build/Generate-Agents.ps1 -WhatIf

# Validate generated files match templates
pwsh build/Generate-Agents.ps1 -Validate
```

### Modify an Agent

**CRITICAL (ADR-036)**: The pre-commit hook generates VS Code/Copilot files but does NOT sync to Claude agents.

For **universal changes** (content that applies to ALL platforms):

1. Edit the source template: `templates/agents/{agent}.shared.md`
2. **Also edit**: `src/claude/{agent}.md` (MANUAL - not auto-synced!)
3. Regenerate: `pwsh build/Generate-Agents.ps1`
4. Commit template, Claude source, and generated files together

For **Claude-specific changes** (MCP tools, Serena integration):

- Edit only `src/claude/{agent}.md` - do NOT add to templates

### Add a New Agent

1. Create `templates/agents/{name}.shared.md`
2. Define frontmatter with platform-specific tools:

   ```yaml
   ---
   description: Agent description
   tools_vscode: ['vscode', 'read', 'search', 'cloudmcp-manager/*']
   tools_copilot: ['shell', 'read', 'edit', 'search', 'agent', 'cloudmcp-manager/*']
   ---
   ```

3. Add agent content following existing patterns
4. Run `pwsh build/Generate-Agents.ps1`
5. Update documentation (README.md, CLAUDE.md)

## Drift Detection

Claude agents (`src/claude/`) are maintained separately from the template system. To ensure consistency between Claude agents and the generated VS Code/Copilot agents:

### Weekly CI Check

A GitHub Actions workflow runs weekly to detect semantic drift between Claude agents and VS Code agents (which are generated from templates):

- **Schedule**: Monday 9 AM UTC
- **Workflow**: `.github/workflows/drift-detection.yml`
- **Script**: `build/scripts/Detect-AgentDrift.ps1`

### Run Locally

```powershell
# Check for drift (default 80% similarity threshold)
pwsh build/scripts/Detect-AgentDrift.ps1

# Get JSON output for tooling
pwsh build/scripts/Detect-AgentDrift.ps1 -OutputFormat JSON

# Get markdown report
pwsh build/scripts/Detect-AgentDrift.ps1 -OutputFormat Markdown

# Use stricter threshold
pwsh build/scripts/Detect-AgentDrift.ps1 -SimilarityThreshold 90
```

### What Gets Compared

The script compares semantic content in key sections while ignoring platform-specific differences:

**Sections Compared:**

- Core Identity / Core Mission
- Key Responsibilities
- Constraints
- Handoff Options / Execution Mindset
- Memory Protocol
- Analysis Types / ADR Templates

**Ignored (Platform-Specific):**

- Claude Code Tools section
- Tool invocation syntax (`mcp__cloudmcp-manager__*` vs `cloudmcp-manager/*`)
- Frontmatter format differences
- Handoff syntax (`/agent` vs `#runSubagent`)

### Drift Types

| Type | Description | Action |
|------|-------------|--------|
| DRIFT DETECTED | Similarity below threshold (default 80%) | Review and sync content |
| NO COUNTERPART | Claude agent has no VS Code equivalent | Create template or justify exclusion |
| OK | Content is sufficiently similar | No action needed |

### Handling Drift

When drift is detected:

1. Review the GitHub issue created by the workflow
2. Determine if drift is intentional or accidental
3. Either:
   - Update Claude agents to match VS Code/templates
   - Update templates to include Claude improvements
   - Document intentional differences

## Related Documentation

- [ADR-036: Two-Source Agent Template Architecture](../.agents/architecture/ADR-036-two-source-agent-template-architecture.md) - Governing architecture decision
- [src/claude/AGENTS.md](../src/claude/AGENTS.md) - Claude agent synchronization rules
- [CONTRIBUTING.md](../CONTRIBUTING.md) - Full contribution guide
- [build/Generate-Agents.ps1](../build/Generate-Agents.ps1) - Generation script
- [build/scripts/Detect-AgentDrift.ps1](../build/scripts/Detect-AgentDrift.ps1) - Drift detection script
- [.github/workflows/validate-generated-agents.yml](../.github/workflows/validate-generated-agents.yml) - CI validation
- [.github/workflows/drift-detection.yml](../.github/workflows/drift-detection.yml) - Drift detection CI

## Template Format

### Frontmatter

```yaml
---
description: Brief description of the agent's purpose
tools_vscode: ['vscode', 'read', 'search', 'cloudmcp-manager/*']
tools_copilot: ['shell', 'read', 'edit', 'search', 'agent', 'cloudmcp-manager/*']
---
```

### Required Sections

- `# Agent Name` - Display name
- `## Core Identity` - Role description
- `## Core Mission` - Primary objective
- `## Key Responsibilities` - Numbered list
- `## Constraints` - What the agent should NOT do
- `## Memory Protocol` - cloudmcp-manager usage
- `## Handoff Options` - When to hand off to other agents

See `agents/analyst.shared.md` for a complete example.

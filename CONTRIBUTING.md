# Contributing to AI Agent System

Thank you for your interest in contributing to this project. This guide explains how to contribute effectively, with special attention to the agent template system.

## Table of Contents

- [Getting Started](#getting-started)
- [Agent Template System](#agent-template-system)
- [How to Modify an Agent](#how-to-modify-an-agent)
- [How to Add a New Agent](#how-to-add-a-new-agent)
- [Platform Configuration](#platform-configuration)
- [Pre-Commit Hooks](#pre-commit-hooks)
- [Running Tests](#running-tests)
- [Pull Request Guidelines](#pull-request-guidelines)

## Getting Started

1. Fork the repository
2. Clone your fork locally
3. Set up pre-commit hooks: `git config core.hooksPath .githooks`
4. Make your changes following the guidelines below
5. Submit a pull request

## Agent Template System

This project uses a **template-based generation system** to maintain agent definitions across multiple platforms (VS Code, Copilot CLI). This ensures consistency while allowing platform-specific customizations.

### Architecture Overview

```text
templates/
  agents/                    # Shared agent definitions (SOURCE OF TRUTH)
    analyst.shared.md
    implementer.shared.md
    orchestrator.shared.md
    ...
  platforms/                 # Platform-specific configurations
    vscode.yaml
    copilot-cli.yaml

src/
  vs-code-agents/           # GENERATED - Do not edit directly
    analyst.agent.md
    implementer.agent.md
    ...
  copilot-cli/              # GENERATED - Do not edit directly
    analyst.agent.md
    implementer.agent.md
    ...
```

### Key Concepts

| Component | Location | Purpose |
|-----------|----------|---------|
| Shared Templates | `templates/agents/*.shared.md` | Single source of truth for agent behavior |
| Platform Configs | `templates/platforms/*.yaml` | Platform-specific settings (model, tools, syntax) |
| Generated Files | `src/vs-code-agents/`, `src/copilot-cli/` | Output files used by each platform |

## How to Modify an Agent

To change an existing agent's behavior, follow these steps:

### Step 1: Edit the Shared Template

Edit the source file in `templates/agents/`:

```powershell
# Example: Modify the analyst agent
code templates/agents/analyst.shared.md
```

### Step 2: Regenerate Platform Files

Run the generation script:

```powershell
pwsh build/Generate-Agents.ps1
```

### Step 3: Verify the Changes

Check that generated files look correct:

```powershell
# Preview what would be generated without writing
pwsh build/Generate-Agents.ps1 -WhatIf

# Verify generated files match templates
pwsh build/Generate-Agents.ps1 -Validate
```

### Step 4: Commit Both Files

Always commit the template AND generated files together:

```bash
git add templates/agents/analyst.shared.md
git add src/vs-code-agents/analyst.agent.md
git add src/copilot-cli/analyst.agent.md
git commit -m "feat(analyst): add new research capability"
```

## How to Add a New Agent

### Step 1: Create the Shared Template

Create a new file in `templates/agents/` with the `.shared.md` extension:

```powershell
# Example: Create a new "reviewer" agent
code templates/agents/reviewer.shared.md
```

### Step 2: Define the Template Structure

Use this template structure (see existing agents in `templates/agents/` for examples):

**Required Frontmatter:**

```yaml
---
description: Brief description of the agent's purpose
tools_vscode: ['vscode', 'read', 'search', 'cloudmcp-manager/*']
tools_copilot: ['shell', 'read', 'edit', 'search', 'agent', 'cloudmcp-manager/*']
---
```

**Required Sections:**

- `# Agent Name` - The agent's display name
- `## Core Identity` - Role description
- `## Core Mission` - Primary objective
- `## Key Responsibilities` - Numbered list of responsibilities
- `## Constraints` - What the agent should NOT do
- `## Memory Protocol` - How to use cloudmcp-manager
- `## Output Format` - Expected outputs
- `## Handoff Protocol` - When/how to hand off to other agents

See `templates/agents/analyst.shared.md` for a complete example.

### Step 3: Configure Platform-Specific Tools

In the frontmatter, define tools for each platform:

- `tools_vscode`: Tools available in VS Code / GitHub Copilot
- `tools_copilot`: Tools available in Copilot CLI

Example:

```yaml
---
description: Code review specialist
tools_vscode: ['vscode', 'read', 'search', 'cloudmcp-manager/*', 'github/*']
tools_copilot: ['shell', 'read', 'edit', 'search', 'agent', 'cloudmcp-manager/*', 'github/*']
---
```

### Step 4: Generate and Verify

```powershell
# Generate all agents
pwsh build/Generate-Agents.ps1

# Verify outputs
pwsh build/Generate-Agents.ps1 -Validate
```

### Step 5: Update Documentation

Add the new agent to:

- `README.md` (Agents table)
- `CLAUDE.md` (Agent Catalog table)
- `USING-AGENTS.md` (if it exists)

## Platform Configuration

Platform configurations in `templates/platforms/` control how agents are transformed for each platform.

### VS Code Configuration (`vscode.yaml`)

```yaml
platform: vscode
outputDir: src/vs-code-agents
fileExtension: .agent.md

frontmatter:
  model: "Claude Opus 4.5 (anthropic)"
  includeNameField: false

handoffSyntax: "#runSubagent"
```

### Copilot CLI Configuration (`copilot-cli.yaml`)

```yaml
platform: copilot-cli
outputDir: src/copilot-cli
fileExtension: .agent.md

frontmatter:
  model: null
  includeNameField: true

handoffSyntax: "/agent"
```

### Key Differences Between Platforms

| Feature | VS Code | Copilot CLI |
|---------|---------|-------------|
| Model field | Required | Not used |
| Name field | Not used | Required |
| Handoff syntax | `#runSubagent` | `/agent` |
| Tools prefix | `tools_vscode` | `tools_copilot` |

## Important: Do Not Edit Generated Files

**Never edit files directly in:**

- `src/vs-code-agents/`
- `src/copilot-cli/`

These files are auto-generated and include a header comment:

```markdown
<!-- AUTO-GENERATED FILE - DO NOT EDIT DIRECTLY
     Generated from: templates/agents/[name].shared.md
     To modify this file, edit the source and run: pwsh build/Generate-Agents.ps1
-->
```

**CI will reject PRs** that modify generated files without corresponding template changes.

## Useful Commands

```powershell
# Generate all agent files from templates
pwsh build/Generate-Agents.ps1

# Verify generated files match templates (used in CI)
pwsh build/Generate-Agents.ps1 -Validate

# Preview what would be generated without writing files
pwsh build/Generate-Agents.ps1 -WhatIf

# Generate with verbose logging
pwsh build/Generate-Agents.ps1 -Verbose
```

## Pre-Commit Hooks

Enable markdown linting auto-fix on commits:

```bash
git config core.hooksPath .githooks
```

This automatically fixes markdown violations before each commit. See [docs/markdown-linting.md](docs/markdown-linting.md) for details.

## Running Tests

### PowerShell Tests (Pester)

```powershell
# Run all tests
pwsh build/scripts/Invoke-PesterTests.ps1

# CI mode (exits with error code on failure)
pwsh build/scripts/Invoke-PesterTests.ps1 -CI

# Run specific test file
pwsh build/scripts/Invoke-PesterTests.ps1 -TestPath "./scripts/tests/Install-Common.Tests.ps1"
```

### Agent Generation Tests

```powershell
# Run generation tests
pwsh build/scripts/Invoke-PesterTests.ps1 -TestPath "./build/tests/Generate-Agents.Tests.ps1"
```

## Pull Request Guidelines

1. **Spec references**: Feature PRs (`feat:`) require spec references (issue, REQ-*, or `.agents/planning/` files)
2. **Template changes**: Always include both template and generated files
3. **Validation**: Run `pwsh build/Generate-Agents.ps1 -Validate` before submitting
4. **Tests**: Ensure all tests pass
5. **Documentation**: Update relevant docs if adding new agents
6. **Commit messages**: Use conventional commit format (e.g., `feat(agent):`, `fix(template):`)

### Spec Reference Best Practices

For traceability and AI-assisted validation:

- **Features (`feat:`)**: Always link to an issue or create a planning document in `.agents/planning/` before submitting
- **Bug fixes (`fix:`)**: Link to issue if it exists; for complex bugs, explain root cause
- **Refactors (`refactor:`)**: Explain rationale and scope in PR description
- **Documentation (`docs:`)**: Spec references not required
- **Infrastructure (`ci:`, `build:`, `chore:`)**: Link to related infra/CI/tooling issue or spec; call out operational risk and rollback plan if applicable

Supported reference formats:

- Issue links: `Closes #123`, `Fixes #456`, `Implements #789`
- Requirement IDs: `REQ-001`, `DESIGN-002`, `TASK-003`
- Spec files: `.agents/specs/requirements/...`, `.agents/planning/...`

The AI Spec Validation workflow will check for these references on all PRs.

## Questions?

If you have questions about contributing, please open an issue or discussion.

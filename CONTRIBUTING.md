# Contributing to AI Agent System

Thank you for your interest in contributing to this project. This guide explains how to contribute effectively, with special attention to the agent template system.

## Table of Contents

- [Getting Started](#getting-started)
- [Git Configuration](#git-configuration)
- [Agent Template System](#agent-template-system)
- [How to Modify an Agent](#how-to-modify-an-agent)
- [How to Add a New Agent](#how-to-add-a-new-agent)
- [Platform Configuration](#platform-configuration)
- [Pre-Commit Hooks](#pre-commit-hooks)
- [Pre-Push Hooks](#pre-push-hooks)
- [Session Protocol](#session-protocol)
- [Running Tests](#running-tests)
- [Copilot CLI Version Management](#copilot-cli-version-management)
- [Pull Request Guidelines](#pull-request-guidelines)
  - [Commit Count Thresholds](#commit-count-thresholds)

## Getting Started

### Prerequisites

**Required Versions:**

- **Python 3.12.x** (primary scripting language per ADR-042; not 3.13.x due to CodeQL bug)
- **PowerShell 7.5.4+** (for existing scripts and cross-platform execution)
- **Pester 5.7.1** (exact version, pinned for supply chain security)
- **UV** (Python package manager, see [installation](https://docs.astral.sh/uv/getting-started/installation/))

**Python 3.12.x Required** (Not 3.13.x)

This project requires Python 3.12.x due to a known bug in Python 3.13.7 that breaks CodeQL analysis and skill validation. Ubuntu 25.10 users must use `pyenv` to install Python 3.12.8:

```bash
# Install pyenv (if not already installed)
curl https://pyenv.run | bash

# Add to your shell profile (~/.bashrc or ~/.zshrc)
cat >> ~/.bashrc <<'EOF'
export PYENV_ROOT="$HOME/.pyenv"
[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"
EOF

# Or for zsh users:
cat >> ~/.zshrc <<'EOF'
export PYENV_ROOT="$HOME/.pyenv"
[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"
EOF

# Reload shell
exec "$SHELL"

# Install Python 3.12.8
pyenv install 3.12.8

# Set for this project
cd /path/to/ai-agents
pyenv local 3.12.8

# Verify
python3 --version  # Should show Python 3.12.8
```

**See:** `.serena/memories/python-version-compatibility.md` for details on the Python 3.13.7 issue.

### Setup Steps

1. Fork the repository
2. Clone your fork locally
3. **Install Python 3.12.x** (see Prerequisites above)
4. **Set up Python environment**: `uv venv && uv pip install -e ".[dev]"`
5. Configure Git for cross-platform development (see [Git Configuration](#git-configuration) below)
6. Set up git hooks (pre-commit + pre-push): `git config core.hooksPath .githooks`
7. Make your changes following the guidelines below
8. Submit a pull request

**After setup, quality gates are automated.** Pre-commit hooks run ruff (Python) and markdownlint on staged files. Pre-push hooks run full test suites, drift detection, and security scans before each push. CI runs the complete validation suite. No manual test commands needed for routine development.

## Git Configuration

This repository enforces LF line endings for all files via `.gitattributes` to prevent cross-platform issues. To ensure smooth collaboration, configure your Git client based on your operating system:

### Windows

```bash
git config --global core.autocrlf true
```

**What this does:**

- **On checkout:** Git converts LF → CRLF for your text editors (Windows native)
- **On commit:** Git converts CRLF → LF for the repository
- **Result:** Repository always has LF, your editor always shows CRLF

### Linux/macOS

```bash
git config --global core.autocrlf input
```

**What this does:**

- **On checkout:** Git leaves LF as-is (Unix native)
- **On commit:** Git converts any CRLF → LF for the repository
- **Result:** Repository always has LF, your editor always shows LF

### Why This Matters

**Problem without proper configuration:**

- YAML frontmatter in agent files fails to parse with CRLF line endings
- GitHub Copilot CLI shows "Unexpected scalar at node end" errors
- Git diffs show entire files changed due to line ending differences
- Collaboration becomes difficult when contributors use different platforms

**Solution:**

- `.gitattributes` enforces LF in the repository (`* text=auto eol=lf`)
- `core.autocrlf` gives you native line endings in your working directory
- Together, they ensure consistency without sacrificing developer experience

**References:**

- [GitHub Copilot CLI Issue #694](https://github.com/github/copilot-cli/issues/694)
- [GitHub Copilot CLI Issue #673](https://github.com/github/copilot-cli/issues/673)
- [Issue #896](https://github.com/rjmurillo/ai-agents/issues/896)

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
argument-hint: Describe the input expected from the user
tools_vscode:
  - vscode
  - read
  - search
  - cloudmcp-manager/*
tools_copilot:
  - shell
  - read
  - edit
  - search
  - agent
  - cloudmcp-manager/*
---
```

> **Note:** Use block-style YAML arrays (hyphen-bulleted) for cross-platform compatibility. Inline array syntax `['tool1', 'tool2']` fails on GitHub Copilot CLI with CRLF line endings.

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
tools_vscode:
  - vscode
  - read
  - search
  - cloudmcp-manager/*
  - github/*
tools_copilot:
  - shell
  - read
  - edit
  - search
  - agent
  - cloudmcp-manager/*
  - github/*
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
  model: "Claude Opus 4.5 (copilot)"
  includeNameField: false

handoffSyntax: "#runSubagent"
```

### Copilot CLI Configuration (`copilot-cli.yaml`)

```yaml
platform: copilot-cli
outputDir: src/copilot-cli
fileExtension: .agent.md

frontmatter:
  # Copilot CLI model: use CLI model identifiers (not VS Code display names)
  model: "claude-opus-4.5"
  includeNameField: true

handoffSyntax: "/agent"
```

### Key Differences Between Platforms

| Feature | VS Code | Copilot CLI |
|---------|---------|-------------|
| Model field | `Claude Opus 4.5 (copilot)` | `claude-opus-4.5` |
| Name field | Not included | Required |
| Handoff syntax | `#runSubagent` | `/agent` |
| Tools prefix | `tools_vscode` | `tools_copilot` |
| `argument-hint` | Included | Included |

> **Note:** The Copilot CLI `model` frontmatter field is accepted but does not control runtime model selection on version 0.0.397. The `--model` CLI flag is required. See ADR-044 for details.

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

Enable automated validation on commits:

```bash
git config core.hooksPath .githooks
```

The pre-commit hook automatically runs checks including, depending on staged files:

- **markdownlint**: Fixes markdown violations before each commit. See [docs/markdown-linting.md](docs/markdown-linting.md) for details.
- **PSScriptAnalyzer**: Validates PowerShell (`.ps1`/`.psm1`) scripts for syntax errors and coding standard violations. Error-level issues block commits; warnings are displayed but non-blocking. Skips gracefully if PowerShell is not installed.
  - **Install**: `pwsh -Command 'Install-Module -Name PSScriptAnalyzer -Scope CurrentUser -Force'`
- **ruff**: Lints Python files for style and common issues when Python files are staged.
- **actionlint**: Validates GitHub Actions workflow files (`.github/workflows/*.yml`) when they are staged.
- **yamllint**: Validates general YAML files when they are staged.

Refer to `.githooks/pre-commit` for the authoritative, up-to-date list of all checks.

## Pre-Push Hooks

The pre-push hook runs comprehensive branch-wide validation before each push. Unlike the pre-commit hook (which checks staged files), the pre-push hook validates all changes in the push range.

**Checks run in order:**

| Phase | Checks | Blocking |
|-------|--------|----------|
| **Fast Guards** | Branch guard, commit count (max 20), changed files count, total additions | Yes |
| **Linting** | markdownlint, ruff, mypy, actionlint, yamllint | Yes (except yamllint) |
| **Build Validation** | Agent generation drift, agent drift detection, path normalization | Yes |
| **Tests** | Full Pester suite, pytest | Yes |
| **Security** | Suppression comment detection, session log validation | Yes |
| **Governance** | Planning artifacts, ADR review reminder | Warn only |

**Environment variables:**

| Variable | Default | Purpose |
|----------|---------|---------|
| `SKIP_PREPUSH` | 0 | Set to 1 to bypass all checks (emergency only) |
| `SKIP_TESTS` | 0 | Skip Pester and pytest (for documentation-only pushes) |

Refer to `.githooks/pre-push` for the authoritative, up-to-date list of all checks.

## Session Protocol

This project uses a session-based workflow for tracking work. Session logs are required for all significant work.

### Session Logs

Create session logs at `.agents/sessions/YYYY-MM-DD-session-NN.json` to document work done during a session.

### QA Validation

The pre-commit hook validates that QA has been performed for sessions involving code changes. There are two exemptions:

| Exemption Type | When to Use | Evidence Value |
|----------------|-------------|----------------|
| **Docs-only** | All changes are documentation files (Markdown) with no code, config, or test changes | `SKIPPED: docs-only` |
| **Investigation-only** | Session is research/analysis with only investigation artifacts staged | `SKIPPED: investigation-only` |

**Investigation artifacts** (allowlist for investigation-only exemption):

- `.agents/sessions/` - Session logs
- `.agents/analysis/` - Research findings
- `.agents/retrospective/` - Learning extractions
- `.serena/memories/` - AI memory updates
- `.agents/security/` - Security assessments

See [ADR-034](.agents/architecture/ADR-034-investigation-session-qa-exemption.md) for the full specification.

## Running Tests

### Automated Quality Gates (Shift Left)

The repository enforces quality automatically at multiple stages:

| Stage | What Runs | Trigger |
|-------|-----------|---------|
| **Pre-commit hook** | Python linting (ruff), Markdown linting | Every commit |
| **Pre-push hook** | Full Pester + pytest, drift detection, lint, security scans | Every push |
| **CI pytest.yml** | pytest, pip-audit, bandit | Every PR/push |
| **CI pester.yml** | Pester tests | Every PR/push |

**No manual test runs required for routine development.** Quality gates run automatically.

### Manual Testing (Optional)

For local debugging or development iteration:

```bash
# Python tests
uv run pytest                               # All tests
uv run pytest tests/test_example.py         # Specific file
uv run pytest --cov --cov-report=html       # With coverage

# Security scanning (also runs in CI)
uv run pip-audit                            # Dependency vulnerabilities
uv run bandit -r .claude/ scripts/          # Static analysis
```

### PowerShell Tests (Pester)

```powershell
# Run all tests
pwsh build/scripts/Invoke-PesterTests.ps1

# CI mode (exits with error code on failure)
pwsh build/scripts/Invoke-PesterTests.ps1 -CI

# Run specific test file
pwsh build/scripts/Invoke-PesterTests.ps1 -TestPath "./tests/Validate-SessionJson.Tests.ps1"
```

### Agent Generation Tests

```powershell
# Run generation tests
pwsh build/scripts/Invoke-PesterTests.ps1 -TestPath "./build/tests/Generate-Agents.Tests.ps1"
```

## Copilot CLI Version Management

The CI pipeline uses GitHub Copilot CLI to run agent reviews. The CLI version is pinned to prevent regressions from auto-updates.

### Current Pin

The CI action (`.github/actions/ai-review/action.yml`) pins `@github/copilot@0.0.397` with `--no-auto-update` on all invocations. This is documented in [ADR-044](.agents/architecture/ADR-044-copilot-cli-frontmatter-compatibility.md).

### Why Version Pinning

Copilot CLI's npm package contains a loader that delegates to a platform-specific binary. This binary auto-updates independently of the npm package version. npm version pinning alone is insufficient; the `--no-auto-update` flag prevents the binary from self-updating during CI runs.

### Validating Agent Frontmatter

After modifying agent templates or platform configs, validate agents load correctly:

```bash
# Check installed version
copilot --no-auto-update --version

# Test a single agent with debug logging (check for warnings)
copilot --no-auto-update --log-level all --agent analyst --prompt "Reply with only the word OK"

# Test all shared agents
for agent in analyst architect backlog-generator critic devops explainer high-level-advisor implementer independent-thinker memory milestone-planner orchestrator pr-comment-responder qa retrospective roadmap security skillbook task-decomposer; do
  copilot --no-auto-update --log-level all --agent "$agent" --prompt "Reply OK" 2>&1 | grep -i warning && echo "FAIL: $agent" || echo "PASS: $agent"
done
```

### Local Workflow Testing with gh act

Use `gh act` (nektos/gh-act) to simulate CI workflows locally:

```bash
# Install gh act extension (one time)
gh extension install nektos/gh-act

# Pull Docker image (one time, ~600MB)
docker pull catthehacker/ubuntu:act-latest

# Dry run (validate workflow structure)
gh act pull_request -n -W .github/workflows/ai-pr-quality-gate.yml

# Full run (single job)
TOKEN=$(gh auth token)
gh act pull_request \
  -j "analyst-review" \
  -W .github/workflows/ai-pr-quality-gate.yml \
  -s "GITHUB_TOKEN=$TOKEN" \
  -s "BOT_PAT=$TOKEN" \
  -P ubuntu-latest=catthehacker/ubuntu:act-latest
```

**Known limitation:** PowerShell composite action steps fail with "Exec format error" in `act`. This is a known `act` limitation, not a workflow bug. The Copilot CLI install and agent invocation steps run correctly.

### Upgrading the Copilot CLI Pin

When the upstream regression ([github/copilot-cli#1195](https://github.com/github/copilot-cli/issues/1195)) is fixed:

1. Install the new version locally: `npm install -g @github/copilot@X.Y.Z`
2. Run the agent validation loop above
3. Update the version in `.github/actions/ai-review/action.yml`
4. Run `gh act` dry-run to validate workflow structure
5. Update ADR-044 with the new version and test results

See `.serena/memories/copilot-cli-frontmatter-regression-runbook.md` for the full diagnostic runbook.

## Pull Request Guidelines

1. **Spec references**: Feature PRs (`feat:`) require spec references (issue, REQ-*, or `.agents/planning/` files)
2. **Template changes**: Always include both template and generated files
3. **Validation**: Run `pwsh build/Generate-Agents.ps1 -Validate` before submitting
4. **Tests**: Ensure all tests pass
5. **Documentation**: Update relevant docs if adding new agents
6. **Commit messages**: Use conventional commit format (e.g., `feat(agent):`, `fix(template):`)

### Commit Count Thresholds

PRs with many commits often indicate scope creep or should be split into smaller PRs. The repository enforces commit thresholds automatically:

| Commit Count | Action | Label Applied |
|--------------|--------|---------------|
| 10 commits | Warning notice in PR | `needs-split` |
| 15 commits | Alert warning in PR | `needs-split` |
| 20 commits | PR blocked from merge | `needs-split` |

#### What This Means

- **10 commits**: The workflow adds a notice. Consider whether the PR should be split.
- **15 commits**: The workflow adds an alert. Splitting is strongly recommended.
- **20 commits**: The workflow blocks the PR. You MUST either split the PR or add the `commit-limit-bypass` label.

#### Handling `needs-split` Labels

**For contributors**:

1. Review the commit history to identify logical groupings
2. Split into smaller, focused PRs where possible
3. If splitting is not practical, add a comment explaining why and request the `commit-limit-bypass` label

**For AI agents (pr-review, pr-comment-responder)**:

When encountering a PR with the `needs-split` label:

1. **Run a retrospective analysis**: Determine why the PR required so many commits
2. **Analyze commit history**: Group commits by logical change to identify potential split points
3. **Provide recommendations**: Suggest how the work could be divided into smaller PRs
4. **Document findings**: Save analysis to `.agents/retrospective/PR-[number]-needs-split-analysis.md` for future reference

#### Bypassing the Limit

To bypass the 20-commit block:

1. A human maintainer MUST add the `commit-limit-bypass` label
2. The bypass is visible in the PR labels and auditable
3. Use this sparingly for genuinely large, atomic changes that cannot be split

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

## Forgetful MCP Server

This project uses the [Forgetful MCP](https://github.com/ScottRBK/forgetful) server for AI agent memory. Forgetful provides semantic search, automatic knowledge graph construction, and cross-session memory persistence.

### Setup

Forgetful uses stdio transport with automatic installation via `uvx`. No manual service setup required.

**Configure MCP client** (`.mcp.json`):

```json
{
  "mcpServers": {
    "forgetful": {
      "type": "stdio",
      "command": "uvx",
      "args": [
        "forgetful-ai"
      ]
    }
  }
}
```

### Forgetful Installation Prerequisites

Install `uv` if not already present:

**Linux/macOS:**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows:**

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**Security Note**: Optional: verify installer integrity or use a package manager (e.g., brew/winget) when available.

### Verifying Connection

After configuration, verify the MCP connection in your client:

- **Claude Code**: Run `mcp__forgetful__discover_forgetful_tools()` to see available tools
- Check logs if issues occur (uvx manages the process lifecycle automatically)

### Importing Shared Memories

Import the project's shared Forgetful memories to get cross-session context:

```powershell
pwsh scripts/forgetful/Import-ForgetfulMemories.ps1
```

This imports all JSON exports from `.forgetful/exports/` into your local Forgetful database. The import is idempotent and safe to run multiple times.

**Note**: See `scripts/forgetful/README.md` for limitations on ID-based sync between divergent databases.

## Claude Router Plugin

This project supports the [Claude Router](https://github.com/0xrdan/claude-router) plugin for intelligent model routing and cost optimization.

### What is Claude Router?

Claude Router automatically directs queries to the most cost-effective Claude model (Haiku, Sonnet, or Opus) based on task complexity, reducing costs by up to 98% without sacrificing quality.

### How It Works

**Routing Logic:**

- **Fast (Haiku):** Simple queries, factual questions, syntax help
- **Standard (Sonnet):** Bug fixes, feature implementation, code review, refactoring
- **Deep (Opus):** Architecture decisions, security audits, multi-file refactors, system design

**Classification Mechanism:**

1. **Rule-Based (Primary):** Instant pattern matching (~0ms latency, no API costs)
2. **LLM Fallback (Secondary):** Uses Haiku for edge cases (~100ms latency, ~$0.001 per classification)

### Installation

**Option 1 - Plugin Marketplace (Recommended):**

```bash
# In any Claude Code session:
/plugin marketplace add 0xrdan/claude-router
/plugin install claude-router@claude-router-marketplace
```

Then restart Claude Code to load the plugin.

**Option 2 - One-Command Install:**

```bash
curl -sSL https://raw.githubusercontent.com/0xrdan/claude-router/main/install.sh | bash
```

**Option 3 - Manual Install:**

```bash
git clone https://github.com/0xrdan/claude-router.git
cd claude-router && ./install.sh
```

**Important:** Choose only one installation method to avoid conflicts.

### Configuration

**API Key (Required for LLM Fallback):**

Set your Anthropic API key as an environment variable:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

Or add to `.env` file.

**Routing Enforcement:**

The router enforcement rules are already configured in this project's `CLAUDE.md`. When Claude receives a routing directive, it will automatically spawn the appropriate executor subagent.

### Usage

**Automatic Routing (Default):**

Submit queries normally. The UserPromptSubmit hook automatically classifies and routes them.

**Manual Override:**

Force a specific model when needed:

```bash
/route fast <query>     # Use Haiku
/route standard <query> # Use Sonnet
/route deep <query>     # Use Opus
```

**View Statistics:**

```bash
/router-stats
```

Displays routing history and cost savings metrics.

### Notes

- The marketplace must be added per project (updates are automatic thereafter)
- Classification uses instant rule-matching when possible
- LLM fallback only triggers for uncertain cases
- Token overhead optimized to ~3.4k tokens per interaction
- Slash commands (`/route`, `/router-stats`) and router questions are handled directly, not routed

## Questions?

If you have questions about contributing, please open an issue or discussion.

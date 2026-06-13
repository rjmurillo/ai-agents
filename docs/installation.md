# Installation Guide

This guide covers native marketplace installation for the AI Agents system.

## Prerequisites

You need one of these AI coding tools:

- Claude Code CLI
- GitHub Copilot CLI
- VS Code with GitHub Copilot Chat
- Visual Studio 2022/2026 with GitHub Copilot Chat

For development work on this repository, see [CONTRIBUTING.md](../CONTRIBUTING.md#prerequisites) for Python, uv, and test setup.

## Fastest Start

Use the built-in marketplace support in the CLI you are actually running.

### Claude Code

Run this inside Claude Code:

```text
/install-plugin rjmurillo/ai-agents
```

That installs the full Claude toolkit from `.claude-plugin/marketplace.json`.

### GitHub Copilot CLI

Run this inside Copilot CLI:

```text
/plugin marketplace add rjmurillo/ai-agents
/plugin install project-toolkit@ai-agents
```

The same flow also works from a regular shell with the `copilot` prefix:

```bash
copilot plugin marketplace add rjmurillo/ai-agents
copilot plugin install project-toolkit@ai-agents
```

Copilot CLI resolves this repository through `.github/plugin/marketplace.json`.

### VS Code and Visual Studio

Repository-level agents work automatically when the repository contains `.github/agents/` and `.github/copilot-instructions.md`.

Usage examples in Copilot Chat:

```text
@orchestrator Help me implement a feature
@analyst Review this code for issues
```

## Component-Level Installation

If you want a partial install instead of the full toolkit, use the marketplace commands below.

### Claude Code

Register the marketplace once if you want explicit component installs instead of `/install-plugin`:

```text
/plugin marketplace add rjmurillo/ai-agents
```

| Component | Install Command | What You Get |
|-----------|----------------|--------------|
| Claude agents only | `/plugin install claude-agents@ai-agents` | 24 agent definitions from `src/claude/` |
| Project toolkit | `/plugin install project-toolkit@ai-agents` | 23 agents, 23 slash commands, 29 hooks, and 69 reusable skills from `.claude/` |

### GitHub Copilot CLI

Register the marketplace once:

```text
/plugin marketplace add rjmurillo/ai-agents
```

| Component | Install Command | What You Get |
|-----------|----------------|--------------|
| Copilot full toolkit | `/plugin install project-toolkit@ai-agents` | 24 agents, 28 hooks, 81 skills from `src/copilot-cli/` |

## Installation Paths

### Repository Installation Paths

| Platform | Agent Files | Instructions File |
|----------|-------------|-------------------|
| Claude Code | `.claude/agents/` | `CLAUDE.md` |
| Copilot CLI | `.github/agents/` | `.github/copilot-instructions.md` |
| VS Code | `.github/agents/` | `.github/copilot-instructions.md` |
| Visual Studio 2022/2026 | `.github/agents/` | `.github/copilot-instructions.md` |

### Visual Studio 2022/2026 Notes

Visual Studio 2022 (version 17.14+) and Visual Studio 2026 support GitHub Copilot agent mode using the same `.github/agents/*.agent.md` format as VS Code. Repository-level agents work automatically when you open a solution in a repository containing `.github/agents/`.

Requirements:

- Visual Studio 2022 version 17.14 or later, or Visual Studio 2026
- GitHub Copilot subscription
- "Enable project specific .NET instructions" feature enabled

## Skills

Claude skills ship as part of `project-toolkit`.

Skills live in `.claude/skills/` in the repository and install into Claude's runtime layout with the rest of the Claude toolkit. The `SKILL.md` file requires YAML frontmatter with `name`, `version`, and `description` fields, per `.agents/steering/claude-skills.md`.

Skill directory layout:

```text
.claude/skills/{skill-name}/
  SKILL.md       # Required: YAML frontmatter + prompt content
  scripts/       # Optional: Python or PowerShell automation
  tests/         # Optional: Unit and integration tests
  modules/       # Optional: PowerShell modules
```

To validate the repository copy of the skills structure:

```bash
python3 scripts/validate_skill_installation.py
python3 scripts/validate_skill_installation.py --verbose
```

### Optional skill packs

Some skills ship as optional packs: excluded from a default `ai-agents init` and
installed only on request with `--pack`.

```bash
npx ai-agents init --pack business
```

| Pack | Installs | Purpose |
|------|----------|---------|
| `business` | `business-strategy` | Customer discovery, positioning, pricing, sales, and growth frameworks |

`--pack` is repeatable and accepts comma-separated values (`--pack business` or
`--pack a,b`). An unknown pack name fails with the list of available packs.

## Uninstallation

Use your tool's native uninstall support.

### Claude Code

```text
/plugin uninstall claude-agents@ai-agents
/plugin uninstall project-toolkit@ai-agents
```

### GitHub Copilot CLI

```text
/plugin uninstall project-toolkit@ai-agents
```

## Troubleshooting

### Claude Code

- Restart Claude Code after install so the new agents, hooks, commands, and skills load.
- If `/install-plugin` is not recognized, update Claude Code to a build that supports plugin marketplaces.

### GitHub Copilot CLI

- If `/plugin` is not recognized, update Copilot CLI to a recent stable release.
- If install fails with "No plugin.json found in repository", add the marketplace first with `/plugin marketplace add rjmurillo/ai-agents`.
- No restart is needed after Copilot installation.

### VS Code / Visual Studio

- Restart the IDE or reload the window if newly added repository agents do not appear.
- Repository-level agent loading is the supported path described in `.github/copilot-instructions.md`.

### Verify Installation

Claude Code:

```text
Task(subagent_type="analyst", prompt="Hello, are you available?")
```

VS Code / Visual Studio:

```text
@orchestrator Hello, are you available?
```

Copilot CLI:

```bash
copilot plugin list
copilot --agent analyst --prompt "Hello, are you available?"
```

The Copilot plugin list should include whichever package you installed, such as `project-toolkit@ai-agents`.

### Security Scanning (Recommended for contributors)

For local security scanning before push, install semgrep:

```bash
python3 scripts/install_semgrep.py
```

Or install manually:

```bash
pip install semgrep
```

Semgrep runs automatically in the pre-push hook and scans Python, PowerShell, JavaScript, and YAML files for security issues. It blocks push on HIGH/CRITICAL findings.

### Worktrunk Setup (Optional)

For parallel agent workflows using git worktrees, install Worktrunk:

Homebrew:

```bash
brew install max-sixty/worktrunk/wt && wt config shell install
```

Cargo:

```bash
cargo install worktrunk && wt config shell install
```

Claude Code plugin:

```bash
claude plugin marketplace add max-sixty/worktrunk
claude plugin install worktrunk@worktrunk
```

The repository includes `.config/wt.toml` with lifecycle hooks that configure git hooks automatically on worktree creation, copy dependencies from the main worktree, and run markdown linting before merge.

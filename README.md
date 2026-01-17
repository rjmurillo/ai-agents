# AI Agent System

A coordinated multi-agent system for software development, available for **VS Code (GitHub Copilot)**, **GitHub Copilot CLI**, and **Claude Code CLI**.

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/rjmurillo/ai-agents)
![CodeRabbit Pull Request Reviews](https://img.shields.io/coderabbit/prs/github/rjmurillo/ai-agents?utm_source=oss&utm_medium=github&utm_campaign=rjmurillo%2Fai-agents&labelColor=171717&color=FF570A&link=https%3A%2F%2Fcoderabbit.ai&label=CodeRabbit+Reviews)

## Features

- **17 specialized agents** for different development phases
- **Explicit handoff protocols** between agents
- **Multi-Agent Impact Analysis Framework** for comprehensive planning
- **Cross-session memory** using cloudmcp-manager
- **Self-improvement system** with skill tracking and retrospectives
- **TUI-based installation** via [skill-installer](https://github.com/rjmurillo/skill-installer)

## Quick Start

### Prerequisites

- Python 3.10+
- [UV](https://docs.astral.sh/uv/) package manager

Install UV:

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### Installation (Recommended)

Use skill-installer to install agents:

```bash
# Try without installing
uvx --from git+https://github.com/rjmurillo/skill-installer skill-installer interactive

# Or install globally
uv tool install git+https://github.com/rjmurillo/skill-installer
skill-installer source add rjmurillo/ai-agents
skill-installer interactive
```

Navigate the TUI to select and install agents for your platform.

### CLI Installation (Non-Interactive)

```bash
skill-installer install claude-agents --platform claude
skill-installer install copilot-cli-agents --platform copilot
skill-installer install vscode-agents --platform vscode
```

**Note**: Copilot CLI global installation has a [known issue](https://github.com/github/copilot-cli/issues/452). Use repository installation instead.

### Usage Examples

```bash
# Claude Code
Task(subagent_type="analyst", prompt="investigate issue X")

# VS Code
@orchestrator Help me implement a new feature

# Copilot CLI
copilot --agent analyst --prompt "investigate issue X"
```

See [docs/installation.md](docs/installation.md) for complete installation documentation.

## Directory Structure

```text
src/
├── vs-code-agents/      # VS Code / GitHub Copilot agents
├── copilot-cli/         # GitHub Copilot CLI agents
└── claude/              # Claude Code CLI agents
scripts/                 # Installation scripts
copilot-instructions.md  # GitHub Copilot instructions
CLAUDE.md                # Claude Code instructions
USING-AGENTS.md          # Detailed usage guide
```

## Agents

| Agent | Purpose |
|-------|---------|
| orchestrator | Task coordination and routing |
| analyst | Pre-implementation research |
| architect | Design governance and ADRs |
| planner | Milestones and work packages |
| implementer | Production code and tests |
| critic | Plan validation |
| qa | Test strategy and verification |
| retrospective | Learning extraction |
| memory | Cross-session context |
| skillbook | Skill management |
| + 7 more... | See [USING-AGENTS.md](USING-AGENTS.md) |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed contribution guidelines.

1. Fork and clone the repository
2. Enable pre-commit hooks: `git config core.hooksPath .githooks`
3. Make changes following the guidelines
4. Submit a pull request

### Agent Development

This project uses a **template-based generation system**. To modify agents:

1. Edit templates in `templates/agents/*.shared.md`
2. Run `pwsh build/Generate-Agents.ps1` to regenerate
3. Commit both template and generated files

**Do not edit files in `src/vs-code-agents/` or `src/copilot-cli/` directly.** See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## Documentation

- [CONTRIBUTING.md](CONTRIBUTING.md) - Contribution guidelines and agent development
- [docs/installation.md](docs/installation.md) - Complete installation guide
- [USING-AGENTS.md](USING-AGENTS.md) - Comprehensive usage guide
- [copilot-instructions.md](copilot-instructions.md) - GitHub Copilot integration
- [CLAUDE.md](CLAUDE.md) - Claude Code integration
- [docs/ideation-workflow.md](docs/ideation-workflow.md) - Ideation workflow documentation
- [docs/markdown-linting.md](docs/markdown-linting.md) - Markdown standards

## License

MIT

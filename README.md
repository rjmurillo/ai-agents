# AI Agent System

> A coordinated multi-agent framework for AI-powered software development workflows.

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/rjmurillo/ai-agents)
![CodeRabbit Pull Request Reviews](https://img.shields.io/coderabbit/prs/github/rjmurillo/ai-agents?utm_source=oss&utm_medium=github&utm_campaign=rjmurillo%2Fai-agents&labelColor=171717&color=FF570A&link=https%3A%2F%2Fcoderabbit.ai&label=CodeRabbit+Reviews)

![AI Issue Triage](https://github.com/rjmurillo/ai-agents/actions/workflows/ai-issue-triage.yml/badge.svg)
![AI PR Quality Gate](https://github.com/rjmurillo/ai-agents/actions/workflows/ai-pr-quality-gate.yml/badge.svg)
![Spec-to-Implementation Validation](https://github.com/rjmurillo/ai-agents/actions/workflows/ai-spec-validation.yml/badge.svg)
![Pester Tests](https://github.com/rjmurillo/ai-agents/actions/workflows/pester-tests.yml/badge.svg)
![CodeQL Analysis](https://github.com/rjmurillo/ai-agents/actions/workflows/codeql-analysis.yml/badge.svg)

---

## Table of Contents

- [Purpose and Scope](#purpose-and-scope)
  - [What is AI Agents?](#what-is-ai-agents)
  - [Core Capabilities](#core-capabilities)
- [Installation](#installation)
  - [Supported Platforms](#supported-platforms)
  - [Prerequisites](#prerequisites)
  - [Install via skill-installer](#install-via-skill-installer)
- [Quick Start](#quick-start)
- [System Architecture](#system-architecture)
  - [Agent Catalog](#agent-catalog)
  - [Directory Structure](#directory-structure)
- [Contributing](#contributing)
- [Documentation](#documentation)
- [License](#license)

---

## Purpose and Scope

### What is AI Agents?

AI Agents is a coordinated multi-agent system for software development. It provides specialized AI agents that handle different phases of the development lifecycle, from research and planning through implementation and quality assurance.

The system is designed around explicit handoff protocols between agents, ensuring clear accountability and traceability across complex tasks.

### Core Capabilities

- **17 specialized agents** for different development phases (analysis, architecture, implementation, QA, etc.)
- **Explicit handoff protocols** between agents with clear accountability
- **Multi-Agent Impact Analysis Framework** for comprehensive planning
- **Cross-session memory** using cloudmcp-manager for persistent context
- **Self-improvement system** with skill tracking and retrospectives
- **TUI-based installation** via [skill-installer](https://github.com/rjmurillo/skill-installer)
- **AI-powered CI/CD** with issue triage, PR quality gates, and spec validation

---

## Installation

### Supported Platforms

| Platform | Agent Location | Notes |
|----------|---------------|-------|
| **VS Code / GitHub Copilot** | `src/vs-code-agents/` | Use `@agent` syntax in Copilot Chat |
| **GitHub Copilot CLI** | `src/copilot-cli/` | Use `--agent` flag |
| **Claude Code CLI** | `src/claude/` | Use `Task(subagent_type="...")` |

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

### Install via skill-installer

Use [skill-installer](https://github.com/rjmurillo/skill-installer) to install agents:

```bash
# Try without installing (one-liner)
uvx --from git+https://github.com/rjmurillo/skill-installer skill-installer interactive

# Or install globally for repeated use
uv tool install git+https://github.com/rjmurillo/skill-installer
skill-installer source add rjmurillo/ai-agents
skill-installer interactive
```

Navigate the TUI to select and install agents for your platform.

**CLI Installation (Non-Interactive):**

```bash
skill-installer install claude-agents --platform claude
skill-installer install copilot-cli-agents --platform copilot
skill-installer install vscode-agents --platform vscode
```

See [docs/installation.md](docs/installation.md) for complete installation documentation.

---

## Quick Start

### Claude Code

```python
Task(subagent_type="analyst", prompt="investigate issue X")
Task(subagent_type="implementer", prompt="implement feature Y")
Task(subagent_type="orchestrator", prompt="coordinate multi-step task Z")
```

### VS Code / GitHub Copilot

```text
@orchestrator Help me implement a new feature
@analyst Investigate why tests are failing
@implementer Fix the bug in UserService.cs
```

### GitHub Copilot CLI

```bash
copilot --agent analyst --prompt "investigate issue X"
copilot --agent implementer --prompt "fix the bug"
```

**Note**: Copilot CLI global installation has a [known issue](https://github.com/github/copilot-cli/issues/452). Use repository installation instead.

---

## System Architecture

### Agent Catalog

| Agent | Purpose |
|-------|---------|
| **orchestrator** | Task coordination and routing |
| **analyst** | Pre-implementation research |
| **architect** | Design governance and ADRs |
| **planner** | Milestones and work packages |
| **implementer** | Production code and tests |
| **critic** | Plan validation |
| **qa** | Test strategy and verification |
| **security** | Vulnerability assessment |
| **devops** | CI/CD pipelines |
| **retrospective** | Learning extraction |
| **memory** | Cross-session context |
| **skillbook** | Skill management |
| **explainer** | PRDs and documentation |
| **task-generator** | Atomic task breakdown |
| **high-level-advisor** | Strategic decisions |
| **independent-thinker** | Challenge assumptions |
| **pr-comment-responder** | PR review handling |

See [USING-AGENTS.md](USING-AGENTS.md) for detailed agent documentation.

### Directory Structure

```text
ai-agents/
├── src/
│   ├── vs-code-agents/      # VS Code / GitHub Copilot agents
│   ├── copilot-cli/         # GitHub Copilot CLI agents
│   └── claude/              # Claude Code CLI agents
├── templates/               # Agent template system
├── scripts/                 # Validation and utility scripts
├── docs/                    # Documentation
├── .agents/                 # Agent artifacts (ADRs, plans, etc.)
├── .claude-plugin/          # skill-installer manifest
├── copilot-instructions.md  # GitHub Copilot instructions
├── CLAUDE.md                # Claude Code instructions
└── USING-AGENTS.md          # Detailed usage guide
```

---

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

---

## Documentation

| Document | Description |
|----------|-------------|
| [CONTRIBUTING.md](CONTRIBUTING.md) | Contribution guidelines and agent development |
| [docs/installation.md](docs/installation.md) | Complete installation guide |
| [USING-AGENTS.md](USING-AGENTS.md) | Comprehensive usage guide |
| [copilot-instructions.md](copilot-instructions.md) | GitHub Copilot integration |
| [CLAUDE.md](CLAUDE.md) | Claude Code integration |
| [docs/ideation-workflow.md](docs/ideation-workflow.md) | Ideation workflow documentation |
| [docs/markdown-linting.md](docs/markdown-linting.md) | Markdown standards |

---

## License

MIT

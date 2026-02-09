# AI Agent System

> A coordinated multi-agent framework for AI-powered software development workflows.

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/rjmurillo/ai-agents)

![GitHub commits since latest release](https://img.shields.io/github/commits-since/rjmurillo/ai-agents/latest)
![GitHub commit activity](https://img.shields.io/github/commit-activity/w/rjmurillo/ai-agents)
![CodeRabbit Pull Request Reviews](https://img.shields.io/coderabbit/prs/github/rjmurillo/ai-agents)

![AI Issue Triage](https://github.com/rjmurillo/ai-agents/actions/workflows/ai-issue-triage.yml/badge.svg)
![AI PR Quality Gate](https://github.com/rjmurillo/ai-agents/actions/workflows/ai-pr-quality-gate.yml/badge.svg)
![Spec-to-Implementation Validation](https://github.com/rjmurillo/ai-agents/actions/workflows/ai-spec-validation.yml/badge.svg)
![Pester Tests](https://github.com/rjmurillo/ai-agents/actions/workflows/pester-tests.yml/badge.svg)
![CodeQL Analysis](https://github.com/rjmurillo/ai-agents/actions/workflows/codeql-analysis.yml/badge.svg)

---

## Table of Contents

- [AI Agent System](#ai-agent-system)
  - [Table of Contents](#table-of-contents)
  - [Purpose and Scope](#purpose-and-scope)
    - [What is AI Agents?](#what-is-ai-agents)
    - [Core Capabilities](#core-capabilities)
  - [Installation](#installation)
    - [Supported Platforms](#supported-platforms)
    - [Install via skill-installer](#install-via-skill-installer)
      - [Prerequisites](#prerequisites)
  - [Quick Start](#quick-start)
    - [Examples](#examples)
      - [Simple Scenarios](#simple-scenarios)
      - [Advanced Scenarios](#advanced-scenarios)
  - [System Architecture](#system-architecture)
    - [Agent Catalog](#agent-catalog)
    - [Directory Structure](#directory-structure)
  - [Contributing](#contributing)
    - [Agent Development](#agent-development)
  - [Documentation](#documentation)
  - [License](#license)

---

## Purpose and Scope

### What is AI Agents?

AI Agents is a coordinated multi-agent system for software development. It provides specialized AI agents that handle different phases of the development lifecycle, from research and planning through implementation and quality assurance.

The orchestrator is the hub of operations. Within it has logic from taking everything from a "vibe" or a "shower thought" and building out a fully functional spec with acceptance criteria and user stories, to taking a well defined idea as input and executing on it. There are 21 agents that cover the roles of software development, from vision and strategy, to architecture, implementation, and verification. Each role looks at something specific, like the critic that just looks to poke holes in other agents' (or your own) work, or DevOps that's concerned about how you deploy and operate the thing you just built.

The agents themselves use the platform specific handoffs to invoke subagents, keeping the orchestrator context clean. A great example of this is orchestrator facilitating creating and debating an [Architectural Decision Record](https://adr.github.io/) from research and drafting, to discussion, iterating on the issues, tie breaking when agents don't agree. And then  extracting persistent knowledge to steer future agents to adhere. Artifacts are stored in your memory system if you have one enabled, and Markdown files for easy reference to both agents and humans.

### Core Capabilities

- **21 specialized agents** for different development phases (analysis, architecture, implementation, QA, etc.)
- **Explicit handoff protocols** between agents with clear accountability
- **Multi-Agent Impact Analysis Framework** for comprehensive planning
- **Cross-session memory** with citation verification, graph traversal, and health reporting via Serena + Forgetful
- **Self-improvement system** with skill tracking and retrospectives
- **Quality gates** with pre-PR validation, session protocol enforcement, and automated CI checks
- **50+ reusable skills** for common development workflows (git, PR management, testing, linting)
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

### Install via skill-installer

#### Prerequisites

- Python 3.10+
- [UV](https://docs.astral.sh/uv/) package manager

Install UV:

macOS/Linux

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Windows (PowerShell)

```powershell
pwsh -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Use [skill-installer](https://github.com/rjmurillo/skill-installer) to install agents:

Without installing (one-liner)

```bash
# Latest version
uvx --from git+https://github.com/rjmurillo/skill-installer skill-installer interactive

# Specific version (e.g., v0.3.0)
uvx --from git+https://github.com/rjmurillo/skill-installer@v0.3.0 skill-installer interactive
```

Or install globally for repeated use

```bash
# Latest version
uv tool install git+https://github.com/rjmurillo/skill-installer

# Specific version (e.g., v0.1.0 or v0.2.0 or v0.3.0)
uv tool install git+https://github.com/rjmurillo/skill-installer@v0.1.0

# Run the interactive installer
skill-installer interactive
```

Navigate the TUI to select and install agents for your platform.

See [docs/installation.md](docs/installation.md) for complete installation documentation.

---

## Quick Start

After installing the agents with the method of your choice, you can either select one of them explicitly, ask your LLM to use the agent by name, or even prefix your input with the name of the agent.

### Examples

Here are prompts you can copy and paste. Prefix with the agent name to route directly, or use the orchestrator for multi-step workflows.

#### Simple Scenarios

Review code quality:

> critic: review @src/auth/login-handler.ts for coupling, error handling gaps, and test coverage. Deliver an APPROVE or REJECT verdict with specific line references.

Shows the critic agent doing a focused code review.

Investigate a bug:

> analyst: the /api/users endpoint returns 500 when the email contains a plus sign. Trace the request through the handler, identify the root cause, and propose a fix.

Shows the analyst doing root cause analysis on a specific bug.

Scan for vulnerabilities:

> security: scan @src/api/ for OWASP Top 10 vulnerabilities. Focus on injection, broken auth, and data exposure. Output a threat matrix with CWE identifiers and severity ratings.

Shows the security agent doing a targeted scan.

Write tests for existing code:

> qa: write pytest tests for @scripts/validate_session_json.py. Cover happy path, malformed input, missing required fields, and boundary conditions. Target 95% line coverage.

Shows the QA agent generating tests with specific coverage targets.

Document a module:

> explainer: document @scripts/memory_enhancement/ as a user guide. Include purpose, installation, CLI usage with examples, and architecture overview. Write for developers who have never seen this codebase.

Shows the explainer creating developer documentation.

Plan a feature:

> milestone-planner: break down "add webhook retry with exponential backoff" into milestones. Include acceptance criteria, estimated complexity, dependencies, and a suggested implementation order.

Shows the planner creating structured work packages.

#### Advanced Scenarios

End-to-end feature pipeline:

> orchestrator: build the webhook retry system described in @.agents/specs/webhook-retry.md. Start with analyst to verify requirements. Then milestone-planner to create work packages. Run critic to stress-test the plan. Then implementer to write code and tests. Run qa to verify coverage meets acceptance criteria. Run security to scan for injection and replay risks. Fix all critical findings recursively until critic, qa, and security pass. Open a PR.

The orchestrator chains seven agents into a full development pipeline with quality gates at each stage.

Architecture review:

> orchestrator: conduct a full review of @docs/architecture/service-mesh.md. Route through analyst for data accuracy, architect for structural decisions, security for threat modeling with CWE/CVSS ratings, critic to stress-test for gaps, and independent-thinker to challenge assumptions. Synthesize all findings into a single summary highlighting consensus and disagreements.

Five agents examine the same artifact through different lenses. The orchestrator synthesizes their independent assessments.

Debug, fix, and ship:

> orchestrator: the payment webhook handler drops events when Redis is unavailable. Have analyst investigate the failure pattern in the logs. Then architect propose a resilient design with fallback queuing. Then implementer build the fix with tests. Run qa and security to validate. Open a PR when all checks pass.

Turns an incident report into a shipped fix through structured agent collaboration.

Technology migration evaluation:

> orchestrator: we are considering migrating from REST to gRPC for internal services. Route through analyst to research benchmarks and ecosystem maturity. Then architect to map impact on existing contracts. Then security to threat-model the new transport layer. Then devops to estimate CI/CD changes. Then independent-thinker to argue the strongest case for staying with REST. Then high-level-advisor to deliver a GO or NO-GO verdict with conditions.

Six agents build a decision package. Each contributes a different dimension of analysis. The advisor synthesizes everything into an actionable verdict.

Strategic prioritization:

> orchestrator: we have three candidate features for next quarter: plugin marketplace, offline mode, and admin audit logging. For each, run analyst for effort and risk, roadmap to score with RICE and KANO, security for compliance implications, and devops for operational burden. Then independent-thinker to argue which one we will most regret skipping. Then high-level-advisor to rank all three with a clear recommendation.

The orchestrator runs the same evaluation pipeline across all candidates, producing comparable data for a defensible quarterly plan.

---

## System Architecture

### Agent Catalog

| Agent | Purpose | Output |
|-------|---------|--------|
| **orchestrator** | Task coordination and routing | Delegated results from specialists |
| **analyst** | Research, feasibility analysis, trade-off evaluation | Quantitative findings with evidence |
| **architect** | System design evaluation, ADRs, pattern enforcement | Rated assessments (Strong/Adequate/Needs-Work) |
| **milestone-planner** | Milestones and work packages | Implementation plans with acceptance criteria |
| **implementer** | Production code and tests | Code, tests, commits |
| **critic** | Plan stress-testing, gap identification | Verdicts: APPROVE / APPROVE WITH CONDITIONS / REJECT |
| **qa** | Test strategy and verification | Test reports, coverage analysis |
| **security** | Threat modeling, vulnerability assessment | Threat matrices with CWE/CVSS ratings |
| **devops** | CI/CD pipelines, operational planning | Infrastructure configs, maintenance estimates |
| **roadmap** | Strategic prioritization, RICE/KANO analysis | Priority stacks, cost-benefit analysis |
| **retrospective** | Learning extraction | Actionable insights, skill updates |
| **memory** | Cross-session context | Retrieved knowledge, stored observations |
| **skillbook** | Skill management | Atomic strategy updates |
| **explainer** | PRDs and documentation | Specs, user guides |
| **task-decomposer** | Atomic task breakdown | Estimable work items with done criteria |
| **backlog-generator** | Proactive task discovery | Sized tasks from project state analysis |
| **high-level-advisor** | Strategic decisions, unblocking | Verdicts: GO / CONDITIONAL GO / NO-GO |
| **independent-thinker** | Challenge assumptions, devil's advocate | Counter-arguments with alternatives |
| **pr-comment-responder** | PR review handling | Triaged responses, resolution tracking |
| **spec-generator** | Requirement specifications, EARS format | Structured specs with acceptance criteria |
| **debug** | Debugging assistance, root cause analysis | Diagnostic findings with resolution steps |

See [AGENTS.md](AGENTS.md) for detailed agent documentation.

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
├── .github/copilot-instructions.md  # GitHub Copilot instructions
├── CLAUDE.md                        # Claude Code instructions
└── AGENTS.md                        # Detailed usage guide
```

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed contribution guidelines.

### Developer Setup

If you're contributing code or running tests locally:

1. Fork and clone the repository
2. Install Python dependencies:

   ```bash
   # Create virtual environment (optional but recommended)
   uv venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate

   # Install project with dev dependencies
   uv pip install -e ".[dev]"
   ```

3. Set up environment variables (copy `.env.example` to `.env` and fill in your API keys)
4. Enable pre-commit hooks: `git config core.hooksPath .githooks`
5. Run tests to verify setup:

   ```bash
   # Python tests
   python -m pytest tests/ -v

   # PowerShell tests
   pwsh -Command "Invoke-Pester tests/ -Output Detailed"
   ```

6. Make changes following the guidelines
7. Submit a pull request

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
| [AGENTS.md](AGENTS.md) | Comprehensive usage guide |
| [copilot-instructions.md](.github/copilot-instructions.md) | GitHub Copilot integration |
| [CLAUDE.md](CLAUDE.md) | Claude Code integration |
| [docs/ideation-workflow.md](docs/ideation-workflow.md) | Ideation workflow documentation |
| [docs/markdown-linting.md](docs/markdown-linting.md) | Markdown standards |

---

## License

MIT

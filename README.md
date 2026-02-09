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
      - [Multi-Step Coordination Pattern](#multi-step-coordination-pattern)
      - [Recursive Fix Loop Pattern](#recursive-fix-loop-pattern)
      - [Implementation with Validation Gate](#implementation-with-validation-gate)
      - [PR Coordination Workflow](#pr-coordination-workflow)
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

The orchestrator is the hub of operations. Within it has logic from taking everything from a "vibe" or a "shower thought" and building out a fully functional spec with acceptance criteria and user stories, to taking a well defined idea as input and executing on it. There are 17 agents that cover the roles of software development, from vision and strategy, to architecture, implementation, and verification. Each role looks at something specific, like the critic that just looks to poke holes in other agents' (or your own) work, or DevOps that's concerned about how you deploy and operate the thing you just built.

The agents themselves use the platform specific handoffs to invoke subagents, keeping the orchestrator context clean. A great example of this is orchestrator facilitating creating and debating an [Architectural Decision Record](https://adr.github.io/) from research and drafting, to discussion, iterating on the issues, tie breaking when agents don't agree. And then  extracting persistent knowledge to steer future agents to adhere. Artifacts are stored in your memory system if you have one enabled, and Markdown files for easy reference to both agents and humans.

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

# Specific version (e.g., v0.2.0)
uvx --from git+https://github.com/rjmurillo/skill-installer@v0.2.0 skill-installer interactive
```

Or install globally for repeated use

```bash
# Latest version
uv tool install git+https://github.com/rjmurillo/skill-installer

# Specific version (e.g., v0.1.0 or v0.2.0)
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

#### Multi-Step Coordination Pattern

> orchestrator: merge your branch with main, then find other items that are in non-compliance with @path/to/historical-reference-protocol.md and create a plan to correct each. Store the plan in @path/to/plans/historical-reference-protocol-remediation.md and validate with critic, correcting all identified issues. After the plan is completed, start implementor to execute the plan and use critic, qa, and security to review the results, correcting all critical and major issues recursively. After the work is completed and verified, open a PR.

This demonstrates the orchestrator's strengths in chaining operations together and routing between agents.

#### Recursive Fix Loop Pattern

> orchestrator: fix all items identified by the critic agent, then repeat the cycle recursively until no items are found.

This keeps agents honest. Agents will try to be _helpful_ by declaring they're done sooner, skipping steps, or not reading all documentation. Having another agent validate work product makes the system stronger. A typical flow:

1. Do work
2. Validate that work against a spec (issue, plan, design, test, documentation)
3. Send to another agent (QA)
4. Repeat on down the line

Chain different workflows together as subagents to keep orchestration context alive longer. If you develop software, you probably have some form of "write code, make it work, refactor" cycle. Orchestrator is great at that.

#### Implementation with Validation Gate

> orchestrator: implement Task E2 session validation and E4 pre-commit memory evidence checks. Run the QA agent to verify the implementation meets the PRD acceptance criteria.

#### PR Coordination Workflow

> orchestrator: review the PR comments, address each reviewer's feedback, then run the code-reviewer agent to verify fixes before requesting re-review

#### Direct Agent Invocation

You do not need the orchestrator for focused tasks. Invoke any agent directly by name:

```text
analyst: assess the feasibility of the v0.4.0 extraction plan. Verify the
inventory data, calibrate session estimates against historical velocity, and
identify the top 3 dependency risks with quantitative evidence.
```

```text
security: produce a threat matrix for the plugin security model in
@.agents/projects/v0.4.0/PLAN.md. Include CWE identifiers, CVSS ratings,
and specific mitigation recommendations for each threat.
```

```text
critic: review the implementation plan at @.agents/planning/feature-plan.md.
Stress-test for gaps, missing rollback strategy, and integration testing
coverage. Deliver an APPROVE / APPROVE WITH CONDITIONS / REJECT verdict.
```

```text
roadmap: evaluate whether feature X aligns with the product roadmap. Score
it using RICE framework and compare opportunity cost against the current backlog.
```

```text
high-level-advisor: we are stuck between approach A and approach B. Cut through
the analysis and give a GO / NO-GO verdict with clear conditions.
```

```text
independent-thinker: challenge the core assumptions of the framework extraction
proposal. Present the strongest case against it with at least 3 concrete
alternatives.
```

Direct invocation is best when you know which expertise you need. Use orchestrator when the task requires routing between multiple agents or when you are unsure which agent to start with.

#### Multi-Agent Deep Dive

Route a single artifact through every relevant agent to build a complete picture before committing to a direction:

> orchestrator: conduct a full review of @.agents/projects/v0.4.0/PLAN.md. Route it through analyst to verify data accuracy and calibrate estimates, architect to evaluate structural decisions and coupling, security to produce a threat matrix with CWE/CVSS ratings, critic to stress-test for gaps and deliver a verdict, independent-thinker to challenge assumptions and propose alternatives, roadmap to score strategic alignment using RICE, devops to assess operational and CI/CD implications, and high-level-advisor to deliver a go/no-go recommendation. Synthesize all findings into a single summary with consensus areas and open disagreements.

The orchestrator delegates to each agent in turn, collecting independent assessments of the same artifact. Each agent analyzes through its own lens: security looks for threats, critic looks for gaps, independent-thinker looks for blind spots. The orchestrator synthesizes findings into a unified view that highlights where agents agree and where they diverge. This pattern is especially useful for architectural decisions, milestone plans, and pre-implementation due diligence.

#### Due Diligence Before a Major Decision

Before adopting a new framework, migrating a system, or making an irreversible architectural change, run structured due diligence across multiple dimensions:

> orchestrator: we are considering migrating from REST to gRPC for our internal service mesh. Route this through analyst to research performance benchmarks, ecosystem maturity, and team skill gaps. Then architect to evaluate the impact on our current @docs/architecture/service-contracts.md contracts and propose a migration boundary. Then security to threat-model the new transport layer. Then devops to estimate CI/CD pipeline changes and rollback complexity. Then independent-thinker to argue the strongest case for staying with REST. Then high-level-advisor to deliver a GO / CONDITIONAL GO / NO-GO verdict with specific conditions. Store the consolidated analysis in @.agents/analysis/grpc-migration-due-diligence.md.

The orchestrator builds a decision package by routing through six agents. Analyst provides the quantitative foundation. Architect maps the blast radius. Security identifies new attack surface. DevOps estimates operational cost. Independent-thinker forces the team to confront the best argument against the change. High-level-advisor synthesizes everything into an actionable verdict. The stored artifact becomes a reference for the team and future agents.

#### End-to-End Feature Pipeline

Take a feature from zero to pull request with built-in quality gates at each stage:

> orchestrator: build the webhook retry system described in @.agents/specs/requirements/webhook-retry.md. Start with analyst to verify the requirements are complete and flag ambiguities. Then milestone-planner to break it into milestones with acceptance criteria. Then critic to stress-test the plan for gaps and missing edge cases, correcting all issues before proceeding. Then implementer to write the code and tests. Then qa to verify test coverage meets the acceptance criteria. Then security to scan for injection, replay, and SSRF risks in the webhook handler. Fix all critical and major findings recursively until critic, qa, and security all pass. Open a PR with the full agent trail in the description.

This is the orchestrator's most powerful pattern: a full development pipeline with quality gates. Each agent acts as a checkpoint. Critic validates the plan before any code is written. QA validates the implementation against the spec. Security validates against threat categories. The recursive fix loop ensures issues found late in the pipeline get resolved, not deferred.

#### Strategic Prioritization and Roadmap Alignment

When the backlog is overloaded and the team needs to decide what to build next, use the orchestrator to run a structured prioritization:

> orchestrator: we have three candidate features for the next quarter: plugin marketplace, offline mode, and admin audit logging. For each candidate, route through analyst to estimate effort and risk, roadmap to score with RICE and classify with KANO, security to flag compliance or threat implications, and devops to estimate operational burden. Then independent-thinker to argue which one the team is most likely to regret skipping. Then high-level-advisor to rank all three with a clear recommendation. Store the output in @.agents/analysis/q3-prioritization.md.

The orchestrator runs the same evaluation pipeline across all three candidates, producing comparable data. Roadmap scores each on Reach, Impact, Confidence, and Effort. Security flags compliance obligations. DevOps estimates maintenance tax. Independent-thinker surfaces opportunity cost the team might overlook. High-level-advisor delivers the final ranking with a defensible basis for the quarterly plan.

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

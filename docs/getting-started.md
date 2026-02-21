# Getting Started

This guide walks you through installing and using the AI Agents system in your project.

## Prerequisites

You need one of these AI coding tools:

- [Claude Code CLI](https://docs.anthropic.com/en/docs/agents-and-tools/claude-code/overview)
- [GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/use-copilot-cli)
- [VS Code with GitHub Copilot](https://marketplace.visualstudio.com/items?itemName=GitHub.copilot)

For the skill-installer method, you also need Python 3.10+ and [UV](https://docs.astral.sh/uv/).

## Step 1: Install

The fastest method uses the built-in plugin marketplace. Run this command inside your AI coding tool (not a regular terminal):

**Claude Code:**

```text
/install-plugin rjmurillo/ai-agents
```

**GitHub Copilot CLI:**

```text
/install-plugin rjmurillo/ai-agents
```

This installs all agents for your platform. For selective installation, see [docs/installation.md](installation.md).

## Step 2: Verify

Confirm the agents loaded correctly.

**Claude Code:**

```text
Task(subagent_type="analyst", prompt="Hello, are you available?")
```

**GitHub Copilot CLI:**

```bash
copilot --list-agents
```

**VS Code (Copilot Chat):**

```text
@orchestrator Hello, are you available?
```

If no agents appear, restart your editor and try again.

## Step 3: Use an Agent

Agents accept natural language prompts. You can invoke them directly by name or let the orchestrator route your request.

### Direct invocation

Prefix your prompt with the agent name:

```text
analyst: investigate why the /api/users endpoint returns 500 on emails with plus signs
```

```text
security: scan src/api/ for OWASP Top 10 vulnerabilities
```

```text
qa: write pytest tests for scripts/validate_session_json.py targeting 95% coverage
```

### Orchestrator-routed

For multi-step tasks, describe the full workflow and the orchestrator coordinates agents:

```text
orchestrator: implement user authentication with OAuth2, including tests and security review
```

The orchestrator determines which agents to invoke, in what order, and synthesizes their outputs.

## Step 4: Understand the Output

Each agent produces structured output specific to its role:

| Agent | Output format |
|-------|---------------|
| analyst | Findings with evidence and feasibility assessment |
| architect | Design assessment rated Strong/Adequate/Needs-Work |
| critic | Verdict: APPROVE, APPROVE WITH CONDITIONS, or REJECT |
| implementer | Code, tests, and atomic commits |
| qa | Test reports with coverage analysis |
| security | Threat matrix with CWE/CVSS ratings |
| high-level-advisor | Verdict: GO, CONDITIONAL GO, or NO-GO |

## What Next

- Browse all 21 agents in the [Agent Catalog](agent-catalog.md)
- See all 49 skills in the [Skill Reference](skill-reference.md)
- Understand the system design in [Architecture](architecture.md)
- Learn how to extend and customize in [Customization](customization.md)
- Review the full [Installation Guide](installation.md) for advanced setup options

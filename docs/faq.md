# AI Agents FAQ

Short answers about the AI Agents toolkit. The [README](../README.md) has the full detail.

## What it is

### What is AI Agents?

AI Agents is an open-source multi-agent toolkit for software development. It runs in Claude Code, GitHub Copilot CLI, and VS Code Copilot Chat. An orchestrator routes work to specialist agents with explicit handoffs.

### How many agents does it include?

30 agents. The README [Agent Catalog](../README.md#agent-catalog) lists each one with its purpose and output. [docs/agent-catalog.md](agent-catalog.md) links each agent to its template.

### How do agents review each other's work?

The critic stress-tests plans and returns APPROVED, APPROVED_WITH_CONCERNS, NEEDS_REVISION, or BLOCKED. NEEDS_REVISION sends the plan back to the agent that produced it. QA verifies the tests and security models the threats. A QA failure sends the work back to the implementer.

## Install and platforms

### How do I install it in Claude Code?

Run the two commands below inside Claude Code, then restart Claude Code.

```text
/plugin marketplace add rjmurillo/ai-agents
/plugin install project-toolkit@ai-agents
```

### Does it work with GitHub Copilot CLI?

Yes. Run these two commands inside Copilot CLI. No restart is needed. See [installation.md](installation.md#github-copilot-cli) for more.

```text
/plugin marketplace add rjmurillo/ai-agents
/plugin install project-toolkit@ai-agents
```

### Are the lifecycle skills available in Copilot CLI?

They ship as skills. The six lifecycle skills (`spec`, `plan`, `build`, `test`, `review`, `ship`) are in both bundles, along with agents, the session protocol, and review gates. Claude Code runs them as slash commands (`/spec` to `/ship`). The README [What You Get](../README.md#what-you-get) table lists them as skills for Copilot CLI. [when-to-use.md](when-to-use.md) maps task shapes to lifecycle phases.

## Requirements and cost

### What does it require?

Claude Code or GitHub Copilot CLI with plugin marketplace support. The `project-toolkit` plugin registers no hooks for either CLI (ADR-097), so no hook runtime runs in your session. Some skills run Python scripts, and those skills need Python on PATH. Python 3.14.x is a contributor requirement for this repository.

### Is it free?

The toolkit is MIT licensed. Your Claude or GitHub Copilot plan bills the model usage.

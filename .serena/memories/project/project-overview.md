# AI Agents Project Overview

## Purpose

A coordinated multi-agent system for software development, providing **17 specialized agents** for different development phases. The system is available for:

- **VS Code** (GitHub Copilot)
- **GitHub Copilot CLI**
- **Claude Code CLI**

## Key Features

- **Specialized agents** for different development phases (analyst, architect, milestone-planner, implementer, qa, etc.)
- **Explicit handoff protocols** between agents with defined workflows
- **Cross-session memory** using `cloudmcp-manager`
- **Self-improvement system** with skill tracking and retrospectives
- **Installation scripts** for global or per-repository setup

## Tech Stack

- **Languages**: Markdown (primary), PowerShell (scripts), Python (utilities), YAML (configuration)
- **Tools**: markdownlint-cli2 (linting), npm/npx (package management), git (version control)
- **Platform**: Windows primary, cross-platform compatible

## Repository URL

<https://github.com/rjmurillo/ai-agents>

## Standard Workflows

```text
Feature Development: orchestrator → analyst → architect → milestone-planner → critic → implementer → qa → retrospective
Quick Fix: implementer → qa
Strategic Decision: independent-thinker → high-level-advisor → task-decomposer
```

## Agent Categories

### Primary Workflow Agents

- orchestrator, analyst, architect, milestone-planner, implementer, critic, qa, roadmap

### Support Agents

- memory, skillbook, devops, security, independent-thinker, high-level-advisor, retrospective, explainer, task-decomposer, pr-comment-responder

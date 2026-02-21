# Architecture

This document describes the AI Agents system design, including the plugin structure, template system, and platform support.

## System Overview

AI Agents is a multi-platform agent system built on three layers:

1. **Templates** define agent behavior once in shared markdown files
2. **Build** generates platform-specific agent files from templates
3. **Runtime** loads agents into Claude Code, Copilot CLI, or VS Code

```text
templates/agents/*.shared.md     (source of truth)
        |
        v
build/generate_agents.py        (generation)
        |
        +---> src/claude/        (Claude Code agents)
        +---> src/copilot-cli/   (Copilot CLI agents)
        +---> src/vs-code-agents/(VS Code agents)
```

## Template System

Agent definitions live in `templates/agents/`. Each file uses YAML frontmatter for platform-specific configuration and markdown for the agent prompt.

**Frontmatter fields:**

| Field | Purpose |
|-------|---------|
| `description` | One-line agent description shown in tool selection |
| `argument-hint` | Prompt hint shown to users |
| `tools_vscode` | Tools available on VS Code platform |
| `tools_copilot` | Tools available on Copilot CLI platform |

**Example template structure:**

```markdown
---
description: Research specialist who digs deep into root causes...
argument-hint: Describe the topic to research
tools_vscode:
  - $toolset:editor
  - $toolset:research
tools_copilot:
  - $toolset:editor
  - $toolset:research
---
# Analyst Agent

## Style Guide Compliance
...

## Role and Purpose
...
```

Claude Code agents in `src/claude/` use a different format. They are plain markdown files without YAML frontmatter. Claude Code discovers them through the `.claude/agents/` directory convention.

### Modifying Agents

To change an agent:

1. Edit the template in `templates/agents/<agent>.shared.md`
2. Run `python3 build/generate_agents.py` to regenerate platform files
3. Commit both the template and generated outputs

Do not edit files in `src/vs-code-agents/` or `src/copilot-cli/` directly. They are overwritten on regeneration.

## Plugin Structure

The project distributes agents through the Claude Code plugin marketplace using `.claude-plugin/marketplace.json`:

```json
{
  "name": "ai-agents",
  "plugins": [
    {
      "name": "claude-agents",
      "description": "26 specialized agent definitions...",
      "source": "./src/claude"
    },
    {
      "name": "copilot-cli-agents",
      "description": "Agent definitions for GitHub Copilot CLI",
      "source": "./src/copilot-cli"
    },
    {
      "name": "project-toolkit",
      "description": "Complete project development toolkit...",
      "source": "./.claude"
    }
  ]
}
```

Users install plugins with `/install-plugin rjmurillo/ai-agents` or selectively with `/plugin install <plugin-name>@ai-agents`.

## Platform Differences

| Aspect | Claude Code | Copilot CLI | VS Code |
|--------|------------|-------------|---------|
| Agent location | `src/claude/` | `src/copilot-cli/` | `src/vs-code-agents/` |
| File format | `.md` (no frontmatter) | `.agent.md` (with frontmatter) | `.agent.md` (with frontmatter) |
| Invocation | `Task(subagent_type="...")` | `--agent` flag or `/agent` | `@agent` in Copilot Chat |
| Skills | Yes (49 skills in `.claude/skills/`) | No | No |
| Hooks | Yes (`.claude/hooks/`) | No | No |
| Commands | Yes (`.claude/commands/`) | No | No |

Claude Code has the richest integration because it supports skills, hooks, and commands in addition to agents.

## Agent Communication

Agents communicate through the orchestrator using explicit handoffs. The orchestrator:

1. Receives a user task
2. Classifies complexity (simple, moderate, complex)
3. Routes to appropriate specialists
4. Manages context transfer between agents
5. Synthesizes results into a cohesive response

Each agent operates independently within its domain. Agents do not call each other directly. The orchestrator manages all inter-agent coordination.

## Directory Layout

```text
ai-agents/
├── templates/
│   ├── agents/               # Shared agent templates (edit these)
│   └── platforms/            # Platform generation config
├── build/
│   └── Generate-Agents.ps1  # Template-to-platform generator
├── src/
│   ├── claude/               # Claude Code agents
│   ├── copilot-cli/          # Copilot CLI agents
│   └── vs-code-agents/       # VS Code agents
├── .claude/
│   ├── agents/               # Local agents for this repo
│   ├── skills/               # 49 reusable skills
│   ├── hooks/                # Lifecycle hooks
│   └── commands/             # Slash commands
├── .claude-plugin/
│   └── marketplace.json      # Plugin distribution manifest
├── scripts/                  # Validation and utility scripts
├── tests/                    # pytest test suite
├── .agents/
│   ├── architecture/         # ADRs
│   ├── sessions/             # Session logs
│   └── governance/           # Constraints and policies
└── .serena/
    └── memories/             # Curated knowledge base
```

## Design Decisions

Key architectural decisions are recorded as ADRs in `.agents/architecture/`. Notable decisions include:

| ADR | Decision |
|-----|----------|
| ADR-006 | Logic goes in modules, not workflow YAML |
| ADR-011 | Session state protocol enforcement |
| ADR-012 | Skill catalog discovery and validation |
| ADR-013 | Agent orchestration and parallel execution |
| ADR-017 | Memory tier system |
| ADR-032 | Standardized exit codes |
| ADR-033 | Selective skill gates |
| ADR-035 | Exit code semantics (0=success, 1=logic, 2=config, 3=external, 4=auth) |
| ADR-042 | Python for new scripts (not bash) |
| ADR-043 | Scoped markdownlint on changed files |

## Quality Gates

The system enforces quality at multiple levels:

1. **Pre-commit hooks** validate session logs, markdown formatting, and security patterns
2. **CI workflows** run tests, CodeQL scans, and spec validation
3. **Agent-level gates** use the critic, QA, and security agents as quality checkpoints
4. **Session protocol** requires structured logs with evidence for every session

See [AGENTS.md](../AGENTS.md) for the full session protocol specification.

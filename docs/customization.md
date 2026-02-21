# Customization

This guide explains how to extend and customize the AI Agents system for your project.

## Adding a New Agent

### Step 1: Create the template

Create a new file in `templates/agents/<agent-name>.shared.md`:

```markdown
---
description: One-line description of what the agent does
argument-hint: Describe what the user should provide as input
tools_vscode:
  - $toolset:editor
  - $toolset:research
tools_copilot:
  - $toolset:editor
  - $toolset:research
---
# Agent Name

## Role and Purpose

Describe the agent's role, what it does, and when to use it.

## Output Format

Define the structured output format the agent produces.

## Workflow

1. Step one
2. Step two
3. Step three
```

### Step 2: Generate platform files

Run the generation script to produce platform-specific agent files:

```bash
python3 build/generate_agents.py
```

This creates agent files in `src/vs-code-agents/` and `src/copilot-cli/`.

### Step 3: Add Claude Code agent (if needed)

For Claude Code, create a plain markdown file at `src/claude/<agent-name>.md` without YAML frontmatter.

### Step 4: Register in marketplace

If the agent should be distributed as part of a plugin, it is automatically included because the plugin `source` points to the `src/` directory.

## Modifying Existing Agents

Edit the shared template in `templates/agents/`, then regenerate. Do not edit generated files in `src/vs-code-agents/` or `src/copilot-cli/` directly.

For Claude Code agents in `src/claude/`, you can edit directly since some are not template-generated.

## Creating Skills

Skills are reusable workflow components stored in `.claude/skills/`. Each skill is a directory containing a `SKILL.md` file.

### Skill structure

```text
.claude/skills/my-skill/
├── SKILL.md          # Skill definition with frontmatter
└── scripts/          # Optional supporting scripts
    └── helper.py
```

### SKILL.md format

```markdown
---
name: my-skill
description: What the skill does in one line
---

## Instructions

Step-by-step instructions the agent follows when this skill is invoked.
```

### Using SkillForge

The SkillForge skill automates skill creation:

```text
/SkillForge create a skill that validates JSON schemas against a directory of files
```

SkillForge analyzes your request, checks for existing skills that overlap, and generates the skill following project conventions.

## Customizing Workflows

### Orchestrator routing

The orchestrator routes tasks based on complexity classification:

| Complexity | Agent sequence |
|------------|----------------|
| Simple | Single specialist agent |
| Moderate | 2-3 agents in sequence |
| Complex | Full pipeline with quality gates |

You can override routing by addressing agents directly:

```text
implementer: skip the planning phase and just fix the null check in auth.py line 42
```

### Quality gate configuration

Quality gates are defined in the session protocol. To adjust gates for your project, modify `.agents/governance/PROJECT-CONSTRAINTS.md`.

The default gates are:

1. **Critic review** before implementation
2. **QA validation** after implementation
3. **Security scan** before PR creation

## Adding Hooks

Claude Code hooks run shell commands in response to events. Hooks live in `.claude/hooks/`.

### Hook types

| Hook | Trigger |
|------|---------|
| `PreToolUse` | Before a tool call executes |
| `PostToolUse` | After a tool call completes |
| `UserPromptSubmit` | When the user sends a message |

### Example hook

A pre-tool hook that blocks raw `gh` commands in favor of skills:

```python
#!/usr/bin/env python3
import sys
import json

input_data = json.load(sys.stdin)
if input_data.get("tool_name") == "Bash":
    command = input_data.get("tool_input", {}).get("command", "")
    if command.startswith("gh "):
        print("Blocked: Use the github skill instead of raw gh commands")
        sys.exit(1)
```

## Project-Level Overrides

### CLAUDE.md

The root `CLAUDE.md` file contains project-wide instructions for Claude Code. Add project-specific agent configuration here.

### copilot-instructions.md

The `.github/copilot-instructions.md` file provides instructions for GitHub Copilot (VS Code and CLI).

### Memory system

The memory system stores cross-session knowledge in `.serena/memories/`. Agents read and write memories to maintain context across sessions.

To add project-specific knowledge:

1. Create a memory file in `.serena/memories/`
2. Reference it from the memory index
3. Agents discover and read it automatically

## Platform-Specific Customization

### Claude Code only

Claude Code supports skills, hooks, and commands that other platforms do not. Use these for advanced customization:

- **Skills** for reusable workflows
- **Hooks** for automated guardrails
- **Commands** for user-facing slash commands

### VS Code and Copilot CLI

These platforms support agents and toolsets defined in the YAML frontmatter. Customize available tools by editing the `tools_vscode` and `tools_copilot` fields in agent templates.

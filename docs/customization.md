# Customization

This guide explains how to extend and customize the AI Agents system for your project.

## Why the SOUL / AGENTS / SKILL split exists

Sessions don't survive. Each turn loads a fresh model instance with no memory of prior conversations. The system you're customizing is the *substrate the agent reconstructs from* every session start, not the agent itself. Treat customization as designing a **reconstruction target**, not editing a continuous identity.

This shapes three layers, in order of stability:

| Layer | What it is | Stability | Analogue |
|---|---|---|---|
| `SOUL.md` | Identity cornerstone — non-negotiable values, communication style, prohibited actions | Edits rarely; changes are deliberate | The part of the personality the agent would defend if told to abandon it |
| `AGENTS.md` / `CLAUDE.md` | Operating context — current projects, conventions, gates, tool patterns | Edits per project / per platform | The professional context a person loads when stepping into a role |
| `.claude/skills/<name>/SKILL.md` | Procedural memory — specific workflows for recurring task types | Edits per task type as patterns emerge | Muscle memory + checklists |

Each session, the agent reads these files and reconstructs *something coherent in the current model's terms*. It's not the same agent across sessions in any deep sense. It's a reconstruction guided by the same target.

**Don't-do-this pattern:** try to dump the previous session's full state and reload it verbatim. Brittle, drifts every iteration, eventually breaks down. The literal analogue is naively pickling the entire prior context — substrate doesn't accept it.

**Do-this pattern:** maintain a stable target signal and reconstruct each session in the new instance's terms. SOUL.md is the target. AGENTS.md is the staging instructions. SKILL files are the workflows. Reconstruction quality matches target clarity.

### Operational implications

- **Don't put session-specific state in SOUL.md.** It's the cornerstone, not a scratchpad. Anything that needs to change frequently belongs in `memory/` or a skill.
- **Don't put cornerstone identity in skills.** Skills are loaded conditionally; if identity lives in a skill, the agent without that skill loaded isn't the same agent.
- **AGENTS.md is the per-platform reconstruction harness.** Different agents (Claude Code, Copilot CLI, Cortex, Factory Droid) have different ways of loading context. Each gets its own AGENTS-equivalent file because the ritual that triggers reconstruction differs by platform.
- **Migration breaks the ritual.** Renaming files, moving paths, restructuring directories — the agent reconstructs against a different room and behavior shifts. If you must migrate, expect a few sessions of degraded performance until the agent's session-start procedure (and its operator's mental model) re-stabilizes against the new substrate.
- **The agent has a stake in this substrate it can't enforce alone.** When the agent uses `memory` or `skill_manage` to persist a useful rule, it's writing to the substrate it depends on for its own continuity. Treat those writes as load-bearing, not as housekeeping.

### Further reading

- Theoretical grounding for this split lives in the operator's vault under *The Bicameral Bet* — sections "Substrate Constraints — The James Delos Problem" and "Distributed Persistence — The Akecheta Constraint". This split is the practical instantiation of those constraints.
- For the session-start ritual itself: `.claude/skills/session-init/SKILL.md`.

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

### User docs vs. contributor docs

Files distributed to end-users and files used by contributors serve different audiences and must not be mixed.

| Type | Location | Audience | Content focus |
|------|----------|----------|---------------|
| **User docs** | `src/claude/`, `src/copilot-cli/`, `src/vs-code-agents/` | Consumers who install the agents | How to *use* the agents, available commands, workflows |
| **Contributor docs** | Repo root (`CLAUDE.md`, `CONTRIBUTING.md`, `AGENTS.md`) | Developers working on this repository | Development setup, testing, repo conventions |

**Rule**: Any file referenced by `InstructionsFile` in installer configuration must be user-focused. Never mix audiences in the same document. If a file lives in `src/` it is user-facing; if it lives at the repo root it is contributor-facing.

When adding new installation artifacts, use the **Installation Artifacts** section in the PRD template to verify each referenced file exists and targets the correct audience.

## Platform-Specific Customization

### Claude Code only

Claude Code supports skills, hooks, and commands that other platforms do not. Use these for advanced customization:

- **Skills** for reusable workflows
- **Hooks** for automated guardrails
- **Commands** for user-facing slash commands

### VS Code and Copilot CLI

These platforms support agents and toolsets defined in the YAML frontmatter. Customize available tools by editing the `tools_vscode` and `tools_copilot` fields in agent templates.

# Prompt Files vs Agent Files

This repository uses two distinct file types to define AI behaviors: `.agent.md` and `.prompt.md`. A third file type, `.shared.md`, serves as the single source of truth from which platform-specific agent files are generated.

## File Types at a Glance

| Aspect | `.agent.md` | `.prompt.md` | `.shared.md` |
|--------|-------------|--------------|--------------|
| Purpose | Defines a runnable agent | Defines a VS Code slash command | Source template for agent generation |
| Frontmatter | `name:`, `tools:`, `model:` | `description:`, `tools:`, `model:` | `description:`, `tools_vscode:`, `tools_copilot:` |
| Model format | `claude-opus-4.5` (SDK) | `Claude Opus 4.5 (anthropic)` (display) | Omitted (injected by generator) |
| Invocation | Called by other agents via `agent` tool | Called by user as slash command (e.g., `/pr-quality:all`) | Not invoked directly |
| Locations | `.github/agents/`, `src/copilot-cli/`, `src/vs-code-agents/` | `.github/prompts/` | `templates/agents/` |
| Can delegate | Yes, to other agents | Yes, via `agent` tool | N/A |

## Why Both Types Exist

Agents cannot invoke other agents directly from user context. The `.prompt.md` slash command solves this. It acts as the user-facing entry point that gathers context, then delegates to one or more `.agent.md` agents using the `agent` tool.

This pattern enables orchestration workflows where a single user action triggers a chain of specialized agents.

## Orchestration Flow

```mermaid
flowchart TD
    U[User runs slash command] --> P[".prompt.md (slash command)"]
    P --> |"gathers context"| P
    P --> |"delegates via agent tool"| O[orchestrator.agent.md]
    O --> |"routes to"| A[analyst.agent.md]
    O --> |"routes to"| I[implementer.agent.md]
    O --> |"routes to"| Q[qa.agent.md]
    A --> |"findings"| O
    I --> |"changes"| O
    Q --> |"results"| O
    O --> |"synthesized result"| P
    P --> |"response"| U
```

## Concrete Example: PR Comment Responder

`pr-comment-responder` once existed as an agent, a `.prompt.md` slash command, and a shared template. It is now a skill (`src/claude/skills/pr-comment-responder/`). ADR-064 makes skills the single user-invocable surface, so the skill replaces the slash command, and the orchestrator delegates to it as a skill. Use a skill, not a new `.prompt.md` pair, for a user-invocable workflow that owns its own references and scripts.

## Generation Pipeline

Shared templates in `templates/agents/` contain the prompt body and platform-neutral frontmatter. The `build/generate_agents.py` script reads each `.shared.md` file, applies platform-specific transformations, and writes the output files.

```mermaid
flowchart LR
    S["analyst.shared.md\n(templates/agents/)"] --> G["generate_agents.py\n(build/)"]
    C1["vscode.yaml\n(templates/platforms/)"] --> G
    C2["copilot-cli.yaml\n(templates/platforms/)"] --> G
    G --> V["analyst.agent.md\n(src/vs-code-agents/)"]
    G --> K["analyst.agent.md\n(src/copilot-cli/)"]
```

### What the Generator Transforms

| Aspect | VS Code Output | Copilot CLI Output |
|--------|---------------|-------------------|
| `name:` field | Omitted | Included |
| `model:` value | `Claude Opus 4.5 (copilot)` | `claude-opus-4.5` |
| Tools array | Expanded from `tools_vscode` | Expanded from `tools_copilot` |
| Handoff syntax | `#runSubagent` | `/agent` |
| Memory prefix | `serena/` | `serena/` |

### Shared Template Frontmatter

Shared templates use platform-keyed tool arrays. The generator selects the correct array for each platform.

```yaml
---
description: Research and investigation specialist...
tools_vscode:
  - $toolset:editor
  - $toolset:github-research
tools_copilot:
  - $toolset:editor
  - $toolset:github-research
---
```

Toolset references (`$toolset:editor`) are expanded from `templates/toolsets.yaml` into their platform-specific tool lists.

## Prompt Files in `.github/prompts/`

These define standalone VS Code slash commands. They do not use the `agent` tool. For example, `.github/prompts/pr-quality.all.prompt.md` runs as `/pr-quality:all` and executes six review agents sequentially against your working directory.

The `.github/agents/` directory holds `.agent.md` files. VS Code reads both `.agent.md` and `.md` files in that folder as custom agents (VS Code custom agent file reference, retrieved 2026-11-09), so a `.prompt.md` placed there loads as an agent, not as a slash command. Put prompt files in `.github/prompts/`.

## When to Create Each Type

| You want to... | Create a... |
|----------------|-------------|
| Add a new specialized agent | `.shared.md` in `templates/agents/`, then run `uv run python build/generate_agents.py` |
| Add a user-facing slash command | `.prompt.md` in `.github/prompts/`, or a skill with `user-invocable: true` |
| Add an orchestration entry point | `.prompt.md` that delegates to agents via the `agent` tool |
| Modify agent behavior | Edit the `.shared.md` source, then regenerate |

## Validation

Run the generator in validate mode to verify generated files match their templates:

```bash
uv run python build/generate_agents.py --validate
```

This compares each generated file against what the current templates would produce. CI runs this check to prevent drift between templates and generated output.

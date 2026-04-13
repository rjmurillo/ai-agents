# Claude vs Template Agent Differences

## Overview

The ai-agents repository maintains **three** output platforms for agents:

1. **Claude Code** (`src/claude/`) - Manually maintained, NOT auto-generated
2. **VS Code Agents** (`src/vs-code-agents/`) - Auto-generated from templates
3. **Copilot CLI** (`src/copilot-cli/`) - Auto-generated from templates

This document describes the key differences between Claude files and shared templates.

## Architecture Decision

**Claude files are intentionally kept separate** from the template system. Reasons:

- Claude has platform-specific tool syntax (`mcp__*` prefixes)
- Claude uses `Task(subagent_type="...", prompt="...")` for agent invocation
- Claude files include platform-specific documentation sections
- Different model configurations (sonnet vs opus per-agent)

## Key Differences

### 1. Frontmatter Structure

| Field | Claude | Templates |
|-------|--------|-----------|
| Agent Name | `name: "Agent Name"` | N/A (derived from filename) |
| Model | `model: sonnet` or `opus` | N/A |
| Description | N/A | `description: "..."` |
| Argument Hint | `argument-hint: "..."` | `argument-hint: "..."` |
| Tools | N/A | `tools_vscode: [...]`, `tools_copilot: [...]` |

### 2. Agent Invocation Syntax

**Claude:**

```python
Task(subagent_type="analyst", prompt="Investigate why X fails")
```

**Templates (VS Code/Copilot):**

```text
#runSubagent with subagentType=analyst
[prompt content]
```

Or:

```text
runSubagent(agentName: "analyst", description: "3-5 words", prompt: "...")
```

### 3. Memory Tool Prefixes

**Claude:**

```python
mcp__cloudmcp-manager__memory-search_nodes(query="[topic]")
mcp__cloudmcp-manager__memory-add_observations(...)
mcp__cloudmcp-manager__memory-create_entities(...)
```

**Templates:**

```text
cloudmcp-manager/memory-search_nodes with query="[topic]"
cloudmcp-manager/memory-add_observations with observations=[...]
```

### 4. Claude-Specific Sections

Claude files include sections not present in templates:

- **"Claude Code Tools"** - Platform-specific tool documentation
- **"GitHub Skill Integration"** - References to `.claude/skills/github/` scripts
- **Model selection guidance** - When to use sonnet vs opus

### 5. Content Depth

Some Claude agents have significantly more content than their template counterparts:

| Agent | Claude Lines | Template Lines | Difference |
|-------|--------------|----------------|------------|
| orchestrator | ~1300 | ~400 | Claude has extended routing logic |
| pr-comment-responder | ~862 | ~697 | Similar, Claude has extra skill paths |
| analyst | ~364 | ~326 | Similar, Claude has tool sections |
| retrospective | ~940 | ~847 | Similar, Claude has structured handoff |

### 6. Handoff Protocol

**Claude** agents use structured markdown for handoff output:

```markdown
## Structured Handoff Output

**For Orchestrator Integration:**
- Summary: [key finding]
- Artifacts: [file paths]
- Next Agent: [recommended]
- Priority: [P0-P3]
```

**Templates** use simpler handoff tables:

```markdown
| Target | When | Purpose |
|--------|------|---------|
| orchestrator | Analysis complete | Route to next agent |
```

## Synchronization Strategy

### What Should Stay In Sync

1. **Core agent behavior** - Same analytical frameworks, workflows, phases
2. **Activation profiles** - Keywords and summon prompts
3. **Output formats** - Same document structures
4. **Agent capability matrix** - Same routing heuristics

### What Can Differ

1. **Tool invocation syntax** - Platform-specific
2. **Memory prefixes** - Platform-specific
3. **Supplementary documentation** - Claude can have extra sections
4. **Model configuration** - Only relevant for Claude

## Maintenance Guidelines

1. **Edit shared content in templates first** - Then manually port to Claude if needed
2. **Use Generate-Agents.ps1** - Always regenerate after template changes
3. **Claude-only content** - Keep platform-specific content in Claude files only
4. **Regular sync checks** - Periodically compare core content between platforms

## Related Memory

Memory entity: `Pattern-AgentGeneration` contains learnings about this system.

See also: `AGENTS.md` in root directory for cross-session memory references.

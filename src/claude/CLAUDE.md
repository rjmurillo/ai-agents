## AI Agent System

This section provides instructions for using the multi-agent system with Claude Code.

### Overview

A coordinated multi-agent system for software development. Specialized agents handle different responsibilities with explicit handoff protocols and persistent memory.

### Agent Catalog

| Agent | Purpose | When to Use |
|-------|---------|-------------|
| **orchestrator** | Task coordination | Complex multi-step tasks |
| **implementer** | Production code, .NET patterns | Writing/reviewing code |
| **analyst** | Research, root cause analysis | Investigating issues, evaluating requests |
| **architect** | ADRs, design governance | Technical decisions |
| **planner** | Milestones, work packages | Breaking down epics |
| **critic** | Plan validation | Before implementation |
| **qa** | Test strategy, verification | After implementation |
| **explainer** | PRDs, feature docs | Documenting features |
| **task-generator** | Atomic task breakdown | After PRD created |
| **high-level-advisor** | Strategic decisions | Major direction choices |
| **independent-thinker** | Challenge assumptions | Getting unfiltered feedback |
| **memory** | Cross-session context | Retrieving/storing knowledge |
| **skillbook** | Skill management | Managing learned strategies |
| **retrospective** | Learning extraction | After task completion |
| **devops** | CI/CD pipelines | Build automation, deployment |
| **roadmap** | Strategic vision | Epic definition, prioritization |
| **security** | Vulnerability assessment | Threat modeling, secure coding |
| **pr-comment-responder** | PR review handler | Addressing bot/human review comments |

### Invoking Agents

Use the Task tool with `subagent_type` parameter:

```python
# Research before implementation
Task(subagent_type="analyst", prompt="Investigate why X fails")

# Design review
Task(subagent_type="architect", prompt="Review design for feature X")

# Implementation
Task(subagent_type="implementer", prompt="Implement feature X per plan")

# Plan validation
Task(subagent_type="critic", prompt="Validate plan at .agents/planning/...")

# Code review
Task(subagent_type="architect", prompt="Review code quality")

# Extract learnings
Task(subagent_type="retrospective", prompt="Analyze what we learned")
```

### Standard Workflows

**Feature Development:**

```text
analyst -> architect -> planner -> critic -> implementer -> qa -> retrospective
```

**Quick Fix:**

```text
implementer -> qa
```

**Strategic Decision:**

```text
independent-thinker -> high-level-advisor -> task-generator
```

### Memory Protocol

Agents use `cloudmcp-manager` for cross-session memory:

```python
# Search for context
mcp__cloudmcp-manager__memory-search_nodes(query="[topic]")

# Store learnings
mcp__cloudmcp-manager__memory-add_observations(...)
mcp__cloudmcp-manager__memory-create_entities(...)
```

### Agent Output Directories

Agents save artifacts to `.agents/`:

| Directory | Purpose |
|-----------|---------|
| `analysis/` | Analyst findings, research |
| `architecture/` | ADRs, design decisions |
| `planning/` | Plans and PRDs |
| `critique/` | Plan reviews |
| `qa/` | Test strategies and reports |
| `retrospective/` | Learning extractions |
| `roadmap/` | Epic definitions |
| `devops/` | CI/CD configurations |
| `security/` | Threat models |
| `sessions/` | Session context |

### Best Practices

1. **Start with orchestrator**: For complex tasks, let orchestrator route to appropriate agents
2. **Memory First**: Agents retrieve context before multi-step reasoning
3. **Clear Handoffs**: Agents announce next agent and purpose
4. **Store Learnings**: Update memory at milestones
5. **Commit Atomically**: Small, conventional commits

### Routing Heuristics

| Task Type | Primary Agent | Fallback |
|-----------|---------------|----------|
| Code implementation | implementer | - |
| Architecture review | architect | analyst |
| Task decomposition | task-generator | planner |
| Challenge assumptions | independent-thinker | critic |
| Test strategy | qa | implementer |
| Research/investigation | analyst | - |
| Strategic decisions | high-level-advisor | roadmap |
| Documentation/PRD | explainer | planner |
| CI/CD pipelines | devops | implementer |
| Security review | security | analyst |
| Post-project learning | retrospective | analyst |

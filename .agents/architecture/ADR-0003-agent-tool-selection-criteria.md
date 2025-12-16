---
status: accepted
date: 2025-12-16
decision-makers: ["architect", "orchestrator"]
consulted: ["implementer", "analyst", "devops"]
informed: ["all agents"]
---

# ADR-0003: Role-Specific Tool Allocation for Multi-Agent System

## Context and Problem Statement

The multi-agent system originally allocated ~58 tools to all agents via blanket permissions. This approach caused several problems:

1. **Context bloat**: Each agent's context window was consumed by tool definitions for capabilities they never used
2. **Token waste**: Tool schemas add significant tokens to every request, increasing cost and latency
3. **Agent confusion**: Agents would sometimes attempt to use tools outside their intended role
4. **Security surface**: Unrestricted tool access violated principle of least privilege
5. **Debugging difficulty**: When issues arose, it was unclear which tools an agent *should* be using

**How should we allocate tools to agents to minimize context overhead while ensuring each agent has the capabilities required for its role?**

## Decision Drivers

* **Principle of least privilege**: Agents should only have access to tools required for their specific role
* **Context efficiency**: Minimize tool definition overhead in context windows (target: 3-9 tools per agent)
* **Role clarity**: Tool allocation should reinforce agent specialization
* **Operational requirements**: Each agent must have all tools necessary to complete their designated tasks
* **Cross-session continuity**: All agents need persistent memory capabilities
* **Semantic code understanding**: All agents benefit from intelligent code navigation

## Considered Options

* **Option 1: Blanket tool allocation** - All agents get all ~58 tools
* **Option 2: Role-specific tool allocation** - Curated 3-9 tools per agent based on responsibilities
* **Option 3: Tiered tool allocation** - Base tools for all, specialty tools per role
* **Option 4: Dynamic tool loading** - Load tools on-demand based on task

## Decision Outcome

**Chosen option: "Option 2: Role-specific tool allocation"**, because it provides the optimal balance of context efficiency, role clarity, and operational capability. Each agent receives a curated set of tools aligned with their core responsibilities.

### Consequences

**Good:**

* Reduced context overhead from ~58 tools to 3-9 per agent
* Clearer agent specialization reinforced by tool boundaries
* Reduced token costs per request
* Faster response times due to smaller context
* Improved debugging (tools indicate intended capabilities)
* Better security posture through least privilege

**Bad:**

* Requires maintenance when agent roles evolve
* New tools require explicit allocation decisions
* Agents cannot adapt to unexpected tool needs without reconfiguration

**Neutral:**

* Tool allocation becomes part of agent definition governance
* Requires documentation of tool selection rationale

### Confirmation

Verify implementation by checking each `.github/agents/*.agent.md` file has:
- Explicit `tools:` frontmatter with 3-9 entries
- Tools aligned with role responsibilities per decision matrix

## Tool Categories

### Category 1: Core Operations

| Tool | Purpose | Grants |
|------|---------|--------|
| `read` | File and code reading | Read-only filesystem access |
| `edit` | File modification | Write access to files |
| `search` | Code search, grep, semantic search | Code navigation |
| `execute` | Terminal command execution | Shell access |

### Category 2: Memory Systems (Universal)

| Tool | Purpose | Grants |
|------|---------|--------|
| `cloudmcp-manager/*` | Cross-session memory, context persistence | Memory read/write |
| `serena/*` | Semantic code analysis, symbol navigation | Intelligent code understanding |

**Rationale for universal allocation**: All agents benefit from cross-session context and semantic code understanding. These are foundational capabilities that enhance any agent's effectiveness.

### Category 3: Research Tools

| Tool | Purpose | Best For |
|------|---------|----------|
| `web` | Web search | Current information, external docs |
| `perplexity/*` | AI-powered research | Complex queries, synthesis |
| `context7/*` | Library documentation | API reference, usage patterns |
| `cognitionai/deepwiki/*` | Repository analysis | Understanding external codebases |

### Category 4: GitHub Integration

| Tool | Purpose | Best For |
|------|---------|----------|
| `github/*` | Full GitHub API | Issues, PRs, repos, commits |
| `github.vscode-pull-request-github/*` | PR-specific operations | PR comments, reviews |

### Category 5: Agent Orchestration

| Tool | Purpose | Best For |
|------|---------|----------|
| `agent` | Invoke sub-agents | Multi-agent coordination |
| `todo` | Task tracking | Workflow state management |
| `memory` | Direct memory operations | Memory-focused operations |

## Decision Matrix

### Core Operations by Role

| Agent | read | edit | search | execute | Rationale |
|-------|:----:|:----:|:------:|:-------:|-----------|
| analyst | ✓ | ✗ | ✓ | ✗ | Research-only, no modifications |
| architect | ✓ | ✓ | ✓ | ✗ | ADR/doc creation, no execution |
| critic | ✓ | ✗ | ✓ | ✗ | Review-only, no modifications |
| devops | ✓ | ✓ | ✓ | ✓ | Full CI/CD pipeline access |
| explainer | ✓ | ✓ | ✗ | ✗ | Documentation creation |
| high-level-advisor | ✓ | ✗ | ✓ | ✗ | Strategic review, no implementation |
| implementer | ✓ | ✓ | ✓ | ✓ | Full development capabilities |
| independent-thinker | ✓ | ✗ | ✓ | ✗ | Analysis without bias from editing |
| memory | ✓ | ✗ | ✗ | ✗ | Memory management only |
| orchestrator | ✓ | ✗ | ✓ | ✗ | Coordination, not implementation |
| planner | ✓ | ✓ | ✓ | ✗ | Plan creation, no execution |
| pr-comment-responder | ✓ | ✓ | ✗ | ✓ | PR interaction with code fixes |
| qa | ✓ | ✓ | ✓ | ✓ | Test creation and execution |
| retrospective | ✓ | ✗ | ✓ | ✗ | Review without modification |
| roadmap | ✓ | ✓ | ✗ | ✗ | Strategic document creation |
| security | ✓ | ✗ | ✓ | ✗ | Security audit, no code changes |
| skillbook | ✓ | ✓ | ✓ | ✗ | Skill documentation updates |
| task-generator | ✓ | ✓ | ✓ | ✗ | Task file creation |

### Specialty Tools by Role

| Agent | Research | GitHub | Orchestration | Rationale |
|-------|:--------:|:------:|:-------------:|-----------|
| analyst | web, perplexity, context7, deepwiki | github/* | ✗ | Heavy research needs |
| architect | ✗ | ✗ | ✗ | Internal design focus |
| critic | ✗ | ✗ | ✗ | Internal review focus |
| devops | ✗ | github/* | ✗ | GitHub Actions, workflows |
| explainer | ✗ | ✗ | ✗ | Documentation focus |
| high-level-advisor | ✗ | ✗ | ✗ | Strategic reasoning |
| implementer | ✗ | github/* | ✗ | PRs, commits, issues |
| independent-thinker | web, perplexity, deepwiki | ✗ | ✗ | External perspective research |
| memory | ✗ | ✗ | memory | Direct memory ops |
| orchestrator | ✗ | github/* | agent, todo, memory | Full coordination |
| planner | ✗ | ✗ | ✗ | Internal planning |
| pr-comment-responder | ✗ | vscode-pr/* | agent | PR-specific operations |
| qa | ✗ | ✗ | ✗ | Test-focused |
| retrospective | ✗ | ✗ | agent | May delegate analysis |
| roadmap | ✗ | ✗ | ✗ | Strategic documents |
| security | web, perplexity | ✗ | ✗ | CVE/vulnerability research |
| skillbook | ✗ | ✗ | ✗ | Internal skill docs |
| task-generator | ✗ | ✗ | ✗ | Task file creation |

## Complete Tool Allocations

| Agent | Tools | Count |
|-------|-------|:-----:|
| analyst | read, search, web, github/*, cloudmcp-manager/*, cognitionai/deepwiki/*, context7/*, perplexity/*, serena/* | 9 |
| architect | read, edit, search, cloudmcp-manager/*, serena/* | 5 |
| critic | read, search, cloudmcp-manager/*, serena/* | 4 |
| devops | execute, read, edit, search, cloudmcp-manager/*, github/*, serena/* | 7 |
| explainer | read, edit, cloudmcp-manager/*, serena/* | 4 |
| high-level-advisor | read, search, cloudmcp-manager/*, serena/* | 4 |
| implementer | execute, read, edit, search, cloudmcp-manager/*, github/*, serena/* | 7 |
| independent-thinker | read, search, web, cognitionai/deepwiki/*, cloudmcp-manager/*, perplexity/*, serena/* | 7 |
| memory | read, memory, cloudmcp-manager/*, serena/* | 4 |
| orchestrator | read, search, agent, memory, todo, cloudmcp-manager/*, github/*, serena/* | 8 |
| planner | read, edit, search, cloudmcp-manager/*, serena/* | 5 |
| pr-comment-responder | execute, read, edit, agent, cloudmcp-manager/*, github.vscode-pull-request-github/*, serena/* | 7 |
| qa | execute, read, edit, search, cloudmcp-manager/*, serena/* | 6 |
| retrospective | read, search, agent, cloudmcp-manager/*, serena/* | 5 |
| roadmap | read, edit, cloudmcp-manager/*, serena/* | 4 |
| security | read, search, web, cloudmcp-manager/*, serena/*, perplexity/* | 6 |
| skillbook | read, edit, search, cloudmcp-manager/*, serena/* | 5 |
| task-generator | read, edit, search, cloudmcp-manager/*, serena/* | 5 |

**Statistics:**
- Minimum: 4 tools (critic, explainer, high-level-advisor, memory, roadmap)
- Maximum: 9 tools (analyst)
- Average: 5.6 tools per agent
- Reduction: ~58 → 5.6 average (90% reduction)

## Pros and Cons of the Options

### Option 1: Blanket Tool Allocation

*All agents receive all ~58 available tools*

* Good, because agents can adapt to any situation
* Good, because no maintenance required for tool allocation
* Bad, because massive context overhead (~15-20% of context consumed by tool definitions)
* Bad, because agents may use inappropriate tools for their role
* Bad, because violates principle of least privilege
* Bad, because higher token costs per request

### Option 2: Role-Specific Tool Allocation (Chosen)

*Each agent receives 3-9 curated tools based on role*

* Good, because minimal context overhead
* Good, because reinforces agent specialization
* Good, because follows principle of least privilege
* Good, because clear tool ownership aids debugging
* Neutral, because requires governance when adding tools
* Bad, because agents cannot adapt to unexpected needs

### Option 3: Tiered Tool Allocation

*Base tier (memory, read) for all, specialty tier per role*

* Good, because ensures universal capabilities
* Good, because systematic structure
* Neutral, because similar to Option 2 with more formalism
* Bad, because tiers may not align with actual needs

### Option 4: Dynamic Tool Loading

*Tools loaded on-demand based on detected task*

* Good, because optimal context at any moment
* Good, because agents can access any tool when truly needed
* Bad, because adds complexity to runtime
* Bad, because detection may be unreliable
* Bad, because not supported by current platform

## Anti-Patterns

### ❌ DO NOT: Grant execute to non-implementation agents

**Why**: Agents focused on research, review, or planning should not have shell access. This prevents accidental mutations and maintains clear role boundaries.

**Exception**: Only `implementer`, `devops`, `qa`, and `pr-comment-responder` should have `execute`.

### ❌ DO NOT: Grant edit to review-only agents

**Why**: Agents like `critic`, `analyst`, `high-level-advisor`, `retrospective`, and `security` should analyze without modifying. Edit capability creates temptation to "fix" instead of "report."

### ❌ DO NOT: Give all agents research tools

**Why**: Research tools (web, perplexity, context7, deepwiki) are expensive in terms of context and latency. Only agents with explicit research responsibilities should have them.

**Agents with research tools**: `analyst`, `independent-thinker`, `security`

### ❌ DO NOT: Grant agent orchestration tools widely

**Why**: The `agent` tool enables sub-agent invocation. Only coordinators should have this to prevent circular or unmanaged agent chains.

**Agents with orchestration**: `orchestrator`, `pr-comment-responder`, `retrospective`

### ❌ DO NOT: Skip memory tools

**Why**: `cloudmcp-manager/*` and `serena/*` are universal requirements. Removing them breaks cross-session continuity and intelligent code navigation.

### ❌ DO NOT: Add tools "just in case"

**Why**: Every tool adds context overhead. Only add tools with demonstrated need based on agent responsibilities.

## Implementation Notes

### Adding a New Tool

1. Identify which agent role(s) need the tool
2. Verify the tool aligns with agent's core mission
3. Check tool doesn't violate anti-patterns
4. Add to agent's `tools:` frontmatter
5. Update this ADR's decision matrix

### Adding a New Agent

1. Define core mission and responsibilities
2. Apply decision matrix to determine tool categories
3. Start minimal, add tools only as needed
4. Document rationale in agent file

### Tool Allocation Review Triggers

- Agent responsibilities change
- New MCP server added to system
- Performance issues traced to context size
- Agent attempts to use unavailable tool

## Related Decisions

- [ADR-0002: Agent Model Selection Optimization](ADR-002-agent-model-selection-optimization.md) - Model selection criteria for agents

## More Information

**Source of truth**: `.github/agents/*.agent.md` files contain the definitive tool allocations.

**Task reference**: This ADR documents the methodology established during Task 8 tool optimization.

**Review schedule**: Re-evaluate tool allocations quarterly or when adding new agents/tools.

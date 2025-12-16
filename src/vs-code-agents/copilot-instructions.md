## AI Agent System

This section provides instructions for using the multi-agent system with VS Code / Copilot Chat.

### Overview

A coordinated multi-agent system for software development. Specialized agents handle different responsibilities with explicit handoff protocols and persistent memory.

### Primary Workflow Agents

| Agent | Role | Best For | Output Directory |
|-------|------|----------|------------------|
| **orchestrator** | Task coordination | Complex multi-step tasks | N/A (routes to others) |
| **analyst** | Pre-implementation research | Root cause analysis, requirements | `.agents/analysis/` |
| **architect** | Design governance | ADRs, technical decisions | `.agents/architecture/` |
| **planner** | Work package creation | Epic breakdown, milestones | `.agents/planning/` |
| **implementer** | Code execution | Production code, tests | Source files |
| **critic** | Plan validation | Review before implementation | `.agents/critique/` |
| **qa** | Test verification | Test strategy, coverage | `.agents/qa/` |
| **roadmap** | Strategic vision | Epic definition, prioritization | `.agents/roadmap/` |

### Support Agents

| Agent | Role | Best For |
|-------|------|----------|
| **memory** | Context continuity | Cross-session persistence |
| **skillbook** | Skill management | Learned strategy updates |
| **devops** | CI/CD pipelines | Build automation, deployment |
| **security** | Vulnerability assessment | Threat modeling, secure coding |
| **independent-thinker** | Assumption challenging | Alternative viewpoints |
| **high-level-advisor** | Strategic decisions | Prioritization, unblocking |
| **retrospective** | Reflector/learning | Outcome analysis, skill extraction |
| **explainer** | Documentation | PRDs, technical specs |
| **task-generator** | Task decomposition | Breaking epics into tasks |

### Invoking Agents

Use the `#runSubagent` command in Copilot Chat:

```text
#runSubagent with subagentType=orchestrator
Help me implement a new feature for user authentication

#runSubagent with subagentType=analyst
Investigate why the API is returning 500 errors

#runSubagent with subagentType=implementer
Implement the login form per the plan in .agents/planning/

#runSubagent with subagentType=critic
Validate the implementation plan at .agents/planning/feature-plan.md
```

### Standard Workflows

**Feature Development:**

```text
orchestrator -> analyst -> architect -> planner -> critic -> implementer -> qa -> retrospective
```

**Quick Fix Path:**

```text
implementer -> qa
```

**Strategic Decision Path:**

```text
independent-thinker -> high-level-advisor -> task-generator
```

### Handoff Protocol

When handing off between agents:

1. **Announce**: "Completing [task]. Handing off to [agent] for [purpose]"
2. **Save Artifacts**: Store outputs in appropriate `.agents/` directory
3. **Route**: Use `#runSubagent with subagentType={agent_name}`

### Memory System

Agents use `cloudmcp-manager` memory tools for cross-session continuity:

- `cloudmcp-manager/memory-search_nodes`: Find relevant context
- `cloudmcp-manager/memory-create_entities`: Store new knowledge
- `cloudmcp-manager/memory-add_observations`: Update existing entities
- `cloudmcp-manager/memory-create_relations`: Link related concepts

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

### Best Practices

1. **Memory First**: Retrieve context before multi-step reasoning
2. **Document Outputs**: Save artifacts to appropriate directories
3. **Clear Handoffs**: Announce next agent and purpose
4. **Store Learnings**: Update memory at milestones
5. **Follow Plans**: The plan document is authoritative
6. **Test Everything**: No skipping hard tests
7. **Commit Atomically**: Small, conventional commits

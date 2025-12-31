# GitHub Copilot Instructions

## BLOCKING GATE: Session Protocol

> **Canonical Source**: [.agents/SESSION-PROTOCOL.md](../.agents/SESSION-PROTOCOL.md)
>
> This file uses RFC 2119 key words. MUST = required, SHOULD = recommended, MAY = optional.

### Phase 1: Serena Initialization (BLOCKING)

If Serena MCP tools are available, you MUST NOT proceed to any other action until both calls succeed:

```text
1. serena/activate_project  (with project path)
2. serena/initial_instructions
```

**Verification**: Tool output appears in session transcript.

**If skipped**: You lack project memories, semantic code tools, and historical context.

**Check for Serena**: Look for tools prefixed with `serena/` or `mcp__serena__`.

### Phase 2: Context Retrieval (BLOCKING)

You MUST read `.agents/HANDOFF.md` before starting work.

**Verification**: Content appears in session context; you reference prior decisions.

**If skipped**: You will repeat completed work or contradict prior decisions.

### Phase 3: Session Log (REQUIRED)

You MUST create session log at `.agents/sessions/YYYY-MM-DD-session-NN.md` early in session.

**Verification**: File exists with Protocol Compliance section.

### Session End (BLOCKING)

You CANNOT claim session completion until validation PASSES:

```bash
pwsh scripts/Validate-Session.ps1 -SessionLogPath ".agents/sessions/[session-log].md"
```

Before running validator, you MUST:

1. Complete Session End checklist in session log (all `[x]` checked)
2. Update `.agents/HANDOFF.md` with session summary and session log link
3. Run `npx markdownlint-cli2 --fix "**/*.md"`
4. Commit all changes including `.agents/` files
5. Record commit SHA in Session End checklist Evidence column

**Verification**: Validator exits with code 0 (PASS).

**If validation fails**: Fix violations and re-run validator. Do NOT claim completion.

**Full protocol with RFC 2119 requirements**: [.agents/SESSION-PROTOCOL.md](../.agents/SESSION-PROTOCOL.md)

### Branch Operation Verification (MUST)

Before ANY mutating git or GitHub operation, you MUST verify the current branch:

```bash
# 1. Always verify current branch first
git branch --show-current

# 2. Confirm it matches your intended PR/issue
```

**Required flags for external operations**:

| Operation | Required Flag | Example |
|-----------|---------------|---------|
| `gh workflow run` | `--ref {branch}` | `gh workflow run ci.yml --ref feat/my-feature` |
| `gh pr create` | `--base` and `--head` | `gh pr create --base main --head feat/my-feature` |

**Anti-patterns to AVOID**:

| Do NOT | Do Instead |
|--------|------------|
| `gh workflow run ci.yml` (no ref) | `gh workflow run ci.yml --ref {branch}` |
| Assume you're on the right branch | Run `git branch --show-current` first |
| Switch branches without checking status | Run `git status` before `git checkout` |

**Why**: Branch confusion causes commits to wrong branches, workflows on wrong refs, and PRs from wrong base - wasting significant effort.

---

Refer to [AGENTS.md](../AGENTS.md) for complete project instructions.

This file exists for GitHub Copilot's repo-level custom instructions. All canonical agent documentation is maintained in `AGENTS.md` to follow the DRY principle.

## Quick Reference

- **Agent invocation**: `@agent_name` in Copilot Chat or `#runSubagent with subagentType=agent_name`
- **Memory system**: `cloudmcp-manager` memory tools
- **Output directories**: `.agents/{analysis,architecture,planning,critique,qa,retrospective}/`

For full details on workflows, agent catalog, and best practices, see [AGENTS.md](../AGENTS.md).

<!-- BEGIN: ai-agents installer -->
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

<!-- END: ai-agents installer -->

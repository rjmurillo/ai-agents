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
pwsh scripts/Validate-SessionEnd.ps1 -SessionLogPath ".agents/sessions/[session-log].md"
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

---

## ⚠️ CRITICAL: Cost Efficiency Requirements

> **Canonical Source**: [.agents/governance/COST-GOVERNANCE.md](../.agents/governance/COST-GOVERNANCE.md)
>
> This section uses RFC 2119 key words. MUST = required, SHOULD = recommended, MAY = optional.

**Cost efficiency is a first-class requirement, not an afterthought.** Both Claude API token costs and GitHub Actions runner costs directly impact sustainability. Inefficient sessions waste money.

### Cost Impact Examples

| Cost Source | Impact of Inefficiency |
|-------------|----------------------|
| **Claude API** | Opus 4.5 input_no_cache: $15/M tokens. A single uncached 100M token day = $1,500 |
| **GitHub Actions** | Windows runners: 2x cost. macOS: 10x cost. Credits deplete fast |
| **Artifact Storage** | Accumulates daily. 37,000 GB-hours = $12/month for ONE repo |

### Token Efficiency Requirements (Claude API)

| Req Level | Requirement | Rationale |
|-----------|-------------|-----------|
| **MUST** | Use Serena symbolic tools to read symbol bodies, not entire files | Reduces input tokens by 80%+ |
| **MUST** | Read task-specific memories before work (enables cache hits) | Cache reads: $1.50/M vs $15/M |
| **MUST** | Use Haiku for quick tasks (model selection) | Haiku: $0.25/M vs Opus: $15/M |
| **SHOULD** | Limit file reads to necessary sections using offset/limit | Reduces context bloat |
| **SHOULD** | Use `#runSubagent` for codebase exploration | Delegated agents have separate context |

### GitHub Actions Cost Requirements

| Req Level | Requirement | Reference |
|-----------|-------------|-----------|
| **MUST** | Use `ubuntu-24.04-arm` for new workflows (37.5% cheaper) | [ADR-007](../.agents/architecture/ADR-007-github-actions-runner-selection.md) |
| **MUST** | Justify any Windows/macOS runner usage with ADR-007 comment | Document exception |
| **MUST** | Set artifact retention to minimum needed (1-7 days default) | [ADR-008](../.agents/architecture/ADR-008-artifact-storage-minimization.md) |
| **MUST** | Add path filters to prevent unnecessary workflow runs | Workflow template |
| **SHOULD** | Use `concurrency` to cancel duplicate runs | Workflow template |
| **SHOULD** | Upload debug artifacts only on failure (`if: failure()`) | Conditional upload |

### Cost-Related ADRs

All CI/CD changes MUST comply with these Architecture Decision Records:

- **[ADR-007: GitHub Actions Runner Selection](../.agents/architecture/ADR-007-github-actions-runner-selection.md)** - ARM-first policy
- **[ADR-008: Artifact Storage Minimization](../.agents/architecture/ADR-008-artifact-storage-minimization.md)** - No artifacts by default

### Verification

Cost efficiency is verified through:

1. **Workflow reviews**: PR reviewers check for ADR-007/ADR-008 compliance
2. **Monthly audits**: Review GitHub billing for cost creep
3. **Session reviews**: Check token usage patterns in Claude API dashboard

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

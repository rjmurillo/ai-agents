# Claude Code Instructions

## BLOCKING GATE: Session Protocol

> **Canonical Source**: [.agents/SESSION-PROTOCOL.md](.agents/SESSION-PROTOCOL.md)
>
> This file uses RFC 2119 key words. MUST = required, SHOULD = recommended, MAY = optional.

### Phase 1: Serena Initialization (BLOCKING)

You MUST NOT proceed to any other action until both calls succeed:

```text
1. mcp__serena__activate_project  (with project path)
2. mcp__serena__initial_instructions
```

**Verification**: Tool output appears in session transcript.

**If skipped**: You lack project memories, semantic code tools, and historical context.

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

**Full protocol with RFC 2119 requirements**: [.agents/SESSION-PROTOCOL.md](.agents/SESSION-PROTOCOL.md)

---

Refer to [AGENTS.md](AGENTS.md) for complete project instructions.

This file exists for Claude Code's auto-load behavior. All canonical agent documentation is maintained in `AGENTS.md` to follow the DRY principle.

## Quick Reference

- **Agent invocation**: `Task(subagent_type="agent_name", prompt="...")`
- **Memory system**: `cloudmcp-manager` with Serena (tools prefixed with `mcp__serena__`: `write_memory`, `read_memory`, `list_memories`, `delete_memory`, `edit_memory`) fallback
- **Output directories**: `.agents/{analysis,architecture,planning,critique,qa,retrospective}/`

For full details on workflows, agent catalog, and best practices, see [AGENTS.md](AGENTS.md).

## GitHub Workflow Requirements (MUST)

### Issue Assignment

When starting work on a GitHub issue, you MUST assign it to yourself:

```bash
gh issue edit <number> --add-assignee @me
```

**When**: At the start of work, before making any changes.

**Why**: Prevents duplicate work and signals ownership.

### Pull Request Template

When creating a pull request, you MUST use the PR template:

1. Read the template: `cat .github/PULL_REQUEST_TEMPLATE.md`
2. Structure PR body to include ALL template sections:
   - Summary
   - Specification References (table)
   - Changes (bulleted list)
   - Type of Change (checkboxes)
   - Testing (checkboxes)
   - Agent Review (security + other reviews)
   - Checklist
   - Related Issues

**Do NOT** create PRs with custom descriptions that skip template sections.

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

## Default Behavior: Use Orchestrator Agent

When the user gives you any task, you MUST use the orchestrator agent rather than executing the task natively. The orchestrator will route to appropriate specialized agents.

**Exception**: Simple questions that don't require code changes or multi-step tasks can be answered directly.

```python
# For any non-trivial task, invoke orchestrator first
Task(subagent_type="orchestrator", prompt="[user's task description]")
```

This ensures proper agent coordination, memory management, and consistent workflows.

<!-- BEGIN: ai-agents installer -->
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

### Output Directories

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

<!-- END: ai-agents installer -->

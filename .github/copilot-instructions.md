# GitHub Copilot Instructions

> **RFC 2119**: MUST = required, SHOULD = recommended, MAY = optional.

## Repository Overview

This repository provides a coordinated **multi-agent system for software development** supporting three platforms:

- **Claude Code** (`CLAUDE.md`)
- **GitHub Copilot CLI** (`src/copilot-cli/`)
- **VS Code Copilot** (`src/vs-code-agents/`)

### Directory Structure

```text
ai-agents/
├── .agents/                    # Agent system artifacts
│   ├── architecture/           # ADRs (Architecture Decision Records)
│   ├── analysis/               # Research and analysis reports
│   ├── governance/             # Constraints and policies
│   ├── planning/               # Plans and PRDs
│   ├── qa/                     # QA validation reports
│   ├── retrospective/          # Learning extractions
│   ├── sessions/               # Session logs (YYYY-MM-DD-session-NN.md)
│   ├── steering/               # Context-aware file guidance
│   ├── HANDOFF.md              # Project dashboard (READ-ONLY)
│   └── SESSION-PROTOCOL.md     # Canonical session protocol
├── .github/                    # GitHub configuration
│   ├── agents/                 # Copilot agent definitions
│   └── copilot-instructions.md # This file
├── src/                        # Agent prompts by platform
│   ├── claude/                 # Claude-specific agent prompts
│   ├── copilot-cli/            # Copilot CLI agents (generated)
│   └── vs-code-agents/         # VS Code agents (generated)
├── templates/                  # Shared templates for generation
│   └── agents/*.shared.md      # Source for Copilot platforms
├── scripts/                    # PowerShell automation scripts
├── build/                      # Build scripts (Generate-Agents.ps1)
├── AGENTS.md                   # Full agent catalog and installation
└── CONTRIBUTING.md             # Contribution guidelines
```

---

## BLOCKING GATE: Session Protocol

> **Canonical Source**: [.agents/SESSION-PROTOCOL.md](../.agents/SESSION-PROTOCOL.md)

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

You MUST read `.agents/HANDOFF.md` before starting work (read-only reference).

**Verification**: Content appears in session context; you reference prior decisions.

**If skipped**: You will repeat completed work or contradict prior decisions.

### Phase 3: Session Log (REQUIRED)

You MUST create session log at `.agents/sessions/YYYY-MM-DD-session-NN.md` early in session.

**Verification**: File exists with Protocol Compliance section.

### Phase 4: Branch Verification (BLOCKING)

You MUST verify the current branch before starting work:

```bash
git branch --show-current
```

**Verification**: Branch documented in session log; not on main/master.

### Session End (BLOCKING)

You CANNOT claim session completion until validation PASSES:

```bash
pwsh scripts/Validate-Session.ps1 -SessionLogPath ".agents/sessions/[session-log].md"
```

Before running validator, you MUST:

1. Complete Session End checklist in session log (all `[x]` checked)
2. Update Serena memory with cross-session context (NOT HANDOFF.md)
3. Run `npx markdownlint-cli2 --fix "**/*.md"`
4. Commit all changes including `.agents/` and `.serena/memories/` files
5. Record commit SHA in Session End checklist Evidence column

**IMPORTANT**: Do NOT update `.agents/HANDOFF.md` directly. Session context goes to session logs and Serena memory.

**Verification**: Validator exits with code 0 (PASS).

**If validation fails**: Fix violations and re-run validator. Do NOT claim completion.

**QA Validation Exemptions** (per ADR-034):

- Skip with `SKIPPED: docs-only` for documentation-only changes (no code, config, or test changes)
- Skip with `SKIPPED: investigation-only` for investigation sessions when only staging: `.agents/sessions/`, `.agents/analysis/`, `.agents/retrospective/`, `.serena/memories/`, `.agents/security/`

Session logs (`.agents/sessions/`) are automatically filtered from QA validation checks.

**Full protocol with RFC 2119 requirements**: [.agents/SESSION-PROTOCOL.md](../.agents/SESSION-PROTOCOL.md)

---

## Critical Constraints

> **Canonical Source**: [.agents/governance/PROJECT-CONSTRAINTS.md](../.agents/governance/PROJECT-CONSTRAINTS.md)

| Constraint | Source | Violation Response |
|------------|--------|-------------------|
| MUST use PowerShell only (.ps1/.psm1) | ADR-005 | No .sh or .py files |
| MUST NOT put logic in workflow YAML | ADR-006 | Logic goes in .psm1 modules |
| MUST use atomic commits (one logical change) | code-style-conventions | Max 5 files OR single topic |
| MUST verify branch before git operations | SESSION-PROTOCOL | Run `git branch --show-current` |

---

## Branch Operation Verification (MUST)

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

## MCP Servers

The project uses MCP servers for extended capabilities:

| Server | Transport | Purpose |
|--------|-----------|---------|
| **Serena** | stdio | Code analysis, project memory, symbol lookup |
| **Forgetful** | stdio | Semantic search, knowledge graph |
| **DeepWiki** | HTTP (`mcp.deepwiki.com/mcp`) | Documentation lookup |

### Serena (Project Memory)

```text
serena/activate_project  - Activate project context
serena/initial_instructions - Get project-specific instructions
serena/list_memories - List available memories
serena/read_memory - Read specific memory
serena/write_memory - Store cross-session context
serena/find_symbol - Find code symbols
```

### Forgetful (Semantic Memory)

All Forgetful tools use `execute_forgetful_tool(tool_name, arguments)` pattern:

```text
execute_forgetful_tool("create_memory", {...}) - Store memories with semantic embeddings
execute_forgetful_tool("query_memory", {...}) - Find memories by semantic similarity
execute_forgetful_tool("get_memory", {...}) - Retrieve specific memory by ID
execute_forgetful_tool("list_projects", {...}) - List all memory projects
execute_forgetful_tool("create_entity", {...}) - Create knowledge graph entities
execute_forgetful_tool("search_entities", {...}) - Search entities by name/type
```

> **Note**: Forgetful uses stdio transport with automatic installation via `uvx`. No manual service setup required.
>
> **Upstream Fix**: [Issue #19](https://github.com/ScottRBK/forgetful/issues/19) (FastMCP banner corruption) has been resolved.

---

## Architecture Decision Records (ADRs)

ADRs document significant technical decisions. Located in `.agents/architecture/`.

### Key ADRs

| ADR | Title | Impact |
|-----|-------|--------|
| ADR-005 | PowerShell-Only Scripting | No .sh or .py files allowed |
| ADR-006 | Thin Workflows, Testable Modules | Logic in .psm1, not YAML |
| ADR-007 | Memory-First Architecture | Always check memory before reasoning |
| ADR-014 | Distributed Handoff Architecture | Session logs replace centralized HANDOFF.md |
| ADR-034 | Investigation Session QA Exemption | When QA can be skipped |
| ADR-036 | Two-Source Agent Template Architecture | Claude vs shared templates |

### Two-Source Architecture (ADR-036)

**CRITICAL**: This project uses two sources for agent prompts:

1. **Claude-specific** (`src/claude/*.md`) - Manual edits only
2. **Shared templates** (`templates/agents/*.shared.md`) - Auto-generates Copilot platforms

When adding content for ALL platforms:

1. Edit `templates/agents/{agent}.shared.md` (generates Copilot CLI + VS Code)
2. Edit `src/claude/{agent}.md` (manual for Claude)

Pre-commit hook handles generation but NOT content sync between sources.

---

## Quick Reference

- **Agent invocation**: `@agent_name` in Copilot Chat or `#runSubagent with subagentType=agent_name`
- **Output directories**: `.agents/{analysis,architecture,planning,critique,qa,retrospective}/`

For full details on workflows, agent catalog, and best practices, see [AGENTS.md](../AGENTS.md).

---

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
| **pr-comment-responder** | PR review handler | Addressing bot/human review comments |

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

Agents use Serena and Forgetful MCP for cross-session memory:

**Serena** (project-specific memory):

- `serena/read_memory`: Read project memories
- `serena/write_memory`: Store cross-session context
- `serena/list_memories`: List available memories

**Forgetful** (semantic search, knowledge graph):

- `forgetful/memory_create`: Store memories with semantic embeddings
- `forgetful/memory_search`: Find memories by semantic similarity
- `forgetful/entity_create`: Create knowledge graph entities
- `forgetful/entity_search`: Search entities by name/type

> **Note**: Forgetful uses stdio transport with automatic installation via `uvx`. No manual service setup required.
>
> **Upstream Fix**: [Issue #19](https://github.com/ScottRBK/forgetful/issues/19) (FastMCP banner corruption) has been resolved.

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
| PR review comments | pr-comment-responder | - |

### Best Practices

1. **Memory First**: Retrieve context before multi-step reasoning
2. **Document Outputs**: Save artifacts to appropriate directories
3. **Clear Handoffs**: Announce next agent and purpose
4. **Store Learnings**: Update memory at milestones
5. **Follow Plans**: The plan document is authoritative
6. **Test Everything**: No skipping hard tests
7. **Commit Atomically**: Small, conventional commits

### Key Learnings

- **HANDOFF.md Is Read-Only**: Session context goes to session logs and Serena memory
- **QA Validation Required**: Route to qa agent after feature implementation
- **Branch Verification**: Always run `git branch --show-current` before commits

<!-- END: ai-agents installer -->

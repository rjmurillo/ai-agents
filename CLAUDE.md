# Claude Code Instructions

> **RFC 2119**: MUST = required, SHOULD = recommended, MAY = optional.

## BLOCKING GATE: Session Protocol

> **Canonical Source**: [.agents/SESSION-PROTOCOL.md](.agents/SESSION-PROTOCOL.md)

### Session Start (BLOCKING)

Complete ALL before any work:

| Req | Step | Verification |
|-----|------|--------------|
| MUST | `mcp__serena__activate_project` | Tool output in transcript |
| MUST | `mcp__serena__initial_instructions` | Tool output in transcript |
| MUST | Read `.agents/HANDOFF.md` (read-only reference) | Content in context |
| MUST | Create session log: `.agents/sessions/YYYY-MM-DD-session-NN.md` | File exists |
| MUST | List skills: `.claude/skills/github/scripts/` | Output documented |
| MUST | Read `skill-usage-mandatory` memory | Content in context |
| MUST | Read `.agents/governance/PROJECT-CONSTRAINTS.md` | Content in context |

### Session End (BLOCKING)

Complete ALL before closing:

| Req | Step | Verification |
|-----|------|--------------|
| MUST | Complete session log | All sections filled |
| MUST | Update Serena memory (cross-session context) | Memory write confirmed |
| MUST | Run `npx markdownlint-cli2 --fix "**/*.md"` | Lint clean |
| MUST | Route to qa agent (feature implementation) | QA report exists |
| MUST | Commit all changes (including `.serena/memories/`) | Commit SHA recorded |
| MUST NOT | Update `.agents/HANDOFF.md` | HANDOFF.md unchanged |

**Validation**: `pwsh scripts/Validate-SessionEnd.ps1 -SessionLogPath ".agents/sessions/[log].md"`

---

## Critical Constraints

> **Canonical Source**: [.agents/governance/PROJECT-CONSTRAINTS.md](.agents/governance/PROJECT-CONSTRAINTS.md)

| Constraint | Source | Violation Response |
|------------|--------|-------------------|
| MUST use PowerShell only (.ps1/.psm1) | ADR-005 | No .sh or .py files |
| MUST NOT use raw `gh` when skill exists | skill-usage-mandatory | Check `.claude/skills/` first |
| MUST NOT put logic in workflow YAML | ADR-006 | Logic goes in .psm1 modules |
| MUST use atomic commits (one logical change) | code-style-conventions | Max 5 files OR single topic |

---

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

## Document Hierarchy

Read these in order when starting work:

| Priority | Document | Purpose |
|----------|----------|---------|
| 1 | `.agents/SESSION-PROTOCOL.md` | Session start/end requirements |
| 2 | `.agents/HANDOFF.md` | Project status dashboard (read-only) |
| 3 | `.agents/governance/PROJECT-CONSTRAINTS.md` | Hard constraints |
| 4 | `.agents/AGENT-INSTRUCTIONS.md` | Task execution protocol |
| 5 | `.agents/AGENT-SYSTEM.md` | Full agent catalog (18 agents) |
| 6 | `AGENTS.md` | Installation and usage guide |

---

## Default Behavior: Use Orchestrator

For any non-trivial task, delegate to orchestrator:

```python
Task(subagent_type="orchestrator", prompt="[user's task description]")
```

**Exception**: Simple questions or single-file changes can be handled directly.

---

## Quick Reference

### Agent Invocation

```python
# Research before implementation
Task(subagent_type="analyst", prompt="Investigate [topic]")

# Design decisions
Task(subagent_type="architect", prompt="Review design for [feature]")

# Plan validation (REQUIRED before implementation)
Task(subagent_type="critic", prompt="Validate plan at .agents/planning/...")

# Implementation
Task(subagent_type="implementer", prompt="Implement [feature] per plan")

# Quality verification (REQUIRED after implementation)
Task(subagent_type="qa", prompt="Verify [feature]")

# Extract learnings
Task(subagent_type="retrospective", prompt="Analyze session for learnings")
```

### Common Workflows

| Scenario | Flow |
|----------|------|
| Quick fix | `implementer → qa` |
| Standard feature | `analyst → planner → critic → implementer → qa` |
| Strategic decision | `independent-thinker → high-level-advisor → task-generator` |
| Security-sensitive | `analyst → security → architect → critic → implementer → qa` |

### Memory System

```python
# Serena (preferred)
mcp__serena__list_memories()
mcp__serena__read_memory(memory_file_name="[name]")
mcp__serena__write_memory(memory_file_name="[name]", content="...")

# cloudmcp-manager (graph-based)
mcp__cloudmcp-manager__memory-search_nodes(query="[topic]")
mcp__cloudmcp-manager__memory-create_entities(entities=[...])
```

### Output Directories

| Directory | Agent | Purpose |
|-----------|-------|---------|
| `.agents/analysis/` | analyst | Research findings |
| `.agents/architecture/` | architect | ADRs, design decisions |
| `.agents/planning/` | planner | PRDs, plans |
| `.agents/critique/` | critic | Plan reviews |
| `.agents/qa/` | qa | Test reports |
| `.agents/retrospective/` | retrospective | Learnings |
| `.agents/sessions/` | all | Session logs |

---

## Skill System

Before GitHub operations, check for existing skills:

```powershell
Get-ChildItem -Path ".claude/skills/github/scripts" -Recurse -Filter "*.ps1"
```

**Skill locations**:

- PR operations: `.claude/skills/github/scripts/pr/`
- Issue operations: `.claude/skills/github/scripts/issue/`
- Reactions: `.claude/skills/github/scripts/reactions/`

**Rule**: If a skill exists, use it. If missing, ADD to skill library (don't write inline).

---

## Steering System

Steering files provide context-aware guidance based on file patterns:

| Steering File | Applies To | Purpose |
|---------------|------------|---------|
| `security-practices.md` | `**/Auth/**`, `*.env*` | Security requirements |
| `agent-prompts.md` | `src/claude/**/*.md` | Agent prompt standards |
| `testing-approach.md` | `**/*.Tests.ps1` | Pester testing conventions |
| `powershell-patterns.md` | `**/*.ps1`, `**/*.psm1` | PowerShell patterns |

Location: `.agents/steering/`

---

## Key Learnings

### HANDOFF.md Is Read-Only (v1.4)

- **DO NOT** update HANDOFF.md during sessions
- **DO** write session context to session logs
- **DO** use Serena memory for cross-session context
- **Reason**: HANDOFF.md grew to 35K tokens with 80%+ merge conflict rate

### QA Validation Is Required

- Route to qa agent after feature implementation
- Skip with `SKIPPED: docs-only` for documentation-only changes (no code, config, or test changes)
- Skip with `SKIPPED: investigation-only` for investigation sessions (per ADR-034) when only staging: `.agents/sessions/`, `.agents/analysis/`, `.agents/retrospective/`, `.serena/memories/`, `.agents/security/`

### Skill Violations Are Protocol Failures

- Session 15 had 5+ skill violations despite documentation
- Phase 1.5 skill validation gate now enforces compliance

---

## Emergency Recovery

| Problem | Solution |
|---------|----------|
| Lost context | Read `.agents/sessions/` logs |
| Unclear next step | Re-read `.agents/HANDOFF.md` dashboard |
| Linting fails | `npx markdownlint-cli2 --fix "**/*.md"` |
| Git issues | `git log --oneline -5` for recent commits |
| Protocol violation | Acknowledge, complete missed step, document |

---

For complete documentation, see [AGENTS.md](AGENTS.md).

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

<!-- END: ai-agents installer -->

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
- Skip only for documentation-only changes (no code, config, or test changes)

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

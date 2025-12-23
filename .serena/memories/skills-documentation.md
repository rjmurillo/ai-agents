# Documentation Skills

**Created**: 2025-12-20
**Updated**: 2025-12-23 (consolidated from 4 atomic memories)
**Sources**: Various retrospectives and PR reviews
**Skills**: 7 (001-007)

---

## Skill-Documentation-001: Systematic Migration Search

**Statement**: Search entire codebase for pattern before migration to identify all references

**Context**: Before starting any documentation or code pattern migration

**Evidence**: Session 26 (2025-12-18): Grep search identified 16 files with .serena/memories/ references

**Atomicity**: 95% | **Impact**: 8/10 | **Tag**: helpful

**Search Pattern**:

```bash
# Step 1: Define search pattern
grep -r ".serena/memories/" --include="*.md"
grep -r "mcp__cloudmcp-manager__" --include="*.md"

# Step 2: Analyze scope - count files, categorize by type, identify edge cases
# Step 3: Create migration checklist before making changes
```

**Anti-Pattern**: Starting migration without comprehensive search; updating files one by one as you find them.

---

## Skill-Documentation-002: Reference Type Taxonomy

**Statement**: Categorize references as instructive (update), informational (skip), or operational (skip) before migration

**Context**: After identifying references, before making changes

**Evidence**: Session 26: Type distinction prevented inappropriate updates to git commands and historical logs

**Atomicity**: 95% | **Impact**: 9/10 | **Tag**: helpful

**Taxonomy**:

| Type | Definition | Action | Example |
|------|------------|--------|---------|
| **Instructive** | Instructions telling agents what to do | UPDATE | "MUST read .serena/memories/..." |
| **Informational** | Descriptive text about locations | SKIP | "Memories found in `.serena/memories/`" |
| **Operational** | Commands requiring file paths | SKIP | "git add .serena/memories/" |

---

## Skill-Documentation-003: Fallback Preservation

**Statement**: Include fallback clause when migrating to tool calls for graceful degradation

**Context**: When abstracting direct file access to tool calls

**Evidence**: Session 26: 5 fallback clauses added during Serena memory reference migration

**Atomicity**: 96% | **Impact**: 9/10 | **Tag**: helpful

**Pattern**:

```markdown
Read [memory-name] using `mcp__serena__read_memory` with `memory_file_name="[memory-name]"`
  - If Serena MCP not available, read `.serena/memories/[memory-name].md`
```

**Anti-Pattern**: Tool-only reference without fallback path.

---

## Skill-Documentation-004: Pattern Consistency

**Statement**: Use identical syntax for all instances when migrating patterns

**Context**: During migration execution across multiple files

**Evidence**: Session 26: All tool call references use same format across 16 files

**Atomicity**: 96% | **Impact**: 8/10 | **Tag**: helpful

**Canonical Pattern**:

```markdown
Read {name} memory using `mcp__serena__read_memory` with `memory_file_name="{name}"`
  - If the Serena MCP is not available, then read `.serena/memories/{name}.md`
```

**Why**: One pattern to learn, single grep finds all instances, future changes need one template.

---

## Skill-Documentation-005: User-Facing Content Restrictions

**Statement**: Exclude internal PR/Issue/Session references from src/ and templates/ directories

**Context**: When creating or updating user-facing documentation

**Evidence**: PR #212 - User policy request, 6 files updated

**Atomicity**: 92% | **Impact**: 9/10 | **Tag**: critical

**Scope**: `src/claude/`, `src/copilot-cli/`, `src/vs-code-agents/`, `templates/agents/`

**Prohibited**:
- `PR #XXX`, `Issue #XXX`, `Session XX`
- `.agents/`, `.serena/` paths

**Permitted**: CWE, RFC, generic patterns

**Validation**:

```bash
grep -r "PR #\|Issue #\|Session \d\+\|\.agents/\|\.serena/" src/ templates/
# Should return no matches
```

---

## Skill-Documentation-006: Self-Contained Operational Prompts

**Statement**: Include all resource constraints, failure modes, shared resource context, and dynamic adjustment rules for autonomous agents

**Context**: Prompts intended for standalone Claude instances or autonomous agents

**Evidence**: PR #301 - Rate limit guidance missing from autonomous-pr-monitor.md

**Atomicity**: 88% | **Impact**: 9/10 | **Tag**: operational

**Required Sections**:

1. **Resource Constraints**: API limits, shared resources, budget targets
2. **Failure Modes**: Detection and recovery for each failure type
3. **Dynamic Adjustments**: Condition → Action rules
4. **Shared Context**: What else uses these resources
5. **Stop Conditions**: When to self-terminate

**Validation Questions**:
1. "If I had amnesia, could I operate correctly?"
2. "What do I know that the next agent won't?"
3. "What resources am I consuming? Who else uses them?"
4. "Is this sustainable if it runs forever?"

---

## Skill-Documentation-007: Self-Contained Artifacts (General Principle)

**Statement**: Any artifact consumed by a future agent MUST be self-contained enough for that agent to succeed without implicit knowledge

**Context**: Session logs, handoff artifacts, PRDs, task breakdowns, planning documents

**Evidence**: PR #301 - User feedback generalized validation questions

**Atomicity**: 95% | **Impact**: 10/10 | **Tag**: critical (foundational)

**Universal Validation Questions**:

| # | Question | Applies To |
|---|----------|------------|
| 1 | "If I had amnesia and only had this document, could I succeed?" | All artifacts |
| 2 | "What do I know that the next agent won't?" | All artifacts |
| 3 | "What implicit decisions am I making that should be explicit?" | All artifacts |

**Artifact-Specific Extensions**:

| Artifact Type | Additional Questions |
|---------------|---------------------|
| Session Logs | End state? Blocked? Next action? |
| Handoff Artifacts | Decisions made? What was rejected? |
| PRDs | Acceptance criteria unambiguous? |
| Task Breakdowns | Tasks atomic? Dependencies explicit? |
| Operational Prompts | See Skill-Documentation-006 |

**Anti-Patterns**:

```markdown
# BAD: Implicit state
Worked on PR #301. Made good progress. Will continue tomorrow.

# GOOD: Explicit state
Worked on PR #301:
- Completed: Rate limit management section
- Blocked: Waiting for CI (run 12345)
- Next action: Address review comments
```

---

## Quick Reference

| Skill | When to Use |
|-------|-------------|
| 001 | Before any migration - search first |
| 002 | Categorize references before changing |
| 003 | Add fallback when abstracting to tools |
| 004 | Use identical syntax across all files |
| 005 | User-facing content - no internal refs |
| 006 | Autonomous prompts - include constraints |
| 007 | All artifacts - self-containment test |

## Related Memory

- `user-facing-content-restrictions` (policy reference for 005)

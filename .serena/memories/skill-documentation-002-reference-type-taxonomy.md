# Skill-Documentation-002: Reference Type Taxonomy

## Statement

Categorize references as instructive (update), informational (skip), or operational (skip) before migration

## Context

After identifying references, before making changes

## Evidence

Session 26 (2025-12-18): Type distinction prevented inappropriate updates to git commands and historical logs during Serena memory reference migration

## Metrics

- Atomicity: 95%
- Impact: 9/10
- Category: documentation-maintenance, migration, taxonomy
- Created: 2025-12-18
- Tag: helpful
- Validated: 1

## Related Skills

- Skill-Documentation-001 (Systematic Migration Search)
- Skill-Documentation-003 (Fallback Preservation)

## Reference Type Taxonomy

### 1. Instructive References (UPDATE)

**Definition**: Instructions telling agents what to do

**Pattern**: Imperative language, protocol requirements

**Examples**:
```markdown
The agent MUST read .serena/memories/skill-usage-mandatory.md
→ UPDATE TO: Use mcp__serena__read_memory with memory_file_name="skill-usage-mandatory"

Before proceeding, reference .serena/memories/skills-design.md
→ UPDATE TO: Read skills-design memory using mcp__serena__read_memory
```

### 2. Informational References (SKIP)

**Definition**: Descriptive text about file locations

**Pattern**: Explanatory language, documentation of structure

**Examples**:
```markdown
Memories can be found in `.serena/memories/`
→ SKIP: Describes location, not instruction

The skillbook is stored at .serena/memories/skills-*.md
→ SKIP: Documents pattern, not actionable
```

### 3. Operational References (SKIP)

**Definition**: Commands requiring actual file paths

**Pattern**: Git commands, file system operations

**Examples**:
```markdown
git add .serena/memories/
→ SKIP: Git requires actual path

ls .serena/memories/*.md
→ SKIP: File system operation
```

## Decision Flowchart

```text
Is this reference...

...an instruction to agents? → YES → Instructive (UPDATE)
...describing file structure? → YES → Informational (SKIP)
...a git/file command? → YES → Operational (SKIP)
...unclear? → Analyze context, apply principle: "Does pattern matter for execution?"
```

## Success Criteria

- All references categorized before migration starts
- Instructive references updated to new pattern
- Informational references preserved (document location)
- Operational references preserved (require literal paths)
- No inappropriate updates to git commands or historical logs

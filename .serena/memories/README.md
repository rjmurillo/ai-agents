# Memory System Guidelines

## Directory Structure

Memories are organized into topic subdirectories to reduce `list_memories` token overhead.

**Top-level** (visible in `list_memories`): Index files and special files only.

**Subdirectories** (hidden from `list_memories`, readable via path): All atomic memories.

### Reading Memories

```python
# Step 1: list_memories shows only indexes
# Step 2: read_memory("skills-pr-review-index") to find the right memory
# Step 3: read_memory("pr-review/pr-review-001-reviewer-enumeration") to read it
```

### Writing New Memories

1. Determine the topic subdirectory (use existing ones when possible)
2. Write to `{subdirectory}/{memory-name}.md`
3. Update the relevant `*-index.md` with the path-prefixed reference

| Subdirectory | Domain |
|--------------|--------|
| `pr-review/` | PR review patterns, anti-patterns, workflows |
| `ci/` | CI/CD, infrastructure, DevOps |
| `git/` | Git operations, hooks, merge |
| `security/` | Security patterns, OWASP, CWE |
| `skills/` | Skill observations, patterns |
| `knowledge/` | Engineering concepts, laws, frameworks |
| `architecture/` | Architecture decisions, patterns |
| `workflow/` | GitHub Actions, workflow patterns |
| `session/` | Session protocol, init, logging |
| `quality/` | Code quality, testing, DoD |
| See subdirectories for full list | `ls .serena/memories/` |

### Index File Format

Index files at top level use path-prefixed references:

```markdown
| Keywords | File |
|----------|------|
| keyword1 keyword2 | [subdir/memory-name](subdir/memory-name.md) |
```

## Size Constraints

Memory files must stay within atomicity thresholds to support progressive disclosure and minimize token waste.

| Metric | Threshold | Rationale |
|--------|-----------|-----------|
| Characters | 10,000 max | ~2,500 tokens, single retrieval budget |
| Skills (H2 sections) | 15 max | One retrievable concept per file |
| Categories (H1 sections) | 5 max | Domain focus, prevents sprawl |

Source: `memory-size-001-decomposition-thresholds.md`

## When to Decompose

A memory file needs decomposition when:

- Character count exceeds 10,000
- It covers multiple unrelated domains
- You find yourself retrieving the whole file to access one section

## How to Decompose

1. Create an **index file** (`{topic}-index.md`) with a keyword-to-file lookup table
2. Split content into **focused sub-files** (`{topic}-{subtopic}.md`)
3. Update `memory-index.md` to reference the new index file
4. Remove the monolithic original

Index file format:

```markdown
| Keywords | File |
|----------|------|
| keyword1 keyword2 | [subtopic-name](subtopic-name.md) |
```

## Validation Tooling

```bash
# Validate a single file
python3 .claude/skills/memory/scripts/test_memory_size.py .serena/memories/my-memory.md

# Validate all memories
python3 .claude/skills/memory/scripts/test_memory_size.py .serena/memories --pattern "*.md"

# Count tokens for a file
python3 .claude/skills/memory/scripts/count_memory_tokens.py .serena/memories/my-memory.md
```

The pre-commit hook enforces these thresholds automatically:
- **New files**: blocked if oversized
- **Modified files**: warned if oversized

## Token Cost Visibility

Token counts appear inline in `memory-index.md` as `(N)` after each link. These are auto-updated by the pre-commit hook when memory files change.

## Quarterly Curation Process

Run every quarter (Jan, Apr, Jul, Oct) to keep the memory system healthy.

**Step 1: Generate health report**

```bash
python3 scripts/memory/memory_health.py
```

**Step 2: Run stale detector**

```bash
python3 scripts/memory/detect_stale.py .serena/memories
```

**Step 3: Review and act**

| Finding | Action |
|---------|--------|
| Stale (>6 months) | Archive or update with current information |
| Broken memory links | Fix references or remove dead links |
| Broken code references | Update paths or remove stale references |
| Oversized files | Decompose per "How to Decompose" above |
| Near-duplicate content | Merge into single authoritative memory |

**Step 4: Document results**

Create a retrospective memory documenting changes made, files archived, and metrics delta.

## Related

- `memory/memory-size-001-decomposition-thresholds.md` - Threshold rationale and history
- `memory/memory-token-efficiency.md` - Token cost analysis patterns
- `memory/context-engineering-principles.md` - Progressive disclosure architecture

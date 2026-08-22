# Integration, Design Decisions, Extension Points (Detailed)

SKILL.md points here for integration patterns (session protocol, memory skill,
Serena), design-decision rationale, extension points, related skills, and the
commit convention for skill observation updates.

## Integration

### With Session Protocol

Run reflection at session end as part of retrospective:

```text
## Session End Checklist
- [ ] Update the per-issue handoff
- [ ] Run skill reflection (if skills were used)
- [ ] Update Serena memory
- [ ] Commit changes
```

### With Memory Skill

Skill memories integrate with the memory system:

```bash
# Search skill sidecar learnings
python3 .claude/skills/memory/scripts/search_memory.py --query "github-observations constraints"

# Read specific skill sidecar
Read .serena/memories/github/github-observations.md
```

### With Serena

If Serena MCP is available:

```text
mcp__serena__read_memory(memory_file_name="github/github-observations")
mcp__serena__write_memory(memory_file_name="github/github-observations", memory_content="...")
```

## Design Decisions

### Agent Sidecar Naming: `{skill-name}-observations.md`

**Decision**: Skill memories follow the ADR-007 sidecar pattern (e.g., `github-observations.md`).

**Rationale**:

- **ADR-007 Alignment**: Reuses the agent sidecar convention instead of inventing a parallel structure
- **ADR-017 Compliance**: Keeps `{domain}-{description}` format while making "skill-sidecar" explicit
- **Discovery**: Sidecars are now referenced in `memory-index.md`, preventing orphaned learnings
- **Single Canonical Store**: Serena MCP and Git both write to the same file path, eliminating dual-governance ambiguity

**Migration**: Rename `{skill}-observations.md` (or legacy `skill-{name}.md`) to `{skill}-observations.md` and update index references.

### Serena vs Forgetful Roles

- **Serena MCP** remains the canonical record. Every learning is persisted to the `{skill}-observations.md` file.
- **Forgetful** is optional and used for semantic lookup only. When storing supporting context, tag the entry with `skill-{name}` and reference the Serena sidecar instead of duplicating the content.

### Relationship to `curating-memories`

- `curating-memories` = general-purpose maintenance of any memory artifact (linking, pruning, marking obsolete).
- `reflect` = targeted retrospective that feeds those artifacts with new learnings.
- When a sidecar accumulates conflicting guidance, route the file to `curating-memories` for cleanup.

### Durable Continuity Integration

- Add "Run skill reflection if ≥3 distinct skills used" to the optional Session End checklist.
- Manual sidecar edits are self-recording in Git; preserve non-obvious rationale in the commit or PR.
- Invoke reflect immediately after the Stop hook highlights high-confidence learnings so the sidecar is durable before the session ends.

## Extension Points

1. **Curating memories**: route conflicting or stale learnings to `curating-memories` for consolidation.
2. **Memory skill**: use `memory` skill for search/recall before proposing redundant learnings.
3. **Forgetful**: optionally mirror high-confidence learnings into Forgetful with `skill-{name}` tags for semantic recall.
4. **Git and PR history**: preserve non-obvious rationale for manual sidecar edits in the change that carries them.

## Related

| Skill | Relationship |
|-------|--------------|
| `memory` | Skill memories are part of Tier 1 |
| `using-forgetful-memory` | Alternative storage for skill learnings |
| `curating-memories` | For maintaining/pruning skill memories |
| `retrospective` | Full session retrospective (this is mini version) |

## Commit Convention

When committing skill observation updates:

```text
chore(memory): update {skill-name} skill sidecar learnings (session {N})

- Added {count} constraints (HIGH confidence)
- Added {count} preferences (MED confidence)
- Added {count} edge cases (MED confidence)
- Added {count} notes (LOW confidence)

Session: {session-id}
```

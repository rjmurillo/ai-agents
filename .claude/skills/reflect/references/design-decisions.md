# Reflect Design Decisions and Extension Points

Rationale behind the sidecar model. Load when changing reflect's storage or naming.

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

### Session Protocol Integration

- Add "Run skill reflection if ≥3 distinct skills used" to the Session End checklist.
- Document any manual sidecar edits (when Serena MCP is unavailable) in the session log before completion.
- Invoke reflect immediately after the Stop hook highlights high-confidence learnings so the session log and sidecar stay in sync.

---

## Extension Points

1. **Curating memories** – route conflicting or stale learnings to `curating-memories` for consolidation.
2. **Memory skill** – use `memory` skill for search/recall before proposing redundant learnings.
3. **Forgetful** – optionally mirror high-confidence learnings into Forgetful with `skill-{name}` tags for semantic recall.
4. **Session log fixer** – after reflection, ensure the session log captures the learning summary via `session-log-fixer`.


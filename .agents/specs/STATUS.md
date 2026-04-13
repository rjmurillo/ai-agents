# Specifications Status

**Last Updated**: 2026-01-21
**Total Specs**: 7

---

## Quick Status View

| Spec | Status | Tracking | Implementation |
|------|--------|----------|----------------|
| [PRD-memory-enhancement-layer-for-serena-forgetful.md](./PRD-memory-enhancement-layer-for-serena-forgetful.md) | 🟢 Active (v0.3.0) | [#990](https://github.com/rjmurillo/ai-agents/issues/990) | Planned |
| [agent-orchestration-mcp-spec.md](./agent-orchestration-mcp-spec.md) | 🔵 Draft | TBD | Not Started |
| [session-state-mcp-spec.md](./session-state-mcp-spec.md) | 🔵 Draft | TBD | Not Started |
| [skill-catalog-mcp-spec.md](./skill-catalog-mcp-spec.md) | 🔵 Draft | TBD | Not Started |
| [SPEC-local-guardrails.md](./SPEC-local-guardrails.md) | 🔵 Draft | TBD | Not Started |
| [mcp-integration-overview.md](./mcp-integration-overview.md) | 🟢 Reference | N/A | N/A (Overview) |
| [README.md](./README.md) | 🟢 Active | N/A | N/A (Index) |

---

## Status Legend

| Icon | Status | Meaning |
|------|--------|---------|
| 🟢 | Active | Under active development or implementation |
| 🔵 | Draft | Proposal stage, no implementation started |
| 🟡 | Implemented | Completed and operational |
| 🔴 | Superseded | Replaced by newer spec or ADR |
| 📚 | Reference | Documentation/overview only |

---

## Specifications by Type

### Product Requirements (PRDs)

**Purpose**: High-level feature descriptions with user stories and success metrics

| Spec | Status | Target Version |
|------|--------|----------------|
| [PRD-memory-enhancement-layer-for-serena-forgetful.md](./PRD-memory-enhancement-layer-for-serena-forgetful.md) | 🟢 Active | v0.3.0 |

### Technical Specifications

**Purpose**: Detailed technical designs and APIs

| Spec | Status | Related Issues |
|------|--------|----------------|
| [agent-orchestration-mcp-spec.md](./agent-orchestration-mcp-spec.md) | 🔵 Draft | TBD |
| [session-state-mcp-spec.md](./session-state-mcp-spec.md) | 🔵 Draft | TBD |
| [skill-catalog-mcp-spec.md](./skill-catalog-mcp-spec.md) | 🔵 Draft | TBD |
| [SPEC-local-guardrails.md](./SPEC-local-guardrails.md) | 🔵 Draft | TBD |

### Documentation

**Purpose**: Overview and index documents

| Doc | Purpose |
|-----|---------|
| [mcp-integration-overview.md](./mcp-integration-overview.md) | MCP integration strategy overview |
| [README.md](./README.md) | Specifications directory index |
| [STATUS.md](./STATUS.md) | This file - spec status tracker |

---

## Implementation Roadmap

### v0.2.0 (Shipped)
- Pre-PR validation system (Epic #265)
- Session protocol enforcement
- CI/CD quality gates

### v0.3.0 (Planned)
- Memory Enhancement Layer (Epic #990)
  - Citation schema & verification
  - Graph traversal
  - Staleness detection
  - Confidence scoring

### Future (Backlog)
- Agent Orchestration MCP
- Session State MCP
- Skill Catalog MCP
- Local Guardrails

---

## Naming Conventions

### PRDs (Product Requirements)
- Format: `PRD-{feature-name}.md`
- Example: `PRD-memory-enhancement-layer-for-serena-forgetful.md`
- Contains: Problem statement, goals, user stories, success metrics

### Technical Specs
- Format: `{domain}-{component}-spec.md` or `SPEC-{feature}.md`
- Example: `agent-orchestration-mcp-spec.md`, `SPEC-local-guardrails.md`
- Contains: Technical design, APIs, data models, integration points

### Documentation
- Format: `{topic}.md` or `README.md`
- Example: `mcp-integration-overview.md`
- Contains: High-level overviews, indexes, guidance

---

## Adding New Specifications

1. **Choose type**: PRD for features, SPEC for technical designs
2. **Follow naming**: Use conventions above
3. **Add frontmatter**: Include status, author, dates, tracking issue
4. **Update STATUS.md**: Add entry to appropriate table
5. **Create tracking issue**: Link GitHub issue for implementation
6. **Add to README.md**: Update main specs index

---

## Archiving Specifications

When a spec is completed or superseded:

1. Update status in this file (🟡 Implemented or 🔴 Superseded)
2. Add "Implemented in: [PR/ADR link]" to spec frontmatter
3. For superseded specs, add "Superseded by: [link]"
4. Keep in this directory (do not archive) unless obsolete

---

## Related Documentation

- [`.agents/planning/`](../planning/) - Implementation plans and task breakdowns
- [`.agents/architecture/`](../architecture/) - Architecture Decision Records (ADRs)
- [`.agents/archive/`](../archive/) - Historical documentation

---

**Questions?** See [README.md](./README.md) or create a GitHub issue.

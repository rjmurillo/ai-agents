# Design Review: skill-reflect

**Reviewer**: Architect
**Date**: 2026-01-13
**Status**: NEEDS_CHANGES
**Priority**: P1 (Blocking - memory architecture conflict)

## Executive Summary

The skill-reflect capability proposes a mini-retrospective system for analyzing skill usage and updating skill-based memories. The concept aligns with memory-first architecture (ADR-007), but the implementation creates architectural conflicts with the established memory hierarchy and introduces maintenance burden.

**Verdict**: NEEDS_CHANGES

**Severity**: P1 (Blocking)

## Architectural Conflicts

### 1. Memory Tier Violation (BLOCKING)

**Issue**: Proposes `.serena/memories/skill-{name}.md` as parallel memory structure outside established tiering system.

**Current Architecture** (ADR-007 + ADR-017 Tiered Index):

```text
.serena/memories/
├── memory-index.md                    # Tier 1: Master index
├── skills-github-index.md             # Tier 2: Domain index
├── skills-github-pr-operations.md     # Tier 3: Skill cluster
└── pr-review-011-security.md          # Tier 4: Atomic memory
```

**Proposed Architecture** (skill-reflect):

```text
.serena/memories/
├── skill-github.md                    # NEW: Parallel to existing tiers
└── [existing tier structure]
```

**Conflict**: Creates orphaned memories that bypass the index system. These memories:

- Will not appear in `memory-index.md`
- Will not be discovered by tier-based routing
- Create confusion with existing `skills-{domain}-index.md` files
- Violate principle of single canonical location

**Impact**: Memory fragmentation, discovery failures, index inconsistency.

### 2. Dual Memory Governance Ambiguity

**ADR-007 establishes**:

| System | Role | Persistence |
|--------|------|-------------|
| Serena | Canonical | Git-synchronized markdown |
| Forgetful | Supplementary | Local SQLite (semantic search) |

**skill-reflect proposes**: "Works whether Serena MCP is available or not (git fallback)"

**Questions**:

1. If Serena unavailable, where is fallback location?
2. How does this integrate with Forgetful's knowledge graph?
3. Should skill learnings be atomic memories in Forgetful instead?
4. Is this duplicating `curating-memories` skill functionality?

**Recommendation**: Clarify whether skill learnings should be:

- **Option A**: Atomic memories in Forgetful with `skill-{name}` tag
- **Option B**: Section within existing Tier 3 memory (e.g., `skills-github-index.md`)
- **Option C**: Agent sidecar pattern (ADR-007 Section "BMAD-Inspired Enhancements")

### 3. Agent Sidecar Pattern Ignored

**ADR-007 Section "Sidecar Naming Convention"** defines:

```text
Format: {agent}-sidecar-{descriptor}.md
Location: .serena/memories/
Purpose: Agent-specific learned patterns

Examples:
- orchestrator-sidecar-routing-patterns.md
- implementer-sidecar-code-patterns.md
```

**skill-reflect should align**: Skills ARE agent behaviors. Skill learnings ARE agent-specific patterns.

**Proposal**: Rename to agent sidecar pattern:

```text
skill-github → github-skill-sidecar-learnings.md
skill-memory → memory-skill-sidecar-learnings.md
```

**Benefits**:

- Aligns with ADR-007 established pattern
- Makes agent ownership explicit
- Consistent with BMAD Method integration
- Preserves Git synchronization

## Positive Aspects

### 1. Memory-First Alignment

Strong alignment with ADR-007 principle:

> "Memory retrieval MUST precede reasoning in all agent workflows"

The skill provides structured retrospective analysis, which is exactly the feedback loop needed for memory evolution (A-MEM research reference in ADR-007).

### 2. Confidence-Based Categorization

The HIGH/MED/LOW confidence levels map well to Forgetful's importance scoring:

| Confidence | Forgetful Importance | Rationale |
|------------|---------------------|-----------|
| HIGH (corrections) | 8-9 | User explicitly rejected behavior |
| MED (success/edge) | 7-8 | Validated patterns, discovered gaps |
| LOW (preferences) | 6-7 | Emerging patterns needing validation |

### 3. Zettelkasten Principles

The skill documentation demonstrates atomicity:

- One concept per section
- Clear trigger phrases
- Explicit workflow steps
- Decision tree for routing

Aligns with ADR-007 Zettelkasten principles.

### 4. Integration Points

Good integration mapping with existing skills:

- `memory` - Tier 1 search
- `using-forgetful-memory` - Create/update operations
- `curating-memories` - Maintenance operations

## Architectural Recommendations

### R1: Use Agent Sidecar Pattern (BLOCKING)

**Change**: Rename memory files from `skill-{name}.md` to `{name}-skill-sidecar-learnings.md`

**Rationale**: Aligns with ADR-007 Section "Sidecar Naming Convention"

**Example**:

```text
BEFORE: .serena/memories/skill-github.md
AFTER:  .serena/memories/github-skill-sidecar-learnings.md
```

**Implementation**:

1. Update SKILL.md storage location references
2. Update examples to use sidecar naming
3. Add reference to ADR-007 sidecar section

### R2: Integrate with Tiered Index (BLOCKING)

**Change**: Sidecars MUST be referenced in `memory-index.md`

**Add to Tier 1 index**:

```markdown
## Agent Sidecars

Skill-specific learned patterns (per ADR-007 BMAD pattern):

- [[github-skill-sidecar-learnings]] - GitHub skill constraints, edge cases, preferences
- [[memory-skill-sidecar-learnings]] - Memory skill patterns
```

**Rationale**: Maintains single source of truth for memory discovery.

### R3: Clarify Forgetful Integration

**Change**: Add section to SKILL.md:

```markdown
## Storage Strategy

### Serena (Canonical)
- Location: `.serena/memories/{skill-name}-skill-sidecar-learnings.md`
- Purpose: Cross-platform, Git-synchronized
- Format: Markdown with timestamped sections

### Forgetful (Supplementary)
- Use: Semantic search for related patterns
- Tag: `skill-{name}`
- Do NOT duplicate: Serena is canonical source
```

**Rationale**: Eliminates dual-governance ambiguity per ADR-007.

### R4: Avoid Duplication with curating-memories

**Observation**: `curating-memories` skill already handles:

- Updating outdated memories
- Marking obsolete content
- Linking related knowledge

**Question**: Is skill-reflect a specialized workflow for the subset of memories tagged `skill-{name}`?

**Recommendation**: Add to SKILL.md:

```markdown
## Relationship to curating-memories

skill-reflect is a **specialized workflow** for skill-specific memories:

- curating-memories: General memory maintenance (all memories)
- skill-reflect: Skill-focused retrospective (skill sidecars only)

Both use same underlying operations (update_memory, link_memories, mark_obsolete).
```

### R5: Define Session Protocol Integration

**Missing**: How does this integrate with SESSION-PROTOCOL.md?

**Add to SKILL.md**:

```markdown
## Session Protocol Integration

### Session End Checklist (Enhancement)

```markdown
- [ ] Complete session log
- [ ] **Run skill reflection if skills heavily used** (NEW)
- [ ] Update Serena memory
- [ ] Commit changes
```

**Trigger**: If session log shows >3 skill invocations, proactively offer reflection.
```

**Rationale**: Makes skill part of standard workflow, not ad-hoc.

## Design Strengths

1. **Clear triggers**: Explicit phrases and context for invocation
2. **Confidence levels**: Maps user corrections to memory importance
3. **Non-destructive**: Append-only with timestamps preserves history
4. **User approval**: Shows changes before applying (good UX)
5. **Commit convention**: Structured commit messages for memory updates

## Design Weaknesses

1. **Tier bypass**: Creates parallel memory structure outside index
2. **Naming conflict**: `skill-{name}.md` collides with sidecar pattern
3. **Forgetful ambiguity**: Unclear when to use Serena vs Forgetful
4. **Duplication risk**: Overlaps with `curating-memories` functionality
5. **No session integration**: Missing protocol hooks

## Anti-Pattern Detection

### Pattern: Memory Fragmentation

**Warning Sign**: New memory location outside established hierarchy.

**Historical Example**: Before ADR-017 Tiered Index, memories were scattered and undiscoverable.

**Mitigation**: Force all memories through `memory-index.md` routing.

### Pattern: Feature Overlap

**Warning Sign**: Skill proposes functionality that existing skill already provides.

**Mitigation**: Define relationship to `curating-memories` explicitly.

## Verdict Details

### NEEDS_CHANGES (P1 - Blocking)

**Required Changes**:

1. [R1] Rename to agent sidecar pattern (BLOCKING)
2. [R2] Add to memory-index.md (BLOCKING)
3. [R3] Clarify Serena vs Forgetful usage (BLOCKING)
4. [R4] Document relationship to curating-memories (Required)
5. [R5] Define session protocol integration (Required)

**Acceptance Criteria**:

- [ ] No new memory files outside `memory-index.md` routing
- [ ] Sidecar naming convention followed
- [ ] ADR-007 dual memory governance clarified
- [ ] No functional duplication with existing skills
- [ ] Session protocol integration documented

**Timeline**: Fix before merging to main. This is a P1 blocking issue.

## Chesterton's Fence Analysis

**Q**: Why does ADR-007 establish a tiered index system?

**A** (from memory search):

- Prevents memory fragmentation (pre-ADR-017 problem)
- Enables progressive disclosure (read index, then specific memories)
- Maintains single source of truth for discovery
- Supports both human and agent navigation

**Proposed Change**: skill-reflect bypasses this system.

**Investigation Required**: Is there a reason the tier system won't work for skill learnings?

**Recommendation**: No. Skill learnings fit the agent sidecar pattern (Tier 3 in the hierarchy). Use existing system.

## Path Dependence Considerations

**Historical Context**:

1. Before ADR-007: No memory system, repeated discoveries
2. ADR-007: Introduced Serena as canonical + Forgetful as supplementary
3. ADR-017: Added tiered index to prevent fragmentation
4. Now: skill-reflect proposes parallel structure

**Constraint Recognition**: We are path-dependent on tiered index. Bypassing it requires exceptional justification.

**Justification Provided**: None in SKILL.md.

**Conclusion**: Follow established pattern (agent sidecars) unless compelling reason exists.

## Related Decisions

| ADR | Relevance | Compliance |
|-----|-----------|------------|
| ADR-007 | Memory-first architecture | ⚠️ Partial (concept good, storage conflicts) |
| ADR-017 | Tiered index system | ❌ Violates (bypasses index) |
| ADR-040 | Skill frontmatter standards | ✅ Compliant |

## Strategic Frameworks Applied

### Mental Models

- [x] **Chesterton's Fence**: Investigated why tiered index exists before proposing bypass
- [x] **Second-Order Thinking**: Fragmentation consequences explored (undiscoverable memories)

### Architecture Principles

- [x] **Core vs Context**: Skill reflection is core (learning mechanism), warrants careful design
- [x] **Conway's Law**: Skill structure should mirror memory hierarchy (currently misaligned)

### Migration Patterns

- [ ] **Not Applicable**: New feature, not migration

## Final Recommendation

**NEEDS_CHANGES (P1)**

The skill concept is architecturally sound and aligns with memory-first principles. However, the storage implementation creates conflicts with established memory architecture (ADR-007, ADR-017).

**Fix Path**:

1. Adopt agent sidecar naming: `{skill-name}-skill-sidecar-learnings.md`
2. Add sidecars to `memory-index.md` routing
3. Clarify Serena (canonical) vs Forgetful (search) roles
4. Document relationship to `curating-memories`
5. Add session protocol integration hooks

**Effort Estimate**: 2-3 hours (documentation updates, no code changes)

**Blocking Status**: P1 - Must fix before merge. Memory architecture coherence is non-negotiable.

---

**Next Steps**:

1. Implementer addresses R1-R5 recommendations
2. Architect re-reviews updated SKILL.md
3. If approved, proceed to ADR creation (if needed)

**Handoff**: Return to orchestrator for routing to implementer.

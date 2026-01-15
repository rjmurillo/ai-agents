# ADR-017: Tiered Memory Index Architecture

**Status**: Accepted
**Date**: 2025-12-23
**Deciders**: User, Claude Opus 4.5
**Consulted**: 5-agent review (Critic, Architect, Analyst, Security, Independent-Thinker)
**Context**: Issue #307 Memory Automation, PR #308

---

## Context and Problem Statement

The Serena memory system stores learned skills and patterns in `.serena/memories/`. As of 2025-12-23:

- **115 memory files** before optimization
- **~7 new skills per day** growth rate
- **O(n) discovery**: Agents call `list_memories` (100+ names), then `read_memory` multiple times

Two competing optimization strategies emerged:

1. **Consolidation**: Merge related memories into fewer, larger files (reduce `list_memories` cost)
2. **Atomicity**: Keep small, focused files (reduce per-read waste)

**Key Question**: How do we minimize total tokens loaded while maximizing retrieval precision?

---

## Decision Drivers

1. **Token Efficiency**: LLM context windows are finite and expensive
2. **Retrieval Precision**: Load only what's needed for the current task
3. **Activation Vocabulary**: LLMs match on keyword associations, not symbolic lookup
4. **No Embeddings**: Serena MCP uses lexical matching, not semantic search
5. **Scalability**: Must work at 500+ memories without degradation

---

## Considered Options

### Option 1: Flat Consolidation

**Merge all related memories into domain files (e.g., `skills-copilot`)**

| Metric | Value |
|--------|-------|
| `list_memories` cost | Low (~15 files) |
| Per-read cost | High (load all skills in domain) |
| Waste when needing 1 skill | ~67% tokens wasted |

### Option 2: Pure Atomic Files

**Keep every skill in its own file**

| Metric | Value |
|--------|-------|
| `list_memories` cost | High (100+ names) |
| Per-read cost | Low (focused content) |
| Discovery | Requires scanning many file names |

**Problem**: No efficient way to find the right file without reading many.

### Option 3: Tiered Index Architecture (CHOSEN)

**Three-level hierarchy: Top Index → Domain Index → Atomic File**

```text
Level 0: memory-index (domain routing, ~400 tokens)
         ↓
Level 1: skills-{domain}-index (activation vocabulary, ~100 tokens)
         ↓
Level 2: {atomic-skill} (focused content, ~150 tokens)
```

---

## Decision Outcome

**Chosen option: Option 3 - Tiered Index Architecture**

### Critical Assumption

**Memory-index caching**: Efficiency claims assume `memory-index` is loaded once per session and cached. Without caching, the architecture provides **27.6% savings**. With caching (memory-index excluded from per-retrieval cost), savings reach **81.6%**.

### Architecture

```text
memory-index.md (Level 0) - ~400 tokens, cached
├── Points to: skills-copilot-index
├── Points to: skills-coderabbit-index
└── Points to: skills-{domain}-index

skills-copilot-index.md (Level 1) - ~100 tokens
| Keywords | File |
|----------|------|
| P0 P1 P2 RICE maintenance-only ... | copilot-platform-priority |
| duplicate sub-pr close branch ... | copilot-follow-up-pr |
| false-positive triage actionability ... | copilot-pr-review |

copilot-pr-review.md (Level 2) - ~150 tokens
[Focused, actionable content only]
```

### Design Principles

#### 1. Activation Vocabulary

Each domain index contains **10-15 keywords** per skill (recommended guideline based on pilot).

```markdown
| Keywords | File |
|----------|------|
| P0 P1 P2 RICE maintenance-only Claude-Code VSCode investment | copilot-platform-priority |
```

**Why**: LLMs map tokens into vector space where **association patterns** (not symbolic logic) drive selection.

**Keyword Guidelines**:

- Use domain-specific compound terms (e.g., `pr-review`, not `review`)
- Each skill SHOULD have ≥40% unique keywords vs other skills in domain
- Include action verbs: `triage`, `close`, `duplicate`

#### 2. Zero Retrieval-Value Content Elimination

Remove anything that doesn't aid retrieval:

| Remove | Reason |
|--------|--------|
| `# Title` headers | File name is self-descriptive |
| `**Date**: ... \| **Status**: Active` | Not actionable |
| `## Index\n\nParent: ...` | Navigation context already known |
| Verbose prose | Tables are denser |

#### 3. Progressive Refinement

| Level | Purpose | Tokens | Caching |
|-------|---------|--------|---------|
| 0 | Domain routing | ~400 | Session-cached |
| 1 | Skill identification via keywords | ~100 | Per-retrieval |
| 2 | Actionable content | ~150 | Per-retrieval |

---

## Validation

### Measured Token Costs (Analyst Verification)

| File | Measured Tokens |
|------|-----------------|
| `memory-index` (minimized) | ~400 |
| `skills-copilot-index` | ~100 |
| `copilot-platform-priority` | ~130 |
| `copilot-follow-up-pr` | ~95 |
| `copilot-pr-review` | ~210 |
| `skills-coderabbit` (consolidated baseline) | ~1,415 |

### Efficiency Analysis

| Scenario | Tiered (cached) | Consolidated | Savings |
|----------|-----------------|--------------|---------|
| Single skill retrieval | ~250 tokens | ~1,415 tokens | **82%** |
| 3 skills from domain | ~535 tokens | ~1,415 tokens | **62%** |
| 9+ skills (break-even) | ~1,400 tokens | ~1,415 tokens | **~0%** |

**Break-even point**: Tiered loses efficiency when retrieving **9 or more skills** from the same domain (≥70% of domain content).

---

## Consequences

### Positive

1. **82% token reduction** for single-skill retrieval (with caching)
2. **Activation vocabulary** enables intuitive matching
3. **Scalable**: Adding skills doesn't bloat existing files
4. **Blast radius containment**: Corruption affects only one domain

### Negative

1. **More files**: 1 index + N atomic files per domain vs 1 consolidated
   - **Mitigation**: Files are tiny; total bytes decrease by 64%
2. **Two reads for single skill**: Index + atomic file
   - **Mitigation**: ~250 tokens vs ~1,415; net 82% savings
3. **Manual index maintenance**: New skills must be added to index
   - **Mitigation**: CI validation required (see Confirmation)

### Failure Modes

| Mode | Risk | Mitigation |
|------|------|------------|
| **Index drift** | Index points to renamed/deleted file | CI validation script |
| **Keyword collision** | Overlapping keywords across skills | ≥40% unique keywords per skill |
| **Cold start** | Memory-index not cached | Accept 27.6% savings vs 82% |
| **Wrong path** | Agent picks wrong skill from keywords | Clear, specific keyword selection |

---

## Confirmation

Compliance verified via:

1. **Pre-commit hook**: Validates new skill files are indexed (`Validate-SkillFormat.ps1`)
2. **CI workflow**: `Validate-MemoryIndex.ps1` checks index ↔ file consistency
3. **Keyword density check**: Each skill has ≥40% unique keywords
4. **Index entry naming validation**: Index entries MUST NOT reference `skill-` prefixed files
5. **Orphan prefix detection**: Detects `skill-` prefixed files not in any index
6. **Index format validation**: Domain index files MUST be "pure lookup table" format (CI validation)

### Validation Implementation Status

> **Multi-Agent Review**: Session 93 (2025-12-28) - 6-agent debate resolved priorities below.

| Validation | Script | Status | Priority | Gap Reference |
|------------|--------|--------|----------|---------------|
| File references exist | `Validate-MemoryIndex.ps1:Test-FileReferences` | ✅ Implemented | - | - |
| Keyword density ≥40% | `Validate-MemoryIndex.ps1:Test-KeywordDensity` | ✅ Implemented | - | - |
| Memory-index references | `Validate-MemoryIndex.ps1:Test-MemoryIndexReferences` | ✅ Implemented | - | - |
| Orphan detection (domain) | `Validate-MemoryIndex.ps1:Get-OrphanedFiles` | ✅ Implemented | - | - |
| Index entry naming (skill-) | `Validate-MemoryIndex.ps1:Test-FileReferences` | ✅ Implemented | **P0** | Gap 1/2 |
| Orphan prefix (skill-) | `Validate-MemoryIndex.ps1:Get-OrphanedFiles` | ✅ Implemented | **P0** | Gap 4 |
| Pure lookup table format | `Validate-MemoryIndex.ps1:Test-IndexFormat` | ✅ Implemented | **P0** | Token efficiency |

### Domain Index Format Validation

> **User Override (2025-12-28)**: Elevated to P0 MUST requirement. Context window efficiency is critical - loading non-lookup content wastes tokens on every retrieval.

Domain index files (`*-index.md` in `.serena/memories/`) MUST contain ONLY:

```markdown
| Keywords | File |
|----------|------|
| keyword1 keyword2 ... | memory-file-name |
```

The following are PROHIBITED in domain index files:

- Titles (`# ...`)
- Metadata blocks (`**Date**: ... | **Status**: ...`)
- Prose or explanatory text
- Navigation sections (`## Index`, `Parent: ...`)
- Any content outside the keywords table

**Rationale**: Domain indices are loaded frequently during retrieval. Non-lookup content inflates context window usage without aiding skill discovery. This is a CRITICAL token efficiency requirement.

**Enforcement**: CI validation via `Test-IndexFormat` function in `Validate-MemoryIndex.ps1`. Files with prohibited content MUST fail validation.

### Index Entry Naming Validation

Index entries MUST reference files using the `{domain}-{description}` naming convention. The deprecated `skill-` prefix MUST NOT appear in:

- File references within index tables
- Atomic skill files in `.serena/memories/`

**Rationale**: Ensures ADR-017 naming migration is complete and prevents regression.

### Orphan Prefix Detection

Files with `skill-` prefix that are not referenced by any index MUST be detected and flagged as:

- Domain: `INVALID`
- ExpectedIndex: Rename guidance per ADR-017

**Rationale**: Silent failure mode where renamed files remain undetected undermines migration.

### Validation Blocking Status

> **User Override (2025-12-28)**: 3 P0 validations required. Pure lookup format elevated from P2 guideline to P0 requirement.

**Blocking for Phase 3+ rollout**: The following P0 validations must be implemented before expanding tiered architecture to additional domains:

1. **Index entry naming validation** (Gap 1/2): Detect `skill-` prefix in index table entries - ✅ IMPLEMENTED
2. **Orphan prefix detection** (Gap 4): Detect unindexed `skill-` prefixed files - ✅ IMPLEMENTED
3. **Pure lookup table format**: Reject index files with titles, metadata, prose - ✅ IMPLEMENTED

**Implementation tracking**: Session 93 implements all P0 validations (Gap 1/2, Gap 4, Pure Lookup Format) in `Validate-MemoryIndex.ps1`.

**Caching Verification (P1)**: Verify MCP session caching behavior in parallel with Phase 3 expansion. Update efficiency claims to verified numbers (currently: 27.6-81.6% range depending on caching).

### Implementation Notes

**Index File Protection**: The memory cross-reference automation (`Improve-MemoryGraphDensity.ps1`) explicitly excludes index files (*-index.md) from receiving "## Related" sections, ensuring compliance with the pure lookup table requirement (Issue #910). Validation enforcement via `Test-IndexFormat` remains in place as the authoritative check.

---

## Reversibility Assessment

| Criterion | Status |
|-----------|--------|
| Rollback capability | Can revert to consolidated files in <30 minutes |
| Vendor lock-in | None (pure markdown) |
| Exit strategy | Delete indices, concatenate atomics to consolidated |
| Data migration | No data loss on rollback |
| Legacy impact | Existing consolidated memories remain functional |

---

## Abort Criteria

Stop tiered migration and evaluate rollback if:

- Token overhead >20% vs consolidated baseline
- Retrieval precision <80% (wrong file loaded frequently)
- Index maintenance >2 hours/month
- Keyword collision rate >30% within domains
- Index drift detected in >3 consecutive PRs within 30 days

---

## Sunset Trigger

This architecture is optimized for lexical matching without embeddings. When Issue #167 (Vector Memory System) is implemented:

1. Re-evaluate tiered approach vs semantic search
2. Tiered indices may become unnecessary overhead
3. Consider deprecation in favor of embedding-based retrieval

---

## Implementation

### Domain Index Format

```markdown
| Keywords | File |
|----------|------|
| keyword1 keyword2 keyword3 ... | memory-file-name |
```

No title, no metadata. Pure lookup table.

### Atomic File Format

```markdown
## Section

| Column | Column |
|--------|--------|
| Data   | Data   |

**Key insight**: One sentence.
```

No title, no parent pointers, no dates.

### When to Use Tiered vs Consolidated

| Use Tiered | Use Consolidated |
|------------|------------------|
| Domain has ≥3 skills | Domain has ≤2 skills |
| Typical retrieval needs ≤70% of content | Skills always retrieved together |
| Skills are independently useful | Domain is rarely accessed |

---

## Migration Path

1. **Pilot**: Copilot domain (3 skills) - COMPLETE
2. **Validate**: Measured 82% savings (with caching) - COMPLETE
3. **Tooling**: Create `Validate-MemoryIndex.ps1` - REQUIRED before Phase 3
4. **Expand**: Apply to CodeRabbit (12 skills)
5. **Generalize**: Apply to remaining high-value domains

---

## Related Decisions

- [PRD-skills-index-registry.md](../planning/PRD-skills-index-registry.md): Superseded flat registry approach
- [Issue #307](https://github.com/rjmurillo/ai-agents/issues/307): Memory automation tracking
- [Session 51](../sessions/2025-12-20-session-51-token-efficiency-debate.md): 10-agent token efficiency debate
- `.agents/critique/017-tiered-memory-index-critique.md`: 5-agent review
- `.agents/analysis/083-adr-017-quantitative-verification.md`: Token calculations

---

## References

- **Pilot Implementation**: PR #308
- **Measured Data**: Copilot domain (4 files, 535 tokens total)
- **Baseline**: Consolidated `skills-coderabbit` (1,415 tokens)
- **Agent Reviews**: Critic, Architect, Analyst, Security, Independent-Thinker

---

## Validation Checklist

Before applying to new domain:

- [ ] Domain index is pure `| Keywords | File |` table
- [ ] Each skill has 10-15 keywords with ≥40% unique
- [ ] Atomic files have no titles, dates, or parent pointers
- [ ] `memory-index` updated with domain routing
- [ ] CI validation passes (index ↔ file consistency)

---

**Supersedes**: PRD-skills-index-registry.md flat registry approach (for high-value domains)
**Amended by**:

- Session 93 (2025-12-28) - Added validation implementation status table, index entry naming validation, orphan prefix detection
- Session 93 6-Agent Debate (2025-12-28) - Resolved priorities: Gap 1/2 and Gap 4 are P0 blockers; Caching verification P1 parallel task
- Session 93 User Override (2025-12-28) - Elevated Pure lookup format from P2 guideline to P0 MUST requirement; implemented Test-IndexFormat validation

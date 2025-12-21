# Analysis: Semantic Slug Protocol for Memory Naming

## 1. Objective and Scope

**Objective**: Evaluate whether semantic slug naming improves skill discoverability compared to numeric ID approach in PRD.

**Scope**:

- Compare PRD approach (`Skill-Analysis-001`) vs semantic slugs (`skill-git-squash-merge-clean-history.md`)
- Assess consolidation strategy (65 files to 15-20)
- Evaluate `000-memory-index.md` vs `skills-index.md`
- Identify migration risks and benefits

**Out of Scope**:

- Implementation timeline
- Automated migration tooling
- Agent prompt modifications

## 2. Context

### Current State (Session 46)

The Skills Index Registry PRD defined a governance system for 65+ skill files with:

- Numeric IDs: `Skill-{Domain}-{Number}` (e.g., `Skill-Planning-001`)
- Central registry: `skills-index.md` with quick reference table
- Both atomic (`skill-*.md`, 28 files) and collection (`skills-*.md`, 37 files) formats coexist
- O(n) discovery problem: agents read 100+ memory names, then multiple files

### Semantic Slug Proposal (Session 48)

Counter-proposal challenges core PRD assumptions:

- **Core insight**: LLMs are "relevance engines" - numeric tokens (`001`) carry zero semantic weight
- **Naming**: `skill-git-squash-merge-clean-history.md` instead of `Skill-Git-004.md`
- **Consolidation**: Merge 65 files into 15-20 domain libraries
- **Index**: `000-memory-index.md` (sorts first) with one-line summaries

### Prior Decisions

- FR-5 (PRD): Skill ID naming convention enforces `Skill-{Domain}-{Number}`
- FR-9 (PRD): Collection and atomic files coexist
- No evidence of high-level-advisor identifying retrieval problem (searched, not found)

## 3. Approach

### Methodology

1. Compare naming conventions using real-world examples from `.serena/memories/`
2. Analyze retrieval semantics (what tokens help LLMs match relevance?)
3. Evaluate consolidation feasibility (file size, domain boundaries)
4. Assess migration complexity (file renames, cross-references, backward compatibility)

### Tools Used

- `mcp__serena__list_memories` - Current memory inventory (100+ items)
- `Glob` - File pattern analysis (28 atomic, 37 collection files)
- `Read` - Sample skill content structure
- Session logs - Historical context (Sessions 46, 48)

### Limitations

- No A/B testing data on LLM retrieval performance with numeric vs semantic naming
- No user research on agent preferences for file names
- No performance benchmarks for consolidated vs atomic files

## 4. Data and Analysis

### Evidence Gathered

| Finding | Source | Confidence |
|---------|--------|------------|
| 65 total skill files (28 atomic, 37 collection) | Glob tool output | High |
| Numeric IDs carry zero semantic weight for LLMs | Semantic slug proposal | Medium |
| Current PRD defines 10 FRs with numeric ID convention | `.agents/planning/PRD-skills-index-registry.md` | High |
| Collection files contain multiple skills (e.g., `skills-planning.md` has Skill-Planning-001, 002) | File content | High |
| Session 48 routing to 4 agents for feedback | `.agents/sessions/2025-12-20-session-48-semantic-slug-orchestration.md` | High |
| `000-memory-index.md` sorts first in `list_memories` output | File naming convention | High |

### Facts (Verified)

- Current system has 65 skill-related memory files
- PRD Session 46 created 10 Functional Requirements for numeric ID approach
- Atomic skill files follow pattern: `skill-{domain}-{number}-{name}.md`
- Collection files follow pattern: `skills-{domain}.md`
- `list_memories` returns alphabetically sorted list
- Skill content includes: Statement, Context, Evidence, Atomicity, Impact

### Hypotheses (Unverified)

- Semantic slugs improve LLM relevance matching (no benchmark data)
- Consolidating to 15-20 files improves discoverability (no user testing)
- `000-memory-index.md` will be read more frequently than `skills-index.md` (no usage data)
- Migration will not break existing cross-references (needs validation)

## 5. Results

### Naming Convention Comparison

| Aspect | PRD Approach | Semantic Slug Approach |
|--------|--------------|------------------------|
| **Example** | `Skill-Analysis-001` | `skill-git-squash-merge-clean-history` |
| **Semantic Tokens** | "Skill", "Analysis" (2/3) | "skill", "git", "squash", "merge", "clean", "history" (6/6) |
| **Uniqueness** | Guaranteed by number | Relies on slug distinctiveness |
| **Sortability** | Alphabetical = numerical | Alphabetical by domain, then technique |
| **Readability** | Requires index lookup | Self-documenting |
| **Collision Risk** | Low (numbers enforce uniqueness) | Medium (two similar techniques could create near-duplicates) |

### Consolidation Analysis

**Current Structure:**

- 28 atomic skills: Single skill per file
- 37 collection skills: Multiple skills per domain file

**Proposed Structure:**

- 15-20 domain libraries consolidating related skills
- Prefixes: `adr-`, `context-`, `pattern-`, `skill-`

**File Size Estimate:**

- Average atomic skill: 50 lines (2KB)
- Consolidating 5 skills per domain: 250 lines (10KB)
- All 65 skills in 15 files: Average 325 lines/file (13KB) - well within readable limits

**Domain Boundaries:**

Existing domains identified from file analysis:
- Analysis, Architecture, Documentation, Planning, Testing, QA, Security, CI-Infrastructure, PowerShell, GraphQL, Orchestration, Execution, Validation, etc.

Potential consolidated domains (15-20):
- `context-analysis-methodology.md` (all analysis skills)
- `context-architecture-decisions.md` (all architecture patterns)
- `context-testing-standards.md` (all testing/QA skills)
- `skill-powershell-techniques.md` (PowerShell-specific how-tos)
- `pattern-git-workflows.md` (Git patterns)
- etc.

### Index Comparison

| Feature | `skills-index.md` (PRD) | `000-memory-index.md` (Proposal) |
|---------|-------------------------|----------------------------------|
| **Sort Position** | Mid-alphabet ("s") | First (leading "0") |
| **Scope** | Skills only | All memories |
| **Content** | 5-column table (Skill ID, Domain, Statement, File, Status) | One-line summaries |
| **Maintenance** | Manual updates per FR-10 | Manual (same effort) |
| **Discoverability** | Requires knowing to search for "skills-index" | Always first in `list_memories` |

## 6. Discussion

### The "Relevance Engine" Argument

The semantic slug proposal's core insight: **LLMs match relevance using tokens**.

When `list_memories` returns `Skill-Build-001.md`:
- Tokens: `Skill`, `Build`, `001`
- Semantic weight: "Skill" (generic), "Build" (domain), "001" (no meaning)
- Agent cannot infer this solves "PowerShell Pester test failure"

When `list_memories` returns `skill-pester-test-isolation-pattern.md`:
- Tokens: `skill`, `pester`, `test`, `isolation`, `pattern`
- Semantic weight: All tokens carry meaning
- Agent can infer relevance to "Pester test failure"

This argument is **plausible but unverified**. No benchmark data exists comparing LLM retrieval accuracy with numeric vs semantic naming.

### Consolidation Benefits

**Pro:**
- Reduces cognitive load (15-20 files vs 65)
- Groups related skills for browsing
- Larger files provide more context per read

**Con:**
- Harder to pinpoint specific skill within file
- Merge conflicts more likely with larger files
- Loss of atomic versioning (can't deprecate one skill without affecting others)

### Migration Complexity

**Required Changes:**

1. **File Renames**: 65 files need new names following semantic slug convention
2. **Cross-References**: All `Skill-{Domain}-{Number}` references in skill content need updating
3. **Agent Prompts**: References to skill IDs in agent definitions may need updating
4. **Index Structure**: Rebuild index with new naming convention

**Backward Compatibility Risk**: MEDIUM

- Old skill IDs (`Skill-Analysis-001`) referenced in:
  - Historical session logs (read-only, no issue)
  - Other skill files (requires update)
  - Agent prompts (if hardcoded IDs exist)
  - HANDOFF.md and planning documents (requires update)

### The `000-memory-index.md` Advantage

Sorting first in `list_memories` is a **significant UX improvement**.

Current behavior:
- Agent calls `list_memories`, receives 100+ items alphabetically
- Must scan entire list to find `skills-index` (position ~85/100)

Proposed behavior:
- Agent calls `list_memories`, receives 100+ items
- First item is `000-memory-index.md`
- Agent reads index immediately if unsure where to look

This is a **low-cost, high-value change** independent of the semantic slug debate.

### Prefix Taxonomy

Proposed prefixes provide **clear categorization**:

- `adr-[000]-[slug].md` - Architecture Decision Records (chronological, keep numbers)
- `context-[domain]-[topic].md` - Domain knowledge libraries
- `pattern-[problem]-[solution].md` - Reusable solution patterns
- `skill-[technology]-[technique].md` - How-to guides

This taxonomy is **more expressive** than current `skill-*` vs `skills-*` distinction.

### PRD Impact

**Conflicting Requirements:**

- FR-5: Enforces `Skill-{Domain}-{Number}` naming
- FR-7: Skill creation process assumes numeric IDs
- FR-8: Skill deprecation process assumes numeric IDs

**Obsoleted Requirements:**

- FR-2, FR-3, FR-4: Quick reference table structure becomes less critical if file names are self-documenting
- FR-6: Lifecycle states (Draft/Active/Deprecated) may not fit consolidated file model

**Preserved Requirements:**

- FR-1: Index file location (still applies to `000-memory-index.md`)
- FR-10: Manual index maintenance (same effort)

## 7. Recommendations

| Priority | Recommendation | Rationale | Effort |
|----------|----------------|-----------|--------|
| P0 | Adopt `000-memory-index.md` naming for index file | Sorts first, low-risk, high-value UX improvement | Low (rename only) |
| P1 | Adopt prefix taxonomy (`adr-`, `context-`, `pattern-`, `skill-`) | Clear categorization, aligns with industry conventions | Medium (migration) |
| P1 | Pilot semantic slugs with 5 new skills | Test retrieval hypothesis before full migration | Low (new files only) |
| P2 | Consolidate collection files (`skills-*.md`) into `context-*.md` | Preserve multi-skill content, modernize naming | Medium (37 files) |
| P2 | Migrate atomic skills to semantic slugs incrementally | Gradual migration reduces risk | High (28 files + refs) |
| P3 | Deprecate numeric ID convention after 6-month transition | Allow time for agents to adapt | Low (documentation) |

## 8. Conclusion

### Verdict

**Proceed with Hybrid Approach**

- Adopt `000-memory-index.md` immediately (P0)
- Adopt prefix taxonomy for new memories (P1)
- Pilot semantic slugs for new skills (P1)
- Defer consolidation decision pending pilot results (P2)

### Confidence

**Medium**

The semantic slug proposal addresses a **real discoverability problem** but lacks empirical validation. The PRD's numeric ID approach provides **guaranteed uniqueness** but sacrifices semantic richness.

A **hybrid approach** allows incremental testing while preserving backward compatibility.

### Rationale

1. **The discoverability problem is real**: Agents reading 65+ files to find one skill is inefficient
2. **Semantic tokens likely help**: LLMs match on relevance, not arbitrary numbers
3. **Migration risk is manageable**: Incremental approach limits disruption
4. **Consolidation needs validation**: File count reduction may not improve retrieval if files lack semantic names

### User Impact

#### What Changes for You

If adopted:
- New skills will have descriptive names (`skill-git-rebase-interactive.md` vs `Skill-Git-005`)
- Master index will always appear first in memory listings (`000-memory-index.md`)
- Related skills may be grouped in domain files instead of separate files

#### Effort Required

- **For users**: None (agent behavior, not user-facing)
- **For agents**: 2-4 weeks to learn new naming conventions during pilot
- **For maintainers**: Medium effort to migrate 65 files and update cross-references

#### Risk if Ignored

- Skill discovery remains O(n) linear search
- Agents continue reading multiple files unnecessarily
- New skills keep adding to the 65-file count without semantic organization

## 9. Appendices

### Sources Consulted

- `.agents/planning/PRD-skills-index-registry.md` - Current PRD (Session 46)
- `.agents/sessions/2025-12-20-session-48-semantic-slug-orchestration.md` - Proposal context
- `.serena/memories/` - File listing (28 atomic, 37 collection skills)
- `skill-planning-001-checkbox-manifest.md` - Sample atomic skill structure
- `skills-planning.md` - Sample collection skill structure

### Data Transparency

**Found:**
- 65 total skill files in `.serena/memories/`
- 28 atomic skills, 37 collection skills
- PRD with 10 Functional Requirements
- Semantic slug proposal with 4 prefix types

**Not Found:**
- Benchmark data on LLM retrieval with numeric vs semantic naming
- High-level-advisor feedback identifying retrieval problem
- User research on agent preferences
- Performance data for consolidated vs atomic files
- Cross-reference inventory (how many places reference `Skill-{Domain}-{Number}`)

### Open Questions for Follow-Up

1. **Collision Detection**: How will we prevent near-duplicate semantic slugs? (e.g., `skill-git-rebase.md` vs `skill-git-interactive-rebase.md`)
2. **Deprecation in Consolidated Files**: How do we mark one skill deprecated within a multi-skill file?
3. **Backward Compatibility Timeline**: How long do we maintain old numeric IDs before full migration?
4. **Agent Adoption**: Will agents naturally prefer `000-memory-index.md` or do prompts need updates?

---

**Analysis Complete**
**Next Steps**: Route to orchestrator for decision synthesis with other agent feedback (Session 48)

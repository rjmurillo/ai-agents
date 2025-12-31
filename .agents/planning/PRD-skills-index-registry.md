# PRD: Skills Index Registry

**Version**: 1.3
**Created**: 2025-12-20
**Status**: Approved (10-Agent Consensus)
**Approved Date**: 2025-12-20
**Updated**: 2025-12-30 (Added GitHub issue reference)
**Target Audience**: Junior developers
**GitHub Issue**: [#581](https://github.com/rjmurillo/ai-agents/issues/581) - Skills Index Registry Epic

## Introduction/Overview

The ai-agents repository uses a memory system to store learned skills across agent sessions. As of 2025-12-20, the system contains 65+ skill-related memory files stored in `.serena/memories/`. Skills are scattered across two file types:

1. Collection files: `skills-{domain}.md` (e.g., `skills-analysis.md`, `skills-documentation.md`)
2. Atomic files: `skill-{domain}-{number}-{name}.md` (e.g., `skill-analysis-001-comprehensive-analysis-standard.md`)

Agents currently discover skills by calling `mcp__serena__list_memories`, which returns 100+ memory names, then calling `mcp__serena__read_memory` multiple times to find relevant skills. This is an O(n) linear search that scales poorly as skills grow (currently ~7 new skills per day).

This PRD defines a Skills Index Registry to enable O(1) skill lookup by ID, establish consistent naming conventions, and provide skill lifecycle governance.

## Goals

1. Create a central registry (`skills-index.md`) that agents can reference with a single memory read
2. Enable O(1) skill lookup by skill ID without reading multiple files
3. Establish consistent skill ID naming convention to prevent collisions
4. Define skill lifecycle (creation → validation → deprecation) with clear governance
5. Provide quick reference table for browsing all skills by domain

## Non-Goals (Out of Scope)

1. Restructuring existing skill files (files remain in current locations)
2. Automated skill discovery or validation (manual maintenance acceptable for v1)
3. Skill versioning system (skills can be deprecated but not versioned)
4. Integration with agent prompts (agents must actively choose to read index)
5. Migration of collection files to atomic format (both formats coexist)

## User Stories

1. **As an agent**, I want to find a specific skill by ID in one memory read, so that I can reference skills without reading 65+ files
2. **As a retrospective agent**, I want to know what skill IDs are already used, so that I do not create duplicate skill IDs
3. **As a planner agent**, I want to see all skills grouped by domain, so that I can discover related skills when planning implementations
4. **As a skillbook agent**, I want to see which skills are deprecated, so that I do not recommend outdated patterns to other agents
5. **As a quality gate**, I want to validate new skills follow the naming convention, so that the skill registry stays consistent

## Functional Requirements

### FR-1: Skills Index File Location

The system MUST create a file named `skills-index.md` in the `.serena/memories/` directory.

**Rationale**: Placing the index in `.serena/memories/` allows agents to read it using `mcp__serena__read_memory` with `memory_file_name="skills-index"`, consistent with existing memory access patterns.

### FR-2: Quick Reference Table

The index MUST include a table with the following columns:

| Column | Description | Example |
|--------|-------------|---------|
| **Skill ID** | Unique identifier for the skill | `Skill-Analysis-001` |
| **Domain** | Category of the skill | `Analysis` |
| **Statement** | One-sentence summary (10-20 words) | "Analysis documents containing options analysis enable 100% implementation accuracy" |
| **File** | Memory file name where full skill is stored | `skill-analysis-001-comprehensive-analysis-standard` |
| **Status** | Active or Deprecated | `Active` |

**Format**:

```markdown
| Skill ID | Domain | Statement | File | Status |
|----------|--------|-----------|------|--------|
| Skill-Analysis-001 | Analysis | Analysis documents containing options analysis enable 100% implementation accuracy | skill-analysis-001-comprehensive-analysis-standard | Active |
| Skill-Documentation-002 | Documentation | Categorize references as instructive, informational, or operational before migration | skill-documentation-002-reference-type-taxonomy | Active |
```

**Rationale**: The table provides at-a-glance skill discovery. Agents can scan the statement column to find relevant skills, then use the file column to read the full skill definition.

### FR-3: Domain Grouping

The index MUST group skills by domain using markdown headings.

**Format**:

```markdown
## Analysis Skills

| Skill ID | Domain | Statement | File | Status |
|----------|--------|-----------|------|--------|
| Skill-Analysis-001 | Analysis | ... | skill-analysis-001-comprehensive-analysis-standard | Active |

## Documentation Skills

| Skill ID | Domain | Statement | File | Status |
|----------|--------|-----------|------|--------|
| Skill-Documentation-001 | Documentation | ... | skill-documentation-001-systematic-migration-search | Active |
| Skill-Documentation-002 | Documentation | ... | skill-documentation-002-reference-type-taxonomy | Active |
```

**Rationale**: Domain grouping enables browsing related skills. An agent working on documentation can quickly see all documentation skills without searching.

### FR-4: Deprecated Skills Section

The index MUST include a separate section for deprecated skills.

**Format**:

```markdown
## Deprecated Skills

| Skill ID | Domain | Deprecated Date | Reason | Replacement |
|----------|--------|-----------------|--------|-------------|
| Skill-QA-002 | QA | 2025-12-20 | Superseded by Skill-QA-003 (MUST vs SHOULD) | Skill-QA-003 |
```

**Rationale**: Deprecated skills must remain visible to prevent confusion when old references appear in historical documents. The replacement column guides agents to the current best practice.

### FR-5: Skill ID Naming Convention

The system MUST define and enforce the following skill ID naming convention:

**Pattern**: `Skill-{Domain}-{Number}`

**Rules**:

1. **Domain**: CamelCase domain name matching skill file domain (e.g., `Analysis`, `Documentation`, `Architecture`)
2. **Number**: 3-digit zero-padded sequential number (e.g., `001`, `002`, `010`, `100`)
3. **Uniqueness**: Skill IDs MUST be globally unique across all domains
4. **Reserved IDs**: Numbers 001-099 reserved for foundational skills per domain

**Valid Examples**:

- `Skill-Analysis-001`
- `Skill-Documentation-005`
- `Skill-Architecture-015`

**Invalid Examples**:

- `skill-analysis-1` (lowercase, no zero-padding)
- `Analysis-001` (missing "Skill-" prefix)
- `Skill-analysis-001` (lowercase domain)

**Rationale**: Consistent IDs enable reliable cross-references. The zero-padding ensures alphabetical sorting matches numerical order.

### FR-6: Skill Lifecycle States

The system MUST support the following skill lifecycle states:

1. **Draft**: Skill created but not validated
2. **Active**: Skill validated and in use
3. **Deprecated**: Skill superseded or obsolete

**State Transitions**:

```text
Draft → Active (after validation)
Active → Deprecated (when superseded or obsolete)
```

**Validation Criteria** (Draft → Active):

- [ ] Skill ID follows naming convention (FR-5)
- [ ] Skill ID is globally unique (check index)
- [ ] Statement is 10-20 words
- [ ] Evidence section includes validation count
- [ ] Atomicity score is documented

### FR-7: Skill Creation Process

When creating a new skill, agents MUST:

1. Read `skills-index` memory to check for ID collisions
2. Assign next available skill number in domain
3. Create skill file: `skill-{domain}-{number}-{name}.md`
4. Update `skills-index.md` with new entry (status: Draft)
5. After validation, update status to Active

**Example Workflow**:

```text
Agent creates Skill-Planning-023

1. Read skills-index memory
2. Check: Skill-Planning-022 exists, Skill-Planning-023 does not
3. Create file: skill-planning-023-new-skill-name.md
4. Add to skills-index.md:
   | Skill-Planning-023 | Planning | [statement] | skill-planning-023-new-skill-name | Draft |
5. After validation:
   | Skill-Planning-023 | Planning | [statement] | skill-planning-023-new-skill-name | Active |
```

### FR-8: Skill Deprecation Process

When deprecating a skill, agents MUST:

1. Update skill status in index to "Deprecated"
2. Add entry to "Deprecated Skills" section with reason and replacement
3. Preserve deprecated skill file (do NOT delete)
4. Update cross-references in other skills to point to replacement

**Example**:

```markdown
## QA Skills

| Skill ID | Domain | Statement | File | Status |
|----------|--------|-----------|------|--------|
| Skill-QA-002 | QA | QA validation before merge (SHOULD) | skill-qa-002 | Deprecated |
| Skill-QA-003 | QA | BLOCKING gate for qa routing (MUST) | skill-qa-003-blocking-gate | Active |

## Deprecated Skills

| Skill ID | Domain | Deprecated Date | Reason | Replacement |
|----------|--------|-----------------|--------|-------------|
| Skill-QA-002 | QA | 2025-12-20 | Superseded by Skill-QA-003 (MUST vs SHOULD) | Skill-QA-003 |
```

### FR-9: Collection Files Handling

Collection files (e.g., `skills-analysis.md`, `skills-documentation.md`) MUST be listed in the index with their own entries.

**Format**:

```markdown
## Analysis Skills (Collection)

| Skill ID | Domain | Statement | File | Status |
|----------|--------|-----------|------|--------|
| Skills-Analysis-Collection | Analysis | Multiple analysis skills grouped by domain | skills-analysis | Active |

## Analysis Skills (Atomic)

| Skill ID | Domain | Statement | File | Status |
|----------|--------|-----------|------|--------|
| Skill-Analysis-001 | Analysis | Analysis documents containing options analysis enable 100% implementation accuracy | skill-analysis-001-comprehensive-analysis-standard | Active |
```

**Rationale**: Collection files contain multiple skills. Listing them separately from atomic skills prevents confusion about which file to read.

### FR-10: Index Maintenance

The system MUST support manual index updates initially. Future automation is out of scope for v1.

**Maintenance Tasks**:

1. Add new skills after creation
2. Update status when skills are validated
3. Move skills to deprecated section when superseded
4. Verify no duplicate skill IDs monthly

**Update Frequency**: After each skill creation or deprecation

## Design Considerations

### UI/UX Requirements

The index MUST be readable in markdown viewers (GitHub, VS Code, Claude Code). No special tooling required.

### Table Readability

Tables MUST use alignment for readability:

```markdown
| Skill-Analysis-001      | Analysis      | Analysis documents containing options analysis enable 100% implementation accuracy | skill-analysis-001-comprehensive-analysis-standard | Active     |
| Skill-Documentation-002 | Documentation | Categorize references as instructive, informational, or operational before migration | skill-documentation-002-reference-type-taxonomy   | Active     |
```

**Note**: Markdown renderers handle alignment automatically; source file alignment is optional.

## Technical Considerations

### Performance

**Current State**: O(n) discovery requires reading multiple files

- `mcp__serena__list_memories`: ~100ms
- `mcp__serena__read_memory` per file: ~50ms
- Total for 5 skills: ~350ms

**Target State**: O(1) lookup with index

- `mcp__serena__read_memory` for index: ~50ms
- Agent scans table in-memory: ~10ms
- `mcp__serena__read_memory` for specific skill: ~50ms
- Total: ~110ms (68% faster)

### Token Efficiency Trade-offs

The memory system operates without embeddings or vector databases. This creates a fundamental trade-off:

**Trade-off**: More files vs. smaller files

| Approach | `list_memories` Cost | Per-read Cost | Discovery |
|----------|---------------------|---------------|-----------|
| Many small files | Higher (100+ names) | Lower (focused content) | Name-based |
| Few large files | Lower (15 names) | Higher (scan irrelevant content) | Content-based |

**Current architecture** (atomic files + index) optimizes for:

1. **Activation vocabulary**: File names and index statements contain high-signal keywords that activate LLM attention patterns
2. **Focused reads**: Each `read_memory` returns only relevant content (no scanning through consolidated libraries)
3. **No embedding overhead**: Purely lexical matching via file names and index summaries

### Activation Vocabulary Principle

LLMs break language into tokens and map them into a **vector space**. That space represents **association, not symbolic logic** - think of it as a word cloud.

For each skill or memory, imagine generating a list of **5 words** that describe it. That list is **gold** - it's your activation vocabulary.

**Design Guidelines**:

1. **Identify 5 activation words** per skill (the most strongly associated terms)
2. **Include activation words** in file names and index statements
3. **Precision matters** - vague words activate too many associations
4. **Match training data patterns** - use terms from common documentation, not invented jargon

**Example**:

```text
Skill: PowerShell null safety with -contains operator

Activation words: powershell, null, contains, array, coercion
File name: skill-powershell-null-safety-contains-operator.md
Index statement: "Use @() array coercion before -contains on potentially single items"
```

**Why this matters**:

- Agents must "want to choose" a memory based on its name before reading it
- Activation vocabulary increases selection probability by matching LLM association patterns
- The index adds a second layer of discoverability (statement-level activation)

**Future evolution** (out of scope for v1):

Embeddings + vector database would provide ~10x improvement:

- Semantic similarity search instead of lexical matching
- Automatic relevance ranking
- Cross-skill concept linking

Until then, the index registry maximizes discoverability within lexical constraints.

### Scalability

The index MUST scale to 500+ skills without performance degradation.

**Assumption**: A markdown table with 500 rows is ~50KB, well within memory limits.

### Backwards Compatibility

Existing skill files MUST remain unchanged. Agents not using the index continue to work with `list_memories` and `read_memory` patterns.

### Dependencies

- Serena MCP memory system (`mcp__serena__read_memory`, `mcp__serena__write_memory`)
- Markdown linting (`markdownlint-cli2`) for table validation

## Success Metrics

### Primary Metrics

1. **Skill Discovery Time**: Reduce from 350ms (5 skills) to 110ms (68% reduction)
2. **Duplicate Skill IDs**: 0 collisions after index creation
3. **Adoption Rate**: 50% of agents reference index within 2 weeks

### Secondary Metrics

1. **Index Completeness**: 100% of active skills listed in index
2. **Deprecation Clarity**: 100% of deprecated skills have replacement references
3. **Naming Consistency**: 100% of new skills follow naming convention

### Validation Criteria

- [ ] Index file created at `.serena/memories/skills-index.md`
- [ ] All 65 existing skills listed in index
- [ ] Table includes all required columns (Skill ID, Domain, Statement, File, Status)
- [ ] Skills grouped by domain with markdown headings
- [ ] Deprecated skills section exists (even if empty initially)
- [ ] Naming convention documented in index header
- [ ] At least one agent successfully uses index to find skill

## Agent Discussion: Semantic Slug Protocol Review

### Context

On 2025-12-20, a "Semantic Slug Protocol" was proposed as an alternative to the numeric ID approach in this PRD. The proposal suggested:

1. Rename files to semantic slugs (e.g., `skill-powershell-null-safety-contains-operator.md`)
2. Consolidate 65 files into 15 domain libraries
3. Use `000-memory-index.md` as master index

**Rationale cited**: "LLMs are relevance engines - numeric tokens carry zero semantic weight"

### 10-Agent Review

The following agents were consulted in parallel:

| Agent | Verdict | Key Insight |
|-------|---------|-------------|
| **Critic** | APPROVE Index | Core premise false - Serena MCP abstracts file names |
| **Analyst** | APPROVE Hybrid | Pilot semantic slugs for 5 new skills only |
| **Implementer** | APPROVE Index | 87% cost reduction (2-3h vs 16-23h) |
| **QA** | NEUTRAL | Test strategy defined for either approach |
| **Orchestrator** | SYNTHESIZE | Consolidated all feedback |
| **Retrospective** | APPROVE Index | File names invisible to agent workflow |
| **Skillbook** | APPROVE Index | Deduplication requires atomicity |
| **Memory** | APPROVE Index | O(1) index lookup vs O(n) library scan |
| **DevOps** | APPROVE Index | 67 cross-references would break |
| **Security** | APPROVE Index | Consolidation increases blast radius 3x |

### Unanimous Findings

1. **Serena MCP abstracts file names** - Agents call `read_memory(memory_file_name)`, not file paths
2. **Index registry solves the real problem** - O(n) → O(1) discovery
3. **Consolidation degrades performance** - 65 atomic files → 15 libraries is architecture regression
4. **67 cross-references would break** - No migration plan defined for semantic slugs
5. **Numeric IDs are stable** - Sequential numbering prevents collisions

### Decision: APPROVED (Disagree and Commit)

**Status**: APPROVED - Numeric IDs with Index Registry (this PRD)

**Rejected Alternative**: Semantic Slug Protocol

- **Premise false**: Serena MCP abstraction makes file names invisible to agents
- **Architecture regression**: O(n) library scanning degrades performance
- **Migration undefined**: 67 cross-references, no rollback plan, no validation tooling

**Extracted for Future Work** (Phase 2):

- Prefix taxonomy for non-skill memories (`retrospective-`, `pattern-`, `context-`)
- This is ALREADY the current pattern - no implementation needed

### Security Recommendations (from Security Agent)

The following controls SHOULD be added:

1. **Skill ID Validation Gate**: Pre-commit hook rejects skill files not listed in index
2. **Index Integrity Check**: Periodic validation that all skill files have index entries
3. **Write Access Patterns**: Document which agents can create/deprecate skills

## Open Questions

1. **Automated Index Generation**: Should we create a script to auto-generate the index from skill files?
   - **Assumption for v1**: Manual maintenance is acceptable; automation can be added later
2. **Skill ID Reassignment**: Can deprecated skill IDs be reused after 6 months?
   - **Assumption for v1**: Skill IDs are never reused to prevent confusion in historical documents
3. **Cross-Domain Skills**: How do we handle skills that span multiple domains (e.g., a skill about both documentation and testing)?
   - **Assumption for v1**: Assign skill to primary domain; mention secondary domain in statement
4. **Collection File Migration**: Should we migrate collection files to atomic format over time?
   - **Assumption for v1**: Both formats coexist; migration is out of scope

## Assumptions

1. Agents will proactively read the index when creating new skills (no enforcement mechanism in v1)
2. Manual index maintenance is sustainable for current skill creation rate (~7/day)
3. Markdown table format is sufficient for 500+ skills (no database required)
4. Skill IDs are never reused, even after deprecation
5. Serena MCP memory system remains the storage backend

## References

- Related Memory: `skills-governance` (governance patterns)
- Related Memory: `skills-documentation` (documentation standards)
- Related Memory: `skill-documentation-004-pattern-consistency` (consistency patterns)
- Related Issue: Skill discovery inefficiency (current O(n) process)
- Target Directory: `.serena/memories/`
- Index File: `.serena/memories/skills-index.md`

## Appendix: Example Index Structure

```markdown
# Skills Index Registry

**Version**: 1.0
**Last Updated**: 2025-12-20
**Total Active Skills**: 65
**Total Deprecated Skills**: 1

## Purpose

This registry provides a central index of all skills in the ai-agents memory system. Use this index to:

- Find skills by ID in one memory read (O(1) lookup)
- Discover related skills grouped by domain
- Check for skill ID collisions before creating new skills
- Identify deprecated skills and their replacements

## Skill ID Naming Convention

**Pattern**: `Skill-{Domain}-{Number}`

**Rules**:

1. Domain: CamelCase domain name (e.g., Analysis, Documentation, Architecture)
2. Number: 3-digit zero-padded sequential (e.g., 001, 002, 010, 100)
3. Uniqueness: Skill IDs MUST be globally unique across all domains

## Analysis Skills

| Skill ID | Domain | Statement | File | Status |
|----------|--------|-----------|------|--------|
| Skill-Analysis-001 | Analysis | Analysis documents containing options analysis enable 100% implementation accuracy | skill-analysis-001-comprehensive-analysis-standard | Active |

## Documentation Skills

| Skill ID | Domain | Statement | File | Status |
|----------|--------|-----------|------|--------|
| Skill-Documentation-001 | Documentation | Structure gap analysis with ID, Severity, Root Cause, Affected Agents, Remediation | skill-documentation-001-systematic-migration-search | Active |
| Skill-Documentation-002 | Documentation | Categorize references as instructive, informational, or operational before migration | skill-documentation-002-reference-type-taxonomy | Active |

## Deprecated Skills

| Skill ID | Domain | Deprecated Date | Reason | Replacement |
|----------|--------|-----------------|--------|-------------|
| Skill-QA-002 | QA | 2025-12-20 | Superseded by Skill-QA-003 (MUST vs SHOULD) | Skill-QA-003 |
```

---

**End of PRD**

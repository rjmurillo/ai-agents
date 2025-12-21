# Test Strategy: Semantic Slug Protocol Migration

**Feature**: Skill file migration from numeric IDs to semantic slugs
**Date**: 2025-12-20
**QA Agent**: Session 49
**Status**: Strategy Defined

## Objective

Verify that the semantic slug migration successfully transforms the skill memory system from numeric identifiers to semantic slugs while maintaining:

- Skill retrievability by agents
- Cross-reference integrity
- Serena MCP compatibility
- Master index accuracy

**Acceptance Criteria Reference**: As defined in Skills Index Registry PRD (Session 46)

## Scope

### What's Being Changed

1. **65+ skill files renamed** from `skill-domain-NNN` to `skill-domain-semantic-slug.md`
2. **Master index created** at `000-memory-index.md`
3. **Files consolidated** from 65 to ~15-20 domain libraries
4. **Cross-references updated** across:
   - Session logs (`.agents/sessions/`)
   - Agent definitions (`src/*/`)
   - AGENTS.md
   - Skills themselves

### Migration Metrics (Baseline)

| Metric | Current Value |
|--------|---------------|
| Total memory files | 108 |
| Individual skill files (skill-*.md) | 28 |
| Domain library files (skills-*.md) | 37 |
| Total skill-related files | 65 |
| Non-skill memories | 43 |

**Target State**: ~15-20 consolidated domain libraries + 1 master index

## Test Types

### 1. Pre-Migration Baseline Tests (BLOCKING)

Establish baseline before any changes.

**Coverage Target**: 100% of current retrieval paths

| Test | Type | Priority |
|------|------|----------|
| Document current retrieval patterns | Baseline | P0 |
| Catalog all skill file references | Baseline | P0 |
| Measure current search performance | Baseline | P1 |
| Document Serena read_memory behavior | Baseline | P0 |

### 2. Migration Execution Tests (BLOCKING)

Verify migration process integrity.

**Coverage Target**: 100% of files migrated

| Test | Type | Priority |
|------|------|----------|
| Verify no skill content lost | Data Integrity | P0 |
| Verify all files renamed | Completeness | P0 |
| Verify master index created | Artifact | P0 |
| Verify consolidation count matches target | Completeness | P1 |

### 3. Retrieval Regression Tests (BLOCKING)

Verify agents can still find skills.

**Coverage Target**: All retrieval methods tested

| Test | Type | Priority |
|------|------|----------|
| Test read_memory with new names | Integration | P0 |
| Test list_memories returns new names | Integration | P0 |
| Test search_nodes finds skills | Integration | P0 |
| Compare retrieval rate pre/post migration | Regression | P0 |

### 4. Cross-Reference Validation Tests (BLOCKING)

Verify no broken references remain.

**Coverage Target**: Zero dangling references

| Test | Type | Priority |
|------|------|----------|
| Grep for old numeric skill IDs | Validation | P0 |
| Verify AGENTS.md references updated | Validation | P0 |
| Verify agent definition references updated | Validation | P0 |
| Verify session log references handled | Validation | P1 |

### 5. Index Accuracy Tests (BLOCKING)

Verify master index is accurate and maintained.

**Coverage Target**: 100% index accuracy

| Test | Type | Priority |
|------|------|----------|
| Verify index includes all skills | Completeness | P0 |
| Verify index metadata accurate | Accuracy | P0 |
| Verify index searchable | Functionality | P1 |
| Verify index update mechanism | Maintenance | P1 |

### 6. Serena Compatibility Tests (BLOCKING)

Verify MCP integration still works.

**Coverage Target**: All MCP operations tested

| Test | Type | Priority |
|------|------|----------|
| Test mcp__serena__read_memory | Integration | P0 |
| Test mcp__serena__list_memories | Integration | P0 |
| Test mcp__serena__write_memory | Integration | P1 |
| Test mcp__serena__edit_memory | Integration | P1 |

## Test Cases

### Happy Path

| Test ID | Test | Input | Expected Output |
|---------|------|-------|-----------------|
| HP-01 | Read skill by semantic name | `read_memory("skill-qa-routing-blocking-gate")` | Skill-QA-003 content returned |
| HP-02 | List all skills | `list_memories()` | All ~15-20 domain libraries + atomics listed |
| HP-03 | Search for skill by topic | `search_nodes("test strategy")` | Relevant skills found (skills-qa, etc.) |
| HP-04 | Read master index | `read_memory("000-memory-index")` | Index with all skills returned |
| HP-05 | Agent references skill | AGENTS.md references skill by slug | Skill found and readable |

### Edge Cases

| Test ID | Test | Condition | Expected Behavior |
|---------|------|-----------|-------------------|
| EC-01 | Old numeric ID in session log | Historical reference to "Skill-QA-001" | No error (historical context preserved) |
| EC-02 | Duplicate semantic slugs | Two skills map to same slug | Migration blocked with error |
| EC-03 | Special chars in slug | Skill name has `/`, `\`, etc. | Slug sanitized per RFC 3986 |
| EC-04 | Very long skill name | Name exceeds slug length limit | Slug truncated with hash suffix |
| EC-05 | Skill moved between domains | Skill changes domain during consolidation | Old location deprecated, new location indexed |

### Error Cases

| Test ID | Test | Error Condition | Expected Handling |
|---------|------|-----------------|-------------------|
| ER-01 | Missing skill after migration | Skill in baseline, not in migrated set | Migration fails with diff report |
| ER-02 | Broken reference in AGENTS.md | Reference to old numeric ID in current docs | Grep test fails, blocks commit |
| ER-03 | Index out of sync | File added but index not updated | Index validation fails |
| ER-04 | Serena read fails | `read_memory("skill-new-slug")` returns error | Investigation triggered |
| ER-05 | Dangling cross-reference | Session log references non-existent skill | Warning logged (historical OK) |

## Coverage Analysis

### Pre-Migration Baseline Requirements

**BLOCKING**: These MUST complete before migration starts.

- [ ] **Skill inventory complete**: All 65 files cataloged with content hashes
- [ ] **Reference map complete**: All cross-references documented
- [ ] **Retrieval baseline established**: Current retrieval rate measured
- [ ] **Test data prepared**: Sample queries for regression testing

### Migration Execution Gates

**BLOCKING**: Migration cannot proceed to next phase until gates pass.

| Phase | Gate | Verification |
|-------|------|--------------|
| Rename | No files lost | File count matches baseline |
| Rename | All files renamed | Zero files with old pattern remain |
| Consolidate | Content preserved | Content hash verification passes |
| Consolidate | Target count met | 15-20 domain libraries exist |
| Index | Master index created | `000-memory-index.md` exists |
| Index | All skills indexed | Index count matches file count |

### Post-Migration Validation

**BLOCKING**: Cannot mark migration complete until validation passes.

- [ ] **Retrieval regression**: New retrieval rate ≥ baseline rate
- [ ] **Cross-references clean**: Zero dangling references in current docs
- [ ] **Serena compatibility**: All MCP operations work with new names
- [ ] **Index accuracy**: Index matches filesystem (100% accuracy)

## Test Execution Plan

### Phase 1: Pre-Migration Baseline (Est: 2 hours)

**Deliverable**: Baseline report with metrics

```bash
# 1. Catalog all skill files
find .serena/memories -name "skill*.md" -o -name "skills-*.md" | sort > baseline-files.txt

# 2. Compute content hashes
while read file; do
  echo "$(md5sum "$file" | cut -d' ' -f1) $file"
done < baseline-files.txt > baseline-hashes.txt

# 3. Find all cross-references
grep -r "skill-\|skills-\|Skill-" .agents/ src/ AGENTS.md > baseline-references.txt

# 4. Test current retrieval
# [Manual: Test read_memory, list_memories, search_nodes]
# Document results in baseline-retrieval.md
```

### Phase 2: Migration Execution (Est: 4 hours)

**Deliverable**: Migrated files + migration log

[Implementer handles this phase]

### Phase 3: Post-Migration Validation (Est: 3 hours)

**Deliverable**: Validation report

```bash
# 1. Verify no files lost
find .serena/memories -name "skill*.md" -o -name "skills-*.md" | sort > migrated-files.txt
diff baseline-files.txt migrated-files.txt
# Expected: Only renames, no deletions

# 2. Verify content preserved
while read file; do
  # Compare content hashes (accounting for renames)
  # Flag any content changes
done < migrated-files.txt

# 3. Verify no dangling references in CURRENT docs
grep -r "Skill-[A-Z].*-[0-9]\{3\}" .agents/ src/ AGENTS.md
# Expected: Zero matches in non-historical files

# 4. Verify master index exists and is accurate
test -f .serena/memories/000-memory-index.md || echo "FAIL: Index missing"
# [Manual: Verify index content matches files]

# 5. Test Serena compatibility
# [Manual: Test all MCP operations]
```

## Test Data Requirements

### Sample Queries for Retrieval Testing

| Query Type | Query | Expected Result |
|------------|-------|-----------------|
| Exact match | `read_memory("skill-qa-routing-blocking-gate")` | Skill-QA-003 |
| Domain search | `search_nodes("qa")` | skills-qa + related |
| Topic search | `search_nodes("test strategy")` | skills-qa, skills-testing |
| Cross-domain | `search_nodes("protocol compliance")` | skills-qa, skills-protocol |

### Reference Validation Patterns

| Pattern | Location | Action |
|---------|----------|--------|
| `Skill-[A-Z]+-[0-9]{3}` | Historical session logs | ALLOW (historical context) |
| `Skill-[A-Z]+-[0-9]{3}` | AGENTS.md | BLOCK (must update) |
| `Skill-[A-Z]+-[0-9]{3}` | src/*/**.md | BLOCK (must update) |
| `skill-domain-nnn` | Any location | BLOCK (old pattern) |

## Acceptance Criteria

### Migration Complete When:

1. **Zero Data Loss** [CRITICAL]
   - [ ] All 65 skill files migrated (100% coverage)
   - [ ] Content hash verification passes for all files
   - [ ] No skill content deleted or corrupted

2. **Consolidation Target Met** [HIGH]
   - [ ] 15-20 domain libraries created (within target range)
   - [ ] Individual atomic skills preserved where appropriate
   - [ ] Clear rationale documented for consolidation decisions

3. **Master Index Accurate** [CRITICAL]
   - [ ] `000-memory-index.md` exists
   - [ ] Index includes all migrated skills (100% coverage)
   - [ ] Index metadata accurate (name, domain, atomicity, impact)
   - [ ] Index searchable and navigable

4. **Retrieval Rate Maintained or Improved** [CRITICAL]
   - [ ] Post-migration retrieval rate ≥ pre-migration baseline
   - [ ] `read_memory` works with all new semantic slugs
   - [ ] `list_memories` returns all new names
   - [ ] `search_nodes` finds skills by topic

5. **Zero Dangling References in Current Docs** [CRITICAL]
   - [ ] AGENTS.md references updated to semantic slugs
   - [ ] Agent definitions (src/*/) updated to semantic slugs
   - [ ] No `Skill-Domain-NNN` pattern in current documentation
   - [ ] Historical session logs preserved (not updated)

6. **Serena MCP Compatibility** [CRITICAL]
   - [ ] `mcp__serena__read_memory` works with new names
   - [ ] `mcp__serena__list_memories` returns new names
   - [ ] `mcp__serena__write_memory` works (if tested)
   - [ ] `mcp__serena__edit_memory` works (if tested)

7. **Documentation Complete** [HIGH]
   - [ ] Migration guide documents process
   - [ ] Semantic slug naming conventions documented
   - [ ] Index maintenance process documented
   - [ ] Rollback procedure documented

### Quality Gates

| Gate | Threshold | Measurement |
|------|-----------|-------------|
| Data Loss | 0 files | File count diff |
| Content Corruption | 0 hash mismatches | Content hash verification |
| Retrieval Regression | ≥100% of baseline | Retrieval success rate |
| Dangling References | 0 in current docs | Grep pattern match count |
| Index Accuracy | 100% | Index vs filesystem diff |
| Consolidation Ratio | 65 → 15-20 files | File count |

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Data loss during consolidation | Medium | Critical | Content hash verification, backup before migration |
| Retrieval regression (agents can't find skills) | Medium | High | Baseline measurement, rollback plan |
| Broken references in agent definitions | High | High | Systematic grep search, update all matches |
| Index out of sync after migration | Medium | Medium | Automated index generation, validation script |
| Serena MCP incompatibility | Low | Critical | Test MCP operations pre/post migration |
| Performance degradation (fewer files) | Low | Low | Performance baseline, measure post-migration |

## Hard-to-Test Scenarios

| Scenario | Challenge | Recommended Approach |
|----------|-----------|---------------------|
| Historical session log references | Many old numeric IDs exist | Mark as historical (no update required), test only current docs |
| Agent learning from new skill names | Behavioral change, not functional | Manual testing with sample queries, observe agent behavior |
| Long-term index maintenance | Process, not one-time migration | Document process, create validation script, schedule periodic audits |
| Skill discoverability improvement | Subjective quality metric | Collect agent feedback, measure retrieval rate over time |

## Test Environment

**Environment**: Local development (D:\src\GitHub\rjmurillo\ai-agents)

**Tools Required**:

- Bash (WSL or Git Bash)
- md5sum (content hashing)
- grep (cross-reference search)
- Serena MCP (compatibility testing)
- Git (version control, rollback)

**Test Data**:

- Baseline files list (baseline-files.txt)
- Baseline content hashes (baseline-hashes.txt)
- Baseline cross-references (baseline-references.txt)
- Sample retrieval queries (see Test Data Requirements)

## Automation Strategy

| Test Area | Automate? | Rationale | Tool/Approach |
|-----------|-----------|-----------|---------------|
| File inventory | Yes | Repeatable, deterministic | Bash script with find + sort |
| Content hash verification | Yes | Repeatable, deterministic | Bash script with md5sum |
| Cross-reference grep | Yes | Repeatable, deterministic | Bash script with grep -r |
| Serena MCP operations | Partial | Manual verification needed | Manual test + session log |
| Retrieval rate measurement | Partial | Some manual judgment required | Mixed: automated query + manual assessment |
| Index accuracy check | Yes | Repeatable, deterministic | Bash script comparing index to filesystem |

**Automation Coverage Target**: 70% (automated scripts for deterministic checks, manual validation for behavioral/quality checks)

**Manual Testing Required**:

- Agent behavior with new skill names
- Skill discoverability (subjective quality)
- Index usability and navigation
- Cross-reference update verification (human review)

## Rollback Plan

**Trigger**: Any CRITICAL acceptance criterion fails

**Procedure**:

1. **Immediate**: Stop migration process
2. **Assessment**: Document which criterion failed and why
3. **Decision**: Fix forward or rollback
4. **If rollback**:
   - Restore from git: `git checkout HEAD -- .serena/memories/`
   - Verify baseline files restored: `diff baseline-files.txt <(find .serena/memories ...)`
   - Re-run baseline tests to confirm restoration
5. **If fix forward**:
   - Document issue in session log
   - Apply fix
   - Re-run failed test
   - Continue validation

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Migration completeness | 100% (65/65 files) | File count comparison |
| Data loss | 0 files | Content hash verification |
| Consolidation ratio | 65 → 15-20 files | File count |
| Retrieval rate | ≥100% of baseline | Retrieval success rate |
| Cross-reference cleanliness | 0 dangling refs in current docs | Grep match count |
| Index accuracy | 100% | Index vs filesystem diff |
| Serena MCP compatibility | 100% (all ops work) | Manual test results |

## Test Report Location

**Post-migration validation report**: `.agents/qa/semantic-slug-migration-test-report.md`

**Contents**:

- Summary of validation results
- Pass/fail status for each acceptance criterion
- Quality gate measurements
- Issues discovered
- Recommendations

## Related Skills

- **Skill-Documentation-001**: Systematic migration search (grep before migration)
- **Skill-Verification-003**: Verify artifact-API state match (validation pattern)
- **Skill-QA-001**: Test strategy gap checklist (ensure comprehensive coverage)

## Next Steps

1. **Implementer**: Review test strategy, confirm feasibility
2. **Implementer**: Execute Phase 1 (baseline)
3. **Implementer**: Execute Phase 2 (migration)
4. **QA**: Execute Phase 3 (validation)
5. **QA**: Create test report documenting results

## Notes

- Historical session logs should NOT be updated (preserve historical context)
- Only current documentation (AGENTS.md, src/*/) requires cross-reference updates
- Index maintenance process needs documentation for long-term sustainability
- Consider creating automated index validation script for ongoing use

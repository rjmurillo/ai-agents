# Forgetful Migration Plan

**Purpose**: Strategic plan for importing observation file learnings into Forgetful MCP for semantic search and cross-session retrieval.

**Created**: 2026-01-18
**Status**: Planning phase

## Migration Scope

**Source**: 34 observation files in `.serena/memories/` with 118+ learnings  
**Target**: Forgetful MCP semantic memory system  
**Timeline**: Phased approach (pilot → bulk → validation)

## Importance Score Mapping

Based on confidence levels in observation files:

| Observation Level | Forgetful Importance | Rationale |
|-------------------|---------------------|-----------|
| HIGH (Constraints - MUST) | 9-10 | Critical corrections preventing errors |
| MED (Preferences - SHOULD) | 7-8 | Quality improvements and workflow optimization |
| LOW (Notes for review) | 5-6 | Observations awaiting validation |

## Phase 1: Pilot Import (Testing Observations)

**Objective**: Validate migration pattern with high-value file

**File**: `testing-observations.md`  
**Learnings**: 16 HIGH + 17 MED + 1 LOW = 34 total  
**Why**: Most frequently updated (17 sessions), highest user correction rate

**Steps**:
1. Create Forgetful project: "ai-agents-testing" with repo "rjmurillo/ai-agents"
2. Import HIGH confidence learnings (importance: 9-10)
   - Tag with: ["testing", "pester", "powershell", "ci-cd", "constraint"]
   - Link related learnings (e.g., pipeline patterns link to array handling)
3. Import MED confidence learnings (importance: 7-8)
   - Tag with: ["testing", "preference", "workflow"]
4. Validate semantic search works correctly
5. Document import pattern for reuse

**Expected Outcome**: 34 memories created, searchable via semantic queries like "pester test failures" or "CI testing patterns"

## Phase 2: High-Value Domains (PR Review, GitHub, PowerShell)

**Files**:
- `pr-review-observations.md` (13 sessions, 9 HIGH + 8 MED)
- `github-observations.md` (7 sessions, 5 HIGH + 5 MED)
- `powershell-observations.md` (10 sessions, 13 HIGH + 5 MED)

**Approach**: Use pilot pattern, create domain-specific projects or tags

## Phase 3: Remaining Observation Files

**Files**: 31 remaining observation files  
**Approach**: Bulk import script using standardized pattern

## Import Pattern (Repeatable)

For each observation file:

1. **Extract metadata**:
   ```powershell
   $file = Get-Content .serena/memories/{domain}-observations.md
   $sessions = # Parse session count
   $lastUpdated = # Parse last updated date
   ```

2. **Parse learnings by confidence**:
   - HIGH section → importance 9-10
   - MED section → importance 7-8
   - LOW section → importance 5-6

3. **Create Forgetful memories**:
   ```powershell
   foreach ($learning in $highConfidence) {
       execute_forgetful_tool("create_memory", @{
           title = $learning.Title           # e.g., "100% test pass rate mandatory"
           content = $learning.Evidence       # Full evidence text
           context = "Observation from session {session}"
           keywords = @($domain, $learningType, $tags)
           tags = @("observation", $confidenceLevel, $domain)
           importance = 9  # HIGH
           project_ids = @($projectId)
           source_repo = "rjmurillo/ai-agents"
           source_files = @(".serena/memories/{domain}-observations.md")
           confidence = 1.0  # HIGH confidence observations
           encoding_agent = "claude-sonnet-4-5"
       })
   }
   ```

4. **Link related memories**:
   - Extract cross-references from "Related" sections
   - Create bidirectional links between related learnings

## Verification Criteria

After migration, validate:

| Check | Success Criteria |
|-------|------------------|
| Semantic search | Query "test failures" returns relevant testing memories |
| Project filtering | Can filter memories by "ai-agents-testing" project |
| Confidence mapping | HIGH observations have importance 9-10 |
| Link preservation | Related learnings are bidirectionally linked |
| Tag consistency | Memories properly tagged by domain and confidence |
| Provenance tracking | source_repo and source_files populated |

## Benefits of Forgetful Migration

1. **Semantic Search**: Query "how to handle bot comments" finds PR review patterns
2. **Cross-Session Retrieval**: Patterns available without re-reading observation files
3. **Knowledge Graph**: Relationships between learnings discoverable
4. **Temporal Tracking**: Can query "recent learnings" or filter by importance
5. **Project Scoping**: Memories linked to specific project contexts

## Alternative: Hybrid Approach

**Keep both systems**:
- **Serena observations**: Authoritative source, human-readable, version controlled
- **Forgetful memories**: Semantic search layer, cross-session queries

**Workflow**:
1. Learnings captured in Serena observations (via /reflect)
2. Periodic batch import to Forgetful for semantic search
3. Use Forgetful for discovery, Serena for canonical reference

## Migration Status

| Phase | Status | Memories | Notes |
|-------|--------|----------|-------|
| **Phase 1** | COMPLETED | 33 | Testing domain pilot |
| **Phase 2** | COMPLETED | 30 | PR review, GitHub, PowerShell |
| **Phase 3** | COMPLETED | 30 | Architecture, CI, Git, Validation |
| **Phase 4** | COMPLETED | 239 | Bulk import remaining HIGH learnings |
| **Phase 5** | COMPLETED | 124 | MED confidence preferences and edge cases |
| **Phase 6** | COMPLETED | 6 | LOW confidence notes for review |

**Total Memories**: 462 in Forgetful
**Total Projects**: 26 domain-specific projects
**Migration Complete**: 2026-01-18

## Phase 4 Completion Summary (2026-01-18)

- **Dry-run prediction**: 87 HIGH learnings
- **Actual imports**: 30 (many already existed from Phases 1-3)
- **New projects created**: 5 (IDs 17-21)
- **Auto-linking**: Working correctly
- **Semantic search**: Validated with 3 test queries
- **Provenance**: source_repo, source_files populated

## Completed Steps

1. Phase 1 pilot (testing-observations.md) - DONE
2. Phase 2 high-value domains - DONE
3. Phase 3 remaining observation files - DONE
4. Phase 4 bulk import of remaining HIGH learnings - DONE

## Related

- `using-forgetful-memory.md` - Forgetful usage patterns
- `curating-memories.md` - Memory maintenance strategies
- `memory-observations.md` - Memory system patterns
- `skill-integration-plan.md` - Skill enhancement with HIGH confidence patterns

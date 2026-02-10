# Memory System Improvement Plan: Context Engineering Integration

**Date**: 2026-02-09
**Status**: ⚠️ SUPERSEDED - Skill-localized approach chosen instead
**Priority**: HIGH
**Source**: Context engineering research + critical analysis

> **Implementation Decision**: The [skill-localized plan](memory-skill-context-engineering-improvements.md) was chosen over this system-wide approach due to lower risk, faster implementation, and self-contained changes. That plan has been completed (2026-02-09). This document is preserved for reference and potential future phases.

## Executive Summary

Prioritized plan to integrate context engineering principles into ai-agents memory system. Addresses three critical gaps: interface consolidation, token cost visibility, and memory size enforcement. Maintains existing strengths (Serena-first, just-in-time, sub-agents) while improving usability and token efficiency.

**Expected Impact**: 8,000+ token savings per task, 80% reduction in interface confusion, 100% cost visibility

## Success Metrics

| Metric | Current | Target | Measurement |
|--------|---------|--------|-------------|
| Interface decision time | ~60s (user confusion) | <10s | User testing |
| Token cost visibility | 0% | 100% | All memory listings show counts |
| Memory atomicity (< 2K chars) | ~70% | 95% | Automated size checks |
| Wasteful retrieval | 87% (large memories) | <10% | Token usage logs |
| User satisfaction | 4/10 (fragmented) | 8/10 | Post-implementation survey |

## Priority Matrix

Using RICE framework (Reach × Impact × Confidence / Effort):

| Initiative | Reach | Impact | Confidence | Effort | RICE Score | Priority |
|------------|-------|--------|------------|--------|-----------|----------|
| P0: Interface consolidation | 100% | 3 | 0.9 | 5 | 54 | 🔴 Critical |
| P0: Token cost visibility | 100% | 3 | 0.95 | 3 | 95 | 🔴 Critical |
| P1: Memory decomposition | 60% | 3 | 0.8 | 8 | 18 | 🟡 High |
| P2: Compaction automation | 40% | 2 | 0.7 | 6 | 9.3 | 🟢 Medium |
| P3: Pollution curation | 20% | 1 | 0.6 | 2 | 6 | 🔵 Low |

## Phase 1: Critical Fixes (2-3 weeks)

### P0.1: Interface Consolidation

**Problem**: 4 overlapping memory interfaces create confusion and violate "unambiguous tool design" principle.

**Solution**: Deprecate redundant paths, enforce single decision matrix

**Implementation**:

1. **Update CLAUDE.md** (Week 1, Day 1)
   - Add Memory Interface Decision Matrix as Section 4
   - Make it auto-loaded (always in context)
   - Format as table for quick scanning

```markdown
## Memory Interface Decision Matrix

| Scenario | Use | Why | Command |
|----------|-----|-----|---------|
| Quick search from CLI | Slash command | Instant, no agent overhead | `/memory-search {query}` |
| Deep exploration | context-retrieval agent | Graph traversal, artifact reading | `Task(subagent_type="context-retrieval")` |
| Script automation | Memory Router skill | PowerShell, testable, error handling | `Search-Memory.ps1 -Query "..."` |
| Agent programming | Direct MCP (last resort) | Full control when abstractions insufficient | `mcp__serena__read_memory(...)` |
```

2. **Deprecate Forgetful slash commands** (Week 1, Day 2-3)
   - Mark `/memory-*` commands as deprecated in help text
   - Redirect to Memory Router skill for scripting
   - Keep `/memory-search` for quick CLI lookups (single exception)
   - Document migration path in `.claude/commands/forgetful/README.md`

3. **Update context-retrieval agent** (Week 1, Day 4-5)
   - Add decision matrix reference to agent prompt
   - Document when to use agent vs direct tools
   - Add examples of complex vs simple queries

**Verification**:
- Agent transcripts show correct interface selection
- No user reports of "which one do I use?"
- 90%+ of memory operations use appropriate interface

**Success Criteria**:
- Decision time < 10 seconds
- Interface selection accuracy > 90%
- User satisfaction improvement from 4/10 to 7/10

---

### P0.2: Token Cost Visibility

**Problem**: No token counts in memory listings. Agents cannot make informed ROI decisions.

**Solution**: Add token counting to all memory operations

**Implementation**:

1. **Create token counting utility** (Week 2, Day 1-2)
   - Python script: `scripts/memory/count-tokens.py`
   - Uses tiktoken library (cl100k_base encoding)
   - Caches counts in `.serena/.token-cache.json`
   - Invalidates cache on file modification

```python
def count_memory_tokens(memory_path: str) -> int:
    """Count tokens in memory file using tiktoken."""
    import tiktoken
    enc = tiktoken.get_encoding("cl100k_base")
    with open(memory_path) as f:
        return len(enc.encode(f.read()))
```

2. **Update memory-index.md** (Week 2, Day 3)
   - Add token count column to main table
   - Format: `| memory-name.md (1,200 tokens) |`
   - Auto-generate via pre-commit hook

```markdown
| Task Keywords | Essential Memories (tokens) |
|---------------|---------------------------|
| github pr cli | [skills-github-cli-index](skills-github-cli-index.md) (3,200) |
```

3. **Update Serena list_memories** (Week 2, Day 4-5)
   - Modify MCP to include token count in output
   - Format: `"memory_name.md (1,234 tokens)"`
   - Requires Serena MCP update (coordinate with maintainer)

4. **Add token budget warnings** (Week 2, Day 5)
   - Warning if single memory > 5,000 tokens
   - Suggestion to decompose if > 10,000 tokens
   - Track cumulative token usage per session

**Verification**:
- All memory listings show token counts
- Pre-commit hook validates counts are current
- Agents reference token costs in decision logs

**Success Criteria**:
- 100% of memory operations show cost upfront
- Agents avoid reading oversized memories
- Token waste reduced by 50%+

---

## Phase 2: Structural Improvements (3-4 weeks)

### P1: Memory Decomposition Enforcement

**Problem**: `skills-github-cli.md` and similar large files waste 87-92% of tokens per read.

**Solution**: Execute Issue #239 decomposition + enforce size limits going forward

**Implementation**:

1. **Execute Issue #239 decomposition** (Week 3-4)
   - Split `skills-github-cli.md` (38,000 chars) into 11 focused files
   - Target structure from `memory-size-001-decomposition-thresholds`
   - Update memory-index with new paths
   - Archive original file in `.serena/memories/archive/`

Expected token savings:

| Scenario | Before | After | Savings |
|----------|--------|-------|---------|
| PR review | 9,500 | 1,200 | 8,300 (87%) |
| Issue triage | 9,500 | 900 | 8,600 (91%) |
| Release | 9,500 | 800 | 8,700 (92%) |
| API debug | 9,500 | 1,500 | 8,000 (84%) |

2. **Create pre-commit size validator** (Week 4, Day 1-2)
   - Python script: `scripts/memory/validate-size.py`
   - Thresholds from `memory-size-001-decomposition-thresholds`:
     - MAX_CHARS: 10,000 (~2,500 tokens)
     - MAX_SKILLS: 15 per file
     - MAX_CATEGORIES: 3-5 per file
   - Fails commit if exceeded, suggests decomposition

```python
THRESHOLDS = {
    "max_chars": 10_000,
    "max_skills": 15,
    "max_categories": 5
}

def validate_memory_size(memory_path: str) -> tuple[bool, str]:
    """Returns (is_valid, message)"""
    # Check character count, skill count, category count
    # Return False with decomposition suggestion if exceeded
```

3. **Update memory creation guidelines** (Week 4, Day 3)
   - Add to `.serena/README.md`
   - Document decomposition triggers
   - Provide examples of good atomicity

4. **Add to session protocol** (Week 4, Day 4-5)
   - Memory size validation as quality gate
   - Session logs must show size compliance
   - Flag for review if near thresholds

**Verification**:
- No memories > 10,000 chars
- Pre-commit hook blocks oversized memories
- Token waste < 10% per retrieval

**Success Criteria**:
- 95% of memories under size threshold
- 8,000+ token savings per task
- Retrieval precision > 90%

---

## Phase 3: Automation (2-3 weeks)

### P2: Context Compaction Automation

**Problem**: No explicit compaction when sessions approach context limits.

**Solution**: Implement session log summarization for long-horizon tasks

**Implementation**:

1. **Create session compaction tool** (Week 5-6)
   - Python script: `scripts/memory/compact-session.py`
   - Triggers at 50+ turns or 80% context capacity
   - Uses Claude API to summarize earlier turns
   - Preserves: decisions, constraints, architectural choices
   - Discards: exploratory dead-ends, redundant outputs

2. **Strategies** (from context engineering analysis):
   - **Recursive summarization**: Condense turns 1-25, keep 26+ full
   - **Hierarchical summarization**: Maintain phase structure
   - **Targeted summarization**: Focus on task-relevant information

3. **Integration points**:
   - Session protocol: Optional compaction after 50 turns
   - Session-end skill: Offer compaction before closing
   - Manual: `/compact-session` command

**Verification**:
- Compacted sessions maintain critical information
- Token reduction 40-60% for long sessions
- No loss of architectural decisions

**Success Criteria**:
- Long sessions (100+ turns) don't hit context limits
- Compaction preserves 100% of critical decisions
- 50% token reduction for compacted sections

---

### P3: Memory Pollution Curation

**Problem**: Stale memories accumulate without active curation process.

**Solution**: Automated obsolescence detection + quarterly review

**Implementation**:

1. **Stale memory detector** (Week 7)
   - Python script: `scripts/memory/detect-stale.py`
   - Flags memories not accessed in 6 months
   - Checks if referenced code still exists
   - Suggests review or archival

2. **Quarterly curation process**:
   - Run detector, generate report
   - Review flagged memories
   - Archive obsolete, update stale
   - Document in retrospective

3. **Memory health dashboard**:
   - Total memories
   - Average age
   - Obsolescence rate
   - Retrieval frequency

**Verification**:
- Detector identifies stale memories accurately
- Quarterly reviews documented
- Obsolescence rate < 5% per quarter

**Success Criteria**:
- No memories untouched > 12 months
- Obsolescence explicitly marked
- Retrieval relevance > 85%

---

## Implementation Roadmap

```text
Week 1-2: P0.1 Interface Consolidation
  ├─ Day 1: Update CLAUDE.md with decision matrix
  ├─ Day 2-3: Deprecate redundant slash commands
  ├─ Day 4-5: Update context-retrieval agent
  └─ Week 2: P0.2 Token cost visibility

Week 3-4: P1 Memory Decomposition
  ├─ Week 3: Execute Issue #239
  └─ Week 4: Size enforcement + guidelines

Week 5-6: P2 Context Compaction (if needed)

Week 7: P3 Pollution Curation (if capacity allows)
```

## Dependencies

| Initiative | Depends On | Blocker Type |
|------------|------------|--------------|
| P0.2 Token visibility | tiktoken library | External |
| P0.2 Serena integration | Serena MCP update | Coordination |
| P1 Decomposition | Issue #239 prioritization | Planning |
| P2 Compaction | Claude API access | Infrastructure |

## Risk Mitigation

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| User rejects interface changes | Low | High | Gradual deprecation, clear migration docs |
| Token counting inaccurate | Medium | Medium | Validate against manual counts, use tiktoken |
| Decomposition breaks workflows | Low | High | Archive originals, update incrementally |
| Compaction loses info | Medium | High | Manual review of first 5 compactions |

## Success Validation

**After Phase 1 (Week 3)**:
- User testing with 5 representative tasks
- Measure interface selection accuracy
- Collect satisfaction feedback
- Token cost visibility at 100%

**After Phase 2 (Week 5)**:
- Measure token savings per task (target: 8,000+)
- Validate memory atomicity (target: 95%)
- Retrieval precision analysis (target: >90%)

**After Phase 3 (Week 7)**:
- Long-session compaction effectiveness
- Stale memory detection accuracy
- Quarterly curation process completion

## Rollback Plan

If any phase fails validation:

1. **Interface consolidation**: Revert CLAUDE.md changes, un-deprecate commands
2. **Token visibility**: Remove counts from displays, keep caching for metrics
3. **Decomposition**: Restore archived originals, keep new files for future
4. **Compaction**: Disable auto-compaction, keep manual option
5. **Pollution curation**: Continue without automation, manual review only

## Related Documents

- [Context Engineering Analysis](/.agents/analysis/memory-system-context-engineering-analysis.md)
- [Context Engineering Research](/.agents/analysis/context-engineering.md)
- [Memory System Fragmentation Tech Debt](/.serena/memories/memory-system-fragmentation-tech-debt.md)
- [Memory Size Decomposition Thresholds](/.serena/memories/memory-size-001-decomposition-thresholds.md)
- Issue #239: Memory Decomposition

## Open Questions

1. Should Serena MCP token counting be contribution to upstream, or fork?
2. What's the priority vs other roadmap items (v0.3.1, Python migration)?
3. Who owns quarterly curation reviews (user or automation)?
4. Should compaction be opt-in or automatic?

---

**Estimated Total Effort**: 6-7 weeks (full-time equivalent)
**Expected ROI**: 8,000+ tokens/task × ~20 tasks/week = 160,000 tokens/week saved
**User Satisfaction**: 4/10 → 8/10 (interface clarity + cost visibility)

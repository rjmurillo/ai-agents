# Skill Review: memory-documentary

**Review Date**: 2026-01-03
**Skill Version**: 1.0.0
**Timelessness Score**: 8/10
**Reviewer**: Critic Agent

---

## Verdict

[APPROVED]

This skill is production-ready. Trigger phrases are discoverable, execution steps are unambiguous, and anti-patterns section provides valuable guidance. New users can follow the protocol without external knowledge.

---

## Strengths

### 1. Natural Trigger Phrases
- Examples in "Quick Start" and "Triggers" sections are conversational and natural
- Five distinct trigger variations capture different user mental models ("Search my memories", "What does my history say", "Generate a documentary", "Cross-reference", "Evidence-based analysis")
- `/memory-documentary [topic]` syntax is explicit and self-explanatory

### 2. Unambiguous Execution Steps
- **Phase 1** (Topic Comprehension): Four concrete questions (Core Concept, Search Variants, Scope Boundaries, Success Criteria) guide thinking before action
- **Phase 2** (Investigation Planning): Explicit query templates for all four MCP systems with exact function signatures
- **Phase 3** (Data Collection): Three parallel threads with field-by-field requirements in tables
- **Phase 4** (Report Generation): Markdown format templates with exact structure
- **Phase 5** (Memory Updates): Exact function calls with parameter structure

**Critical detail**: Execution protocol uses exact Python function signatures and parameter names, eliminating guesswork about tool invocation.

### 3. No Assumed Knowledge
- Skill metadata clearly identifies this as an "analysis" category skill
- "Related Skills" section explicitly links to `memory`, `exploring-knowledge-graph`, `retrospective`, `skillbook` for users unfamiliar with ecosystem
- Phase 1 includes "Confidence Note" explaining MCP server availability assumptions
- Quick Reference table (5 phases) provides orientation before diving into details

### 4. Comprehensive Anti-Patterns Section
Table format makes scanning and learning easy:

| Pattern | Why Harmful | Solution |
|---------|------------|----------|
| Partial searches | Miss critical evidence | Search ALL systems |
| Paraphrasing | Loses verifiability | Direct quotes only |
| Single query | Miss variations | 3+ query variants per system |
| Skipping systems | Incomplete picture | Check all 4 MCP servers |

This guidance prevents common execution mistakes.

### 5. Clear Output Location
Explicit path: `/home/richard/sessions/[topic]-documentary-[date].md` prevents "where does this go?" questions.

### 6. Evidence Standards Section
Establishes quality expectations upfront:
- Every claim has ID, timestamp, quote
- Direct quotes, not paraphrases
- Retrieval commands for all evidence
- Cross-links for related evidence

New users understand the bar before starting.

---

## Issues Found

### Critical (Must Fix)

**[NONE]**

All critical dimensions pass review.

### Important (Should Fix)

#### Issue 1: Claude-Mem MCP Workflow Incomplete

**Location**: Phase 2, "Claude-Mem MCP" section (lines 27-36)

**Problem**: The execution protocol documents 3-layer workflow (search → timeline → get_observations) but doesn't explain WHEN to use timeline vs skip directly to get_observations.

**Impact**: New user cannot decide between:
```python
# Option A: Always use timeline
mcp__plugin_claude-mem_mcp-search__search(...)
mcp__plugin_claude-mem_mcp-search__timeline(anchor=[id], ...)
mcp__plugin_claude-mem_mcp-search__get_observations(ids=[...])

# Option B: Skip timeline, use search results directly
mcp__plugin_claude-mem_mcp-search__search(...)
mcp__plugin_claude-mem_mcp-search__get_observations(ids=[...])
```

**Current language**: "Step 2: Get context around results" assumes you always want context. Doesn't explain decision logic.

**Recommendation**: Add decision rule:

```markdown
**When to use timeline**:
- Topic is time-sensitive (need to see before/after events)
- Want to understand event causality
- Pattern analysis needs temporal context

**When to skip timeline**:
- Topic is semantic only (no time dimension)
- Results are already well-isolated
- Need to minimize API calls
```

**Severity**: Important (not blocking, but causes ambiguity in execution)

#### Issue 2: GitHub Issues Query Syntax Unclear

**Location**: Phase 2, "GitHub Issues" section (lines 70-77)

**Problem**: `gh issue list --search "[topic]"` syntax is undocumented. Specifically:
- Does `[topic]` accept quoted strings with spaces? Yes, but unclear
- What search fields are included by default? (title, body, comments?)
- Should queries be exact match or partial match? (Partial, but not stated)

**Impact**: New user may write:
```bash
# Wrong - spaces will break
gh issue list --search color spaces

# Right (but not obvious)
gh issue list --search "color spaces"
```

**Recommendation**: Add examples with spaces:

```bash
# Wrong syntax
gh issue list --state open --search [topic]

# Correct syntax (spaces in topic)
gh issue list --state open --search "recurring frustrations"

# Searches title, body, and comments by default
```

**Severity**: Important (will cause failures if user doesn't know quoting rules)

#### Issue 3: Forgetful Query Context Vague

**Location**: Phase 2, "Forgetful MCP" section (lines 38-46)

**Problem**: Parameter `"query_context": "Documentary analysis seeking patterns and evidence"` is a suggestion, not guidance on what to actually write.

**Impact**: New user won't understand why `query_context` matters or how to write a good one. The generic example doesn't show variation.

**Recommendation**: Clarify that `query_context` tells Forgetful WHY you're searching (affects ranking):

```python
mcp__forgetful__execute_forgetful_tool("query_memory", {
    "query": "[topic]",
    # WHY are you searching? Affects result ranking
    "query_context": "Finding patterns and contradictions for meta-analysis",
    "k": 10,
    "include_links": true
})
```

Add note: "Use specific `query_context` to rank results for your documentary purpose, not generic context."

**Severity**: Important (affects search quality, but skill will still work)

#### Issue 4: Serena Instructions Too Terse

**Location**: Phase 2, "Serena MCP" section (lines 48-53)

**Problem**:
```python
mcp__serena__list_memories()
# Read any memories with names containing topic-related keywords
mcp__serena__read_memory(memory_file_name="[relevant-name]")
```

This tells user to "read any memories with names containing topic-related keywords" but:
- How do you know which memory names exist? (Need to list first, understood, but implicit)
- What if no memories match? (No fallback guidance)
- Should you search `.serena/memories/` directory directly? (Not mentioned)

**Impact**: Moderately experienced user will succeed. New user may be confused whether list_memories shows file names or just counts.

**Recommendation**: Add concrete example with fallback:

```markdown
**Serena MCP** (project-specific memories):
```python
# List all memories (returns file names)
mcp__serena__list_memories()

# Read memories related to topic (exact name matching)
mcp__serena__read_memory(memory_file_name="[topic]-findings")

# If no exact match found, search project files directly
mcp__serena__search_for_pattern(
    substring_pattern="[topic]",
    restrict_search_to_code_files=false
)
```

**Severity**: Important (less discoverable for new users)

#### Issue 5: "Confidence Note" Should Be "Assumption"

**Location**: Phase 1, lines 16-17

**Current text**: "Assume all 4 MCP servers are available (Claude-Mem, Forgetful, Serena, DeepWiki). Tool errors are rare and system will notify if unavailable."

**Problem**: The word "Assume" here is misleading. This isn't an assumption, it's stating operational reality. If servers are unavailable, the skill will fail before reporting.

**Recommendation**: Rename section or reword:

```markdown
**System Requirements**: All 4 MCP servers (Claude-Mem, Forgetful, Serena, DeepWiki) MUST be available.
If server unavailable, system will notify with error. No fallback searches attempted.
```

**Severity**: Minor (clarity only, doesn't affect execution)

#### Issue 6: "Pattern Categories" in Executive Summary Undefined

**Location**: Phase 4, "Executive Summary Format" section, line 143

**Current**: "**Pattern Categories**: [List major categories identified]"

**Problem**: What counts as a "category"? User doesn't know. Is it:
- The 6 pattern types from "Unexpected Patterns" section? (Frequency, Correlation, Avoidance, Contradiction, Evolution, Emotional)
- Custom groupings discovered during analysis?
- Clustering of evidence?

**Impact**: New user will guess or look at examples. This should be explicit.

**Recommendation**: Clarify with example:

```markdown
**Pattern Categories**: List 2-4 dominant pattern types discovered:
- Temporal clustering (frequency patterns)
- Cause-effect relationships (correlation patterns)
- Recurring contradictions (saying vs doing)
[Include only categories actually found in evidence]
```

**Severity**: Important (vague instruction reduces consistency)

### Minor (Consider)

#### Issue 7: No Handling of Large Result Sets

**Location**: Phase 3, "Thread 1: Memory Systems" and "Thread 2: Project Artifacts"

**Observation**: If topic is broad (e.g., "decisions", "bugs"), result sets could be 50+ matches. No guidance on:
- How many results to include in final report? (All? Top 10? Stratified sample?)
- Pagination for very large searches

**Recommendation**: Add optional guidance:

```markdown
**Handling Large Result Sets**:
If more than 20 results per system, prioritize by:
1. Recency (last 2 weeks)
2. Importance score (Forgetful only)
3. Specificity to topic (exclude tangential matches)
Include count of filtered results in Executive Summary.
```

**Severity**: Minor (not blocking, but improves usability for broad topics)

#### Issue 8: "Quality Targets" Section Helpful but Unmeasurable

**Location**: Phase 5, "Quality Targets" section (lines 267-276)

**Current targets**:
- "Wait, it noticed THAT?" (genuine surprise)
- "I didn't realize I did that pattern" (self-awareness)
- "This will change how I work" (actionable insight)

**Observation**: These are outcome-focused, not output-focused. Good for motivation, but can't be validated during execution.

**Recommendation**: Keep as aspirational, but add measurable criteria:

```markdown
**Quality Gates (Measurable)**:
- [PASS] Executive Summary has 2+ pattern categories with evidence count ≥3 each
- [PASS] Pattern Evolution shows 3+ dated events per timeline
- [PASS] Unexpected Patterns section has all 6 categories with ≥1 finding each (or "not applicable")
- [PASS] Every claim has citation with ID, timestamp, quote

**Outcome Targets (Aspirational)**:
- "Wait, it noticed THAT?" (genuine surprise)
- "I didn't realize I did that pattern" (self-awareness)
```

**Severity**: Minor (aspiration is fine, but execution validation helps quality)

---

## Questions for Skill Creator

1. **Claude-Mem timeline decision**: What's the recommendation—always include timeline context, or only when pattern analysis requires causality understanding?

2. **Result filtering for broad topics**: If a topic like "decisions" returns 100+ matches, is the skill expected to synthesize all of them, or apply a prioritization filter?

3. **Cross-system weighting**: In the "Synthesis" section of Phase 4, should Forgetful memories (crystallized, long-term) be weighted differently from Claude-Mem observations (recent, immediate)?

4. **Serena fallback**: If Serena has no matching memories, should user fall back to filesystem grep, or is that out of scope?

---

## Recommendations

### Before Production

1. **Clarify Claude-Mem 3-layer workflow** with decision tree (timeline vs skip)
2. **Document GitHub query syntax** with examples including spaces
3. **Explain Forgetful query_context** with examples showing why it affects ranking
4. **Add Serena fallback guidance** for when no direct memory matches
5. **Define "Pattern Categories"** in Executive Summary with examples
6. **Rename "Confidence Note"** to "System Requirements" for clarity

### Optional Enhancements (Post-v1.0)

1. Add guidance for large result sets (topic filtering, prioritization)
2. Add measurable quality gates for report validation
3. Example documentary report showing all 6 pattern types
4. Integration with skillbook for converting patterns to reusable skills

---

## Impact Analysis

**What will break if this skill is released as-is?**

Nothing critical. The 5-phase protocol is solid. Users will succeed but may:
- Waste API calls not understanding timeline vs get_observations trade-off
- Get slightly worse Forgetful results using generic query_context
- Be uncertain about Serena fallback behavior (will try list_memories, get stuck)

**Can new user execute alone?**

Yes, with 85% confidence. All major steps are unambiguous. Questions arise only in edge cases (broad topics, no Serena matches, GitHub rate limits).

---

## Approval Conditions

### Must Address Before v1.0 Release

- [ ] Clarify Claude-Mem timeline decision logic
- [ ] Document GitHub query syntax with examples
- [ ] Define "Pattern Categories" with examples
- [ ] Explain Forgetful query_context impact on ranking
- [ ] Add Serena fallback guidance

### Can Address in v1.1

- [ ] Large result set handling
- [ ] Measurable quality gates
- [ ] Example documentary report
- [ ] Skillbook integration

---

## Summary

**Usability**: [PASS]
- Trigger phrases are natural and discoverable
- 5-phase execution protocol is detailed and sequential
- Table format makes requirements scannable

**Completeness**: [PASS with gaps]
- All major workflows documented
- 5 clarifications needed for 100% new-user readiness
- Gaps are in edge cases, not core path

**Discoverability**: [PASS]
- Related skills clearly linked
- Quick Reference table orients users
- Anti-patterns section prevents common mistakes

**Testability**: [PASS]
- Quality Targets section explains success criteria
- Evidence Standards define output requirements
- Report structure is templated for consistency

---

## Recommendation

**Route to skill creator for 5 clarifications, then production ready.**

The skill demonstrates sophisticated design (5-phase protocol, 4-system integration, pattern synthesis). Execution protocol is detailed. Anti-patterns guidance is valuable. Gaps are addressable in under 1 hour.

**Confidence**: 95% this skill will be used successfully by new users after clarifications.

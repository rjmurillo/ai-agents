# Memory Documentary Execution Protocol

Detailed instructions for generating evidence-based documentary reports.

---

## Phase 1: Topic Comprehension (RE2)

Before searching, re-read the topic and answer:

1. **Core Concept**: What is the central subject to investigate?
2. **Search Variants**: What alternative phrasings or related terms should be included?
3. **Scope Boundaries**: What is explicitly IN scope? What is OUT of scope?
4. **Success Criteria**: What would make this analysis valuable?

**Confidence Note**: Assume all 4 MCP servers are available (Claude-Mem, Forgetful, Serena, DeepWiki). Tool errors are rare and system will notify if unavailable.

---

## Phase 2: Investigation Planning (Plan-and-Solve)

Create an explicit search plan BEFORE executing queries:

### Memory Systems Queries

**Claude-Mem MCP** (timeline-based):

```python
# Step 1: Search for index
mcp__plugin_claude-mem_mcp-search__search(query="[topic]")

# Step 2: Get context around results
mcp__plugin_claude-mem_mcp-search__timeline(anchor=[observation_id], depth_before=3, depth_after=3)

# Step 3: Fetch full details
mcp__plugin_claude-mem_mcp-search__get_observations(ids=[filtered_ids])
```

**Forgetful MCP** (semantic):

```python
mcp__forgetful__execute_forgetful_tool("query_memory", {
    "query": "[topic]",
    "query_context": "Documentary analysis seeking patterns and evidence",
    "k": 10,
    "include_links": true
})
```

**Serena MCP** (project-specific):

```python
mcp__serena__list_memories()
# Read any memories with names containing topic-related keywords
mcp__serena__read_memory(memory_file_name="[relevant-name]")
```

**DeepWiki MCP** (documentation):

- Query for framework or concept documentation relevant to topic

### Project Artifacts

List specific grep patterns and file paths:

| Directory | Pattern | Purpose |
|-----------|---------|---------|
| `.agents/retrospective/` | `grep -r "[topic]"` | Learning extractions |
| `.agents/sessions/` | `grep -l "[topic]"` | Session logs |
| `.agents/analysis/` | List files | Research reports |
| `.agents/architecture/` | ADR keywords | Decisions |

### GitHub Issues

```bash
# Open issues
gh issue list --state open --search "[topic]" --json number,title,body,comments,labels,createdAt

# Closed issues
gh issue list --state closed --search "[topic]" --json number,title,body,comments,labels,createdAt,closedAt
```

---

## Phase 3: Data Collection

### Thread 1: Memory Systems

Execute queries from Phase 2 plan. For each result, capture:

| Field | Required |
|-------|----------|
| Memory/Observation ID | Yes |
| Source system | Yes |
| Timestamp | Yes |
| Importance score | If available |
| Direct quote | Yes |
| Related IDs | If available |

### Thread 2: Project Artifacts

For each matching file:

| Field | Required |
|-------|----------|
| File path | Yes |
| Line numbers | For key passages |
| Direct quotes | Yes |
| Git date | If possible (`git log -1 --format=%ai [file]`) |

### Thread 3: GitHub Issues

For each relevant issue:

| Field | Required |
|-------|----------|
| Issue number | Yes |
| Link | Yes |
| State | Yes (OPEN/CLOSED) |
| Created date | Yes |
| Closed date | If closed |
| Labels | Yes |
| Key quotes | From body and comments |
| Related PRs | If any |

**Error Handling**: If GitHub API rate limits occur, note timestamp and include partial results.

---

## Phase 4: Report Generation

### Executive Summary Format

```markdown
## Executive Summary

**Key Finding**: [One sentence summary]

**Timeline**: [Earliest date] to [Most recent date]

**Evidence Count**:
- Memories: N
- Observations: N
- Issues: N
- Files: N

**Pattern Categories**: [List major categories identified]
```

### Evidence Trail Format

For each major finding:

```markdown
### Finding: [Title]

**Memory Evidence**:
- **ID**: Forgetful Memory #123
- **Retrieval**: `execute_forgetful_tool("get_memory", {"memory_id": 123})`
- **Created**: 2025-12-15
- **Importance**: 8/10
- **Quote**: "Direct quote from memory content"
- **Links**: Related to Memory #456, #789

**Document Evidence**:
- **Path**: `.agents/retrospective/2025-12-15-session-review.md`
- **Lines**: 45-52
- **Quote**: "Direct quote from document"
- **Git Date**: 2025-12-15 14:32:00

**GitHub Evidence**:
- **Issue**: [#234](https://github.com/owner/repo/issues/234)
- **State**: CLOSED
- **Created**: 2025-12-10
- **Closed**: 2025-12-18
- **Labels**: bug, priority:high
- **Quote**: "Direct quote from issue body or comment"
```

### Pattern Evolution Format

**Section Header**: `### Pattern Evolution: [Pattern Name]`

**Timeline Format**:

```text
2025-11-01: [Observation #101] - Initial belief: "[quote]"
2025-11-15: [Memory #202] - First iteration: "[quote]"
2025-12-01: [Issue #303] - Technical response
2025-12-15: [Session log] - Current state: "[quote]"
```

**Before/After Table**:

| Aspect | Before | After |
|--------|--------|-------|
| Belief | [Previous] | [Current] |
| Behavior | [Previous] | [Current] |
| Trigger | N/A | [Specific incident with receipt] |

### Unexpected Patterns Format

Analyze across categories with boundaries:

**Frequency Patterns** (temporal clustering):

- Time of day patterns (e.g., "80% of errors after 10pm")
- Day of week patterns (e.g., "Friday commits have 2x bug rate")
- Clustering (e.g., "issues come in bursts of 3-5")

**Correlation Patterns** (co-occurrence):

- Sequential (e.g., "X always happens before Y")
- Prerequisite (e.g., "A implies B follows")
- Simultaneous (e.g., "When X, also Y")

**Avoidance Patterns** (conspicuous absence):

- Topics never mentioned
- Tools never used
- Questions never asked

**Contradiction Patterns** (saying vs doing):

- Stated preference vs actual behavior
- Documentation vs implementation
- Protocol vs practice

**Evolution Patterns** (change over time):

- Recursive loops
- Pendulum swings
- Progressive refinement

**Emotional Patterns** (sentiment markers):

- Frustration markers (e.g., "again", "still broken")
- Excitement markers (e.g., exclamation, "finally")
- Fatigue markers (e.g., shorter messages)

---

## Phase 5: Memory Updates

After report completion, update systems:

### Forgetful Update

```python
mcp__forgetful__execute_forgetful_tool("create_memory", {
    "title": "[Topic] Meta-Pattern Analysis",
    "content": "[Summary of discovered meta-pattern]",
    "context": "Documentary analysis of [topic]",
    "keywords": ["meta-analysis", "[topic-keywords]"],
    "tags": ["documentary", "meta-pattern"],
    "importance": 8
})
```

### Serena Update

```python
mcp__serena__write_memory(
    memory_file_name="documentary-[topic]-[date]",
    content="[Key findings summary]"
)
```

### Output File

Save complete report to: `/home/richard/sessions/[topic]-documentary-[date].md`

---

## Quality Targets

**User Reactions**:

- "Wait, it noticed THAT?" (genuine surprise)
- "I didn't realize I did that pattern" (self-awareness)
- "This will change how I work" (actionable insight)

**Report Characteristics**:

- Documentary feel with full evidence chain
- Patterns synthesized across 4+ data sources
- Timeline showing evolution over weeks/months
- Specific recommendations with evidence backing

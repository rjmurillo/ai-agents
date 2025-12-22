# Agent Design Skills

**Extracted**: 2025-12-16
**Source**: `.agents/governance/agent-design-principles.md`

## Skill-Design-001: Non-Overlapping Specialization (92%)

**Statement**: Each agent must have distinct purpose without duplicating another's responsibility

**Context**: Agent creation and review

**Evidence**: Agent consolidation process identified redundant agents requiring merger

**Atomicity**: 92%

**Tag**: helpful

**Impact**: 9/10

**Detection**: Role overlap in agent definitions
**Fix**: Use consolidation process from governance

---

## Skill-Design-002: Clear Entry Criteria (90%)

**Statement**: Agents need explicit conditions for when to invoke them

**Context**: Agent definition and routing

**Evidence**: Vague routing caused orchestrator ambiguity in multi-agent workflows

**Atomicity**: 90%

**Tag**: helpful

**Impact**: 8/10

**Detection**: Vague "use when" statements
**Fix**: Add concrete trigger scenarios with examples

---

## Skill-Design-003: Explicit Limitations (88%)

**Statement**: Agents must declare what they DON'T do to prevent misuse

**Context**: Agent definition and user expectations

**Evidence**: Agent interview protocol requires "What does it NOT do?" question

**Atomicity**: 88%

**Tag**: helpful

**Impact**: 8/10

**Detection**: Missing "Constraints" section
**Fix**: Document anti-patterns and explicit boundaries

---

## Skill-Design-004: Composability (88%)

**Statement**: Agents should work in sequences without tight coupling

**Context**: Multi-agent workflows and handoffs

**Evidence**: Workflow skills demonstrate pipeline success with loosely coupled agents

**Atomicity**: 88%

**Tag**: helpful

**Impact**: 8/10

**Detection**: Hard-coded agent names in outputs
**Fix**: Use handoff protocol with generic references

---

## Skill-Design-005: Verifiable Success (90%)

**Statement**: Every agent needs measurable completion criteria

**Context**: Agent definition and QA verification

**Evidence**: DoD skills show importance of explicit completion criteria

**Atomicity**: 90%

**Tag**: helpful

**Impact**: 9/10

**Detection**: No output artifacts defined
**Fix**: Add expected deliverables with format/location

---

## Skill-Design-006: Consistent Interface (85%)

**Statement**: All agents follow same input/output contract

**Context**: Agent template enforcement

**Evidence**: Template generation process enforces consistent structure

**Atomicity**: 85%

**Tag**: helpful

**Impact**: 7/10

**Detection**: Inconsistent prompt formats
**Fix**: Apply agent template strictly

---

## Skill-Design-009: Mermaid for AI-Parseable Diagrams (88%)

**Statement**: Use Mermaid for diagrams under 20 nodes; bullet lists for complex architectures

**Context**: Agent specification files, AGENTS.md, documentation requiring AI parsing

**Evidence**: Mermaid is 50% smaller than ASCII, self-healing on edits, dual-use for human/AI. Direct comparison: Mermaid flowchart 67 chars vs equivalent ASCII 140+ chars. ASCII breaks when node labels change; Mermaid regenerates clean output from syntax. AI correctly interprets Mermaid relationship semantics without visual rendering.

**Atomicity**: 88%

**Tag**: helpful

**Impact**: 7/10

**Detection**: ASCII art diagrams in agent specs, diagrams with 20+ nodes as Mermaid
**Fix**: Convert ASCII to Mermaid for <20 nodes; use structured bullet lists for complex architectures

---

## Skill-API-Design-001: Type Discriminator Fields for Merged Data Sources

**Statement**: Add discriminator field to objects when combining data from multiple API endpoints into single collection for source identification

**Context**: When merging results from multiple API endpoints that return similar but distinct object types

**Evidence**: PR #235 - Added `CommentType` field ("Review" or "Issue") to distinguish /pulls/{n}/comments from /issues/{n}/comments when combined

**Atomicity**: 97%

**Tag**: helpful (data modeling)

**Impact**: 8/10 (enables filtering and source tracking)

**Created**: 2025-12-22

**Problem**:

```powershell
# WRONG - No way to identify source after merge
$reviewComments = Invoke-API "/pulls/$PR/comments"
$issueComments = Invoke-API "/issues/$PR/comments"

$allComments = $reviewComments + $issueComments
# Caller cannot determine which comments are review vs issue type
```

**Solution**:

```powershell
# CORRECT - Add discriminator field before merge
$reviewComments = Invoke-API "/pulls/$PR/comments"
$reviewComments | ForEach-Object {
    Add-Member -InputObject $_ -NotePropertyName "CommentType" -NotePropertyValue "Review"
}

$issueComments = Invoke-API "/issues/$PR/comments"
$issueComments | ForEach-Object {
    Add-Member -InputObject $_ -NotePropertyName "CommentType" -NotePropertyValue "Issue"
}

$allComments = $reviewComments + $issueComments

# Callers can now filter by source
$allComments | Where-Object { $_.CommentType -eq "Issue" }  # Bot summaries only
$allComments | Where-Object { $_.CommentType -eq "Review" }  # Code-level comments only
```

**Why It Matters**:

Discriminator fields enable:
- **Source tracking** - Identify which endpoint each object came from
- **Filtering** - Callers can separate objects by source type
- **Debugging** - Easily verify expected counts from each source
- **Type-specific handling** - Different processing logic per source

**When to Use**:

Use discriminator fields when:
- Combining results from 2+ API endpoints
- Merging similar but distinct object types
- Output will be consumed by callers needing to distinguish sources
- Different processing logic applies to different sources

**Field Naming Pattern**:

```powershell
# Discriminator field name patterns
CommentType: "Review" | "Issue"
SourceType: "Local" | "Remote"
EventKind: "Push" | "PullRequest" | "Issue"
DataSource: "Cache" | "API" | "Database"
```

**Anti-Pattern**:

```powershell
# Using separate output parameters (fragile, caller must track both)
function Get-Comments {
    param([ref]$ReviewComments, [ref]$IssueComments)
    # Forces caller to manage two collections
}
```

**Validation**: 1 (PR #235)

---

## Related Documents

- Source: `.agents/governance/agent-design-principles.md`
- Related: skills-workflow (handoff patterns)
- Related: skills-definition-of-done (completion criteria)

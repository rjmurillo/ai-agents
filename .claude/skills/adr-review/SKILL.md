---
name: adr-review
description: Multi-agent debate orchestration for Architecture Decision Records. Automatically triggers on ADR create/edit/delete. Coordinates architect, critic, independent-thinker, security, analyst, and high-level-advisor agents in structured debate rounds until consensus.
license: MIT
metadata:
  version: 2.0.0
  model: claude-opus-4-5-20251101
  subagent_model: claude-opus-4-5-20251101
  domains: [architecture, governance, multi-agent, consensus]
  type: orchestrator
  inputs: [adr-file-path, change-type]
  outputs: [debate-log, updated-adr, recommendations]
  file_triggers:
    patterns:
      - ".agents/architecture/ADR-*.md"
      - "docs/architecture/ADR-*.md"
    events: [create, update, delete]
    auto_invoke: true
---
<!-- markdownlint-disable MD040 -->
<!-- Disabled: MD040 (nested code blocks in prompt examples) -->

# ADR Review

Multi-agent debate pattern for rigorous ADR validation. Orchestrates 6 specialized agents through structured review rounds until consensus or 10 rounds maximum.

---

## Quick Start

This skill triggers **automatically** when ADR files are created, edited, or deleted:

```text
# Automatic triggers (no manual invocation needed):
# - Create: .agents/architecture/ADR-NNN-*.md
# - Edit:   .agents/architecture/ADR-NNN-*.md
# - Delete: .agents/architecture/ADR-NNN-*.md

# Manual triggers:
/adr-review .agents/architecture/ADR-005-api-versioning.md
"review this ADR"
"validate ADR-005"
```

| Input | Output | Consensus Required |
|-------|--------|-------------------|
| ADR file path | Debate log + Updated ADR | 6/6 Accept or D&C |

---

## File Triggers

The skill monitors these file patterns:

| Pattern | Location | Events |
|---------|----------|--------|
| `ADR-*.md` | `.agents/architecture/` | create, update, delete |
| `ADR-*.md` | `docs/architecture/` | create, update, delete |

### Trigger Detection

```powershell
# Detection script checks for ADR changes
& .claude/skills/adr-review/scripts/Detect-ADRChanges.ps1

# Returns:
# - Files created/modified/deleted since last check
# - Change type (create/update/delete)
# - Recommended action (review/archive/none)
```

### Auto-Invoke Behavior

When an ADR file is detected:

| Event | Action |
|-------|--------|
| **Create** | Invoke full debate protocol (Phases 0-4) |
| **Update** | Invoke targeted review (skip Phase 0 if minor) |
| **Delete** | Invoke deletion workflow (archive check) |

---

## When to Use

**MANDATORY Triggers** (automatic, non-negotiable):

- Architect creates or updates an ADR and signals orchestrator
- ANY agent creates or updates a file matching `.agents/architecture/ADR-*.md`
- Orchestrator detects ADR creation/update signal from agent output

**User-Initiated Triggers** (manual):

- User explicitly requests ADR review ("review this ADR", "validate this decision")
- User requests multi-perspective validation for strategic decisions

**Enforcement**:

The architect agent is configured to ALWAYS signal orchestrator with MANDATORY routing when ADR files are created/updated. Orchestrator is configured to BLOCK workflow continuation until adr-review completes.

**Scope**:

- Primary location: `.agents/architecture/ADR-*.md`
- Secondary location: `docs/architecture/ADR-*.md` (if project uses this structure)

**Anti-Pattern**:

- Architect routes to planner without adr-review
- Orchestrator proceeds to next agent without invoking adr-review
- User must manually request adr-review after ADR creation

**Correct Pattern**:

- Architect signals orchestrator: "MANDATORY: invoke adr-review"
- Orchestrator invokes adr-review skill
- Workflow continues only after adr-review completes

## Agent Roles

| Agent | Focus | Tie-Breaker Role |
|-------|-------|------------------|
| **architect** | Structure, governance, coherence, ADR compliance | Structural questions |
| **critic** | Gaps, risks, alignment, completeness | None |
| **independent-thinker** | Challenge assumptions, surface contrarian views | None |
| **security** | Threat models, security trade-offs | None |
| **analyst** | Root cause, evidence, feasibility | None |
| **high-level-advisor** | Priority, resolve conflicts, break ties | Decision paralysis |

## Debate Protocol

### Phase 0: Related Work Research (NEW)

Before launching independent reviews, use analyst agent to search for related work:

```text
Task(subagent_type="analyst", prompt="""
ADR Related Work Research

## ADR Being Reviewed
Title: [ADR title]
Key topics: [Extract 3-5 keywords from ADR]

## Research Tasks

1. **Search open Issues** for related discussions:
   ```bash
   gh issue list --state open --search "[keywords]" --json number,title,labels
   ```

2. **Search open PRs** for in-progress work:

   ```bash
   gh pr list --state open --search "[keywords]" --json number,title,headRefName
   ```

3. **Search closed Issues** for prior decisions:

   ```bash
   gh issue list --state closed --search "[keywords]" --limit 10 --json number,title,labels
   ```

## Output Format

### Related Issues

| # | Title | Status | Relevance |
|---|-------|--------|-----------|
| [number] | [title] | open/closed | [How it relates to ADR] |

### Related PRs

| # | Title | Branch | Status |
|---|-------|--------|--------|
| [number] | [title] | [branch] | [open/merged/closed] |

### Implications for ADR Review

- [What existing work affects this ADR?]
- [Are there gaps already known?]
- [Should any issues be linked?]
- [Are any PRs already implementing this?]
""")

```

Include related work findings in each Phase 1 agent prompt as context.

### Phase 1: Independent Review

Invoke each agent with the ADR content AND related work findings. Each provides:

```markdown
## [Agent] Review

### Strengths
- [What aspects are sound]

### Weaknesses/Gaps
- [What is missing, unclear, or problematic]

### Scope Concerns
- [Should this be split into multiple ADRs?]

### Questions
- [What needs clarification]

### Blocking Concerns
| Issue | Priority | Description |
|-------|----------|-------------|
| [Issue] | P0/P1/P2 | [Details] |

P0 = blocking, P1 = important, P2 = nice-to-have
```

**Agent Invocation Pattern:**

```python
Task(subagent_type="architect", prompt="""
ADR Review Request (Phase 1: Independent Review)

## ADR Content
[Full ADR text]

## Instructions
1. Review for structural compliance with MADR 4.0
2. Check alignment with existing ADRs in .agents/architecture/ and docs/architecture/
3. Identify scope concerns (should this be split?)
4. Classify all issues as P0/P1/P2
5. Return structured review per Phase 1 format
""")
```

Repeat for: critic, independent-thinker, security, analyst, high-level-advisor.

### Phase 2: Consolidation

After all 6 reviews complete:

1. List consensus points (agents agree)
2. List conflicts (agents disagree)
3. Route conflicts to high-level-advisor for resolution
4. Categorize all issues by priority after rulings
5. Draft consolidated change recommendations

**Conflict Resolution Pattern:**

```python
Task(subagent_type="high-level-advisor", prompt="""
ADR Conflict Resolution Required

## Conflict 1: [Description]
- **architect position**: [Position]
- **security position**: [Position]
- Evidence: [Facts]

## Conflict 2: [Description]
...

## Decision Required
For each conflict, provide:
1. Which position prevails
2. Rationale
3. Whether ADR should be split
4. Final P0/P1/P2 classification
""")
```

### Phase 3: Resolution

1. Propose specific updates addressing P0 and P1 issues
2. Document dissenting views for "Alternatives Considered" section
3. Record rationale for incorporated vs rejected feedback
4. Generate complete updated ADR text

**Scope Split Detection:**

If 2+ agents flag scope concerns, recommend splitting:

```markdown
## Scope Split Recommendation

**Original ADR**: [Title]

**Proposed Split**:
1. ADR-NNN-A: [Focused decision 1]
2. ADR-NNN-B: [Focused decision 2]

**Rationale**: [Why splitting improves clarity and enforceability]
```

### Phase 4: Convergence Check

Re-invoke each agent to review proposed updates:

```python
Task(subagent_type="[agent]", prompt="""
ADR Convergence Check (Round [N])

## Updated ADR
[Full updated ADR text]

## Changes Made
[Summary of changes from Phase 3]

## Your Previous Concerns
[Agent's Phase 1 concerns]

## Instructions
Provide ONE position:
- **Accept**: No blocking concerns remain
- **Disagree-and-Commit**: Reservations exist but agree to proceed (document dissent)
- **Block**: Unresolved P0 concerns (specify what remains)
""")
```

**Consensus Criteria:**

- All 6 agents Accept OR Disagree-and-Commit = Consensus reached
- Any agent Blocks = Another round required (if round < 10)
- Round 10 with no consensus = Conclude with unresolved issues documented

## Round Management

```markdown
## Debate State

**Round**: [N] of 10
**Status**: [In Progress | Consensus | Concluded Without Consensus]

### Agent Positions
| Agent | Position | Notes |
|-------|----------|-------|
| architect | Accept/D&C/Block | [Brief note] |
| critic | Accept/D&C/Block | [Brief note] |
| independent-thinker | Accept/D&C/Block | [Brief note] |
| security | Accept/D&C/Block | [Brief note] |
| analyst | Accept/D&C/Block | [Brief note] |
| high-level-advisor | Accept/D&C/Block | [Brief note] |

### Unresolved Issues (if any)
[List P0 issues still blocking]
```

## Deletion Workflow

When an ADR file is deleted, this skill triggers a special workflow:

### Phase D1: Deletion Detection

```powershell
# Script detects deleted ADR files
& .claude/skills/adr-review/scripts/Detect-ADRChanges.ps1

# Output includes:
# - Deleted file path
# - Last known status (proposed/accepted/deprecated/superseded)
# - Dependent ADRs that reference this ADR
```

### Phase D2: Impact Assessment

Invoke analyst to assess deletion impact:

```python
Task(subagent_type="analyst", prompt="""
ADR Deletion Impact Assessment

## Deleted ADR
Path: {deleted_adr_path}
Title: {adr_title}
Status: {last_known_status}

## Research Tasks
1. Find all references to this ADR in codebase
2. Check for dependent ADRs that cite this ADR
3. Identify any implementation code that references this decision
4. Check session logs for recent related work

## Output Format

### References Found
| Location | Type | Impact |
|----------|------|--------|
| [path] | [code/adr/doc] | [high/medium/low] |

### Recommendation
- **Archive**: Keep copy in `.agents/architecture/archive/`
- **Delete**: No dependencies, safe to remove
- **Block**: Active dependencies require resolution first
""")
```

### Phase D3: Archival Decision

Based on impact assessment:

| Status | Dependencies | Action |
|--------|--------------|--------|
| proposed | None | Delete (no archival needed) |
| proposed | Exists | Block deletion, resolve deps |
| accepted | None | Archive then delete |
| accepted | Exists | Block deletion, update deps first |
| deprecated | Any | Archive then delete |
| superseded | Any | Verify successor ADR, then delete |

### Archival Format

If archiving is required:

```markdown
# Archived: ADR-NNN-title

**Archived**: YYYY-MM-DD
**Reason**: [User deleted | Superseded by ADR-XXX | Deprecated]
**Original Status**: [accepted | proposed | deprecated]

---

[Original ADR content preserved below]
```

Save to: `.agents/architecture/archive/ADR-NNN-title.md`

### Phase D4: Cleanup

1. Update dependent ADRs to remove/update references
2. Update any CLAUDE.md files that referenced the ADR
3. Log deletion in session log
4. Return summary to orchestrator

```markdown
## ADR Deletion Complete

**ADR**: [Path]
**Action**: [Archived | Deleted | Blocked]

### Changes Made
- [List of files updated]

### Archive Location (if archived)
- [Path to archived file]

### Blocked (if applicable)
- **Reason**: [Why deletion was blocked]
- **Required Actions**: [What must happen first]
```

## Artifact Storage

Save debate artifacts to `.agents/critique/`:

### Debate Log

Save to: `.agents/critique/ADR-NNN-debate-log.md`

```markdown
# ADR Debate Log: [ADR Title]

## Summary
- **Rounds**: [N]
- **Outcome**: [Consensus | Concluded Without Consensus]
- **Final Status**: [proposed | accepted | needs-revision]

## Round [N] Summary

### Key Issues Addressed
- [Issue 1]
- [Issue 2]

### Major Changes Made
- [Change 1]
- [Change 2]

### Agent Positions
| Agent | Position |
|-------|----------|
| ... | ... |

### Next Steps
[If applicable]
```

### Updated ADR

Save to: `.agents/architecture/ADR-NNN-[title].md` (or update in place)

### Recommendations

Return to orchestrator with structured recommendations:

```markdown
## ADR Review Complete

**ADR**: [Path]
**Consensus**: [Yes/No]
**Rounds**: [N]

### Outcome
- **Status**: [accepted | needs-revision | split-recommended]
- **Updated ADR**: [Path to updated file]
- **Debate Log**: [Path to debate log]

### Scope Split (if applicable)
[Details of recommended splits]

### Planning Recommendations
[If ADR accepted and implementation planning needed]

**Recommend orchestrator routes to**:
- planner: Create implementation work packages
- task-generator: Break into atomic tasks
- None: ADR is informational only
```

## Integration Points

### Prior ADR Locations

Check these locations for existing ADRs and patterns:

- `.agents/architecture/ADR-*.md`
- `docs/architecture/ADR-*.md`

### ADR Template Reference

Use MADR 4.0 format per architect.md. Key sections:

- Context and Problem Statement
- Decision Drivers
- Considered Options
- Decision Outcome (with Consequences and Confirmation)
- Pros and Cons of Options

### Reversibility Assessment

Every ADR must include reversibility assessment per architect.md:

- Rollback capability
- Vendor lock-in assessment
- Exit strategy
- Legacy impact
- Data migration reversibility

## Example Invocation

**User triggers:**

```text
Review this ADR: .agents/architecture/ADR-005-api-versioning.md
```

**Orchestrator triggers:**

```python
# When architect creates/updates ADR
Task(subagent_type="orchestrator", prompt="""
Trigger adr-review skill for: .agents/architecture/ADR-005-api-versioning.md

Follow debate protocol in .claude/skills/adr-review/SKILL.md
""")
```

## Efficiency Notes

- **Phase 0 is critical**: Related work research prevents duplicate effort and identifies existing gaps
- Most reviews converge in 1-2 rounds when high-level-advisor resolves conflicts early
- Skip Phase 1 re-invocation for agents with no relevant expertise (e.g., security for pure process ADRs)
- Cache agent positions between rounds to avoid re-reading unchanged concerns
- If Phase 0 finds an open PR already implementing the ADR, consider deferring review until PR is merged

## Related Work Integration

When Phase 0 finds related items:

| Finding | Action |
|---------|--------|
| Open issue discussing same topic | Link in ADR, acknowledge in review |
| Closed issue with prior decision | Verify ADR aligns or documents deviation |
| Open PR implementing feature | Wait for PR or coordinate with author |
| Known gap in backlog | Verify ADR addresses the gap |
| Duplicate proposal | Consider closing in favor of existing |

---

## Scripts

This skill includes automation scripts for agentic operation:

### Detect-ADRChanges.ps1

Detects ADR file changes for automatic skill triggering.

**Location**: `.claude/skills/adr-review/scripts/Detect-ADRChanges.ps1`

**Usage**:

```powershell
# Basic detection (compares to HEAD~1)
& .claude/skills/adr-review/scripts/Detect-ADRChanges.ps1

# Compare to specific commit
& .claude/skills/adr-review/scripts/Detect-ADRChanges.ps1 -SinceCommit "abc123"

# Include untracked new ADR files
& .claude/skills/adr-review/scripts/Detect-ADRChanges.ps1 -IncludeUntracked
```

**Output** (JSON):

```json
{
  "Created": ["path/to/new-adr.md"],
  "Modified": ["path/to/changed-adr.md"],
  "Deleted": ["path/to/removed-adr.md"],
  "DeletedDetails": [{
    "Path": "path/to/removed-adr.md",
    "ADRName": "ADR-005-removed",
    "Status": "deleted",
    "Dependents": ["path/to/dependent-adr.md"]
  }],
  "HasChanges": true,
  "RecommendedAction": "review",
  "Timestamp": "2025-01-01T12:00:00Z",
  "SinceCommit": "HEAD~1"
}
```

**Exit Codes**:

| Code | Meaning |
|------|---------|
| 0 | Success (changes may or may not exist) |
| 1 | Error during detection |

### Orchestrator Integration

The orchestrator should run detection at session start:

```python
# At session start, check for ADR changes
result = Bash("pwsh -NoProfile -Command '& .claude/skills/adr-review/scripts/Detect-ADRChanges.ps1'")

if result.HasChanges:
    if result.RecommendedAction == "review":
        # Invoke adr-review skill for each Created/Modified file
        for adr in result.Created + result.Modified:
            Skill(skill="adr-review", args=adr)
    elif result.RecommendedAction == "archive":
        # Invoke deletion workflow for each Deleted file
        for adr in result.Deleted:
            Skill(skill="adr-review", args=f"--delete {adr}")
```

---

## Verification Checklist

After skill invocation:

- [ ] Debate log exists at `.agents/critique/ADR-NNN-debate-log.md`
- [ ] ADR status updated (proposed/accepted/needs-revision)
- [ ] All P0 issues addressed or documented
- [ ] Dissent captured for Disagree-and-Commit positions
- [ ] Recommendations provided to orchestrator
- [ ] Deletion archival complete (if delete event)

---

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Single-agent ADR review | Misses domain expertise | Use full 6-agent debate |
| Skipping Phase 0 | Duplicates existing work | Always research first |
| Ignoring D&C dissent | Loses important context | Document all reservations |
| Manual ADR monitoring | Error-prone, inconsistent | Use Detect-ADRChanges.ps1 |
| Deleting accepted ADRs without archive | Loses institutional knowledge | Always archive accepted ADRs |

---

## Changelog

### v2.0.0 (Current)

- Added file_triggers metadata for automatic invocation
- Added deletion workflow (Phases D1-D4)
- Added Detect-ADRChanges.ps1 script
- Added Quick Start section
- Added Scripts section with automation docs
- Updated frontmatter to SkillCreator v3.2 format
- Added verification checklist

### v1.0.0

- Initial multi-agent debate protocol
- Phases 0-4 workflow
- Agent prompt templates

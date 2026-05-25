# Issue Resolution Protocol

When debate topics are resolved, issues MUST be handled by priority.

## P0/P1: Must Resolve Before Acceptance

P0 (blocking) and P1 (important) issues MUST be resolved before the ADR can be accepted:

| Priority | Resolution Requirement | Acceptance Gate |
|----------|------------------------|-----------------|
| **P0** | Issue fully addressed in ADR revision | BLOCKING - cannot proceed |
| **P1** | Issue addressed OR deferred with justification + backlog issue | BLOCKING - requires justification AND tracking |
| **P2** | Documented for future work | Non-blocking |

**Critical**: Deferred P1 items MUST be backlogged as GitHub issues. Deferral without tracking = lost work.

## P1 Deferral Requirements

When a P1 issue is deferred (not fully resolved), it MUST:

1. **Have documented justification** in the ADR or debate log explaining why deferral is acceptable
2. **Be filed as a GitHub issue** with `priority:P1`, `backlog`, and `adr-followup` labels
3. **Be linked to related issues/ADRs** that will trigger its surfacing
4. **Have keywords in title** that match memory-index routing patterns

### Surfacing Mechanism (How Amnesiac Agents Find Deferred Items)

Deferred P1 items surface through THREE mechanisms:

| Mechanism | How It Works | When It Triggers |
|-----------|--------------|------------------|
| **GitHub Issue Linking** | Link deferred issue to parent ADR, related epics, or blocking issues | When agent works on linked item, `gh issue view` shows linked issues |
| **Phase 0 Search** | ADR review Phase 0 searches `label:adr-followup` for related work | Every ADR review includes this search |
| **Memory-Index Keywords** | Issue title contains keywords that match memory-index patterns | Session Start context retrieval surfaces related issues |

**Critical**: The trigger is NOT a calendar reminder. It's **keyword-based surfacing** during normal agent workflows.

### Practical Example

Deferred item: "ADR-007 needs reversibility assessment"

**Surfacing setup**:

```bash
# 1. Link to parent ADR issue (if one exists)
gh issue edit [deferred-issue] --add-label "adr-followup" --repo rjmurillo/ai-agents

# 2. Create Serena memory for cross-session context
mcp__serena__write_memory(
  memory_file_name="adr-007-deferred-p1",
  content="P1 DEFERRED: ADR-007 needs reversibility assessment. Trigger: When any ADR-007 revision occurs or when reversibility patterns are discussed. Issue #[number]."
)

# 3. Add to memory-index routing (keywords -> memory)
# In memory-index, add row:
# | adr-007 reversibility rollback | adr-007-deferred-p1 |
```

**How it surfaces**:

1. Agent starts session working on "ADR-007 revision"
2. Session Start reads `memory-index`
3. Keywords "adr-007" match -> reads `adr-007-deferred-p1` memory
4. Memory contains: "P1 DEFERRED: needs reversibility assessment. Issue #[number]"
5. Agent is now aware and can address or acknowledge

### P1 Deferral Issue Template

```bash
gh issue create \
  --title "[ADR-NNN] [P1 DEFERRED] [keyword-rich description]" \
  --body "$(cat <<'EOF'
## Context

This P1 issue was identified during ADR review and deferred with justification.

**ADR**: `[path to ADR]`
**Debate Log**: `[path to debate log]`
**Raised By**: [Agent name]

## Issue Description

[Full description from debate log]

## Deferral Justification

[Why this was acceptable to defer]

## Surfacing Mechanism

**Keywords for memory-index**: [list keywords that should trigger this]
**Linked Issues**: #[parent-issue], #[related-epic]
**Memory Created**: `[memory-name]` in Serena

**Trigger scenarios**:
- [ ] When working on [specific ADR/feature]
- [ ] When [keyword] appears in session objective
- [ ] When Phase 0 search finds this issue

## Acceptance Criteria

- [ ] [Specific criteria for resolution]

---

*P1 deferred during ADR review - surfaces via memory-index keywords*
EOF
)" \
  --label "priority:P1,backlog,adr-followup" \
  --repo rjmurillo/ai-agents
```

**Post-creation steps** (REQUIRED):

1. Create Serena memory with issue reference and trigger keywords
2. Update `memory-index` with routing entry for trigger keywords
3. Link issue to parent ADR issue or related epics

## P2: Plan and Backlog

P2 (nice-to-have) issues that are not addressed during the review MUST be:

1. **Documented** in the debate log under "Residual P2 Issues"
2. **Filed as GitHub issues** in the project backlog
3. **Linked** to the ADR for traceability

**GitHub Issue Creation** (for each unresolved P2):

```bash
gh issue create \
  --title "[ADR-NNN] [Brief description of P2 issue]" \
  --body "$(cat <<'EOF'
## Context

This issue was identified during ADR review but classified as P2 (nice-to-have).

**ADR**: `[path to ADR]`
**Debate Log**: `[path to debate log]`
**Raised By**: [Agent name]

## Issue Description

[Full description from debate log]

## Recommended Action

[What should be done to address this]

## Acceptance Criteria

- [ ] [Specific criteria for resolution]

---

*Created automatically by adr-review skill*
EOF
)" \
  --label "backlog,adr-followup" \
  --repo rjmurillo/ai-agents
```

## Debate Log Update

After issue creation, update the debate log:

```markdown
### Residual P2 Issues (Backlogged)

| Issue | Agent | GitHub Issue | Description |
|-------|-------|--------------|-------------|
| [Issue title] | [agent] | #[number] | [Brief description] |
```

## Resolution Summary Template

Add to final recommendations:

```markdown
### Issue Resolution Summary

| Priority | Count | Resolved | Deferred | Backlogged |
|----------|-------|----------|----------|------------|
| P0 | [N] | [N] | 0 (not allowed) | N/A |
| P1 | [N] | [M] | [K] | [K] issues created |
| P2 | [N] | [M] | N/A | [K] issues created |

**Backlogged Issues** (P1 deferred + P2):
- #[number]: [P1 DEFERRED] [title]
- #[number]: [title]
```

**Validation**: The sum of (Resolved + Deferred) for each priority MUST equal Count. All deferred P1 items MUST have corresponding GitHub issues.

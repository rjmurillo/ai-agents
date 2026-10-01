# Issue Resolution Protocol

When debate topics are resolved, findings MUST be handled by priority. This
skill never files GitHub issues. An agent that finds a deferred item does not
select it as work: the owner decides what becomes a tracked issue. Deferred
items stay in the debate log and reach the owner in the final recommendation.

## P0/P1: Must Resolve Before Acceptance

P0 (blocking) and P1 (important) findings MUST be resolved before the ADR can be accepted:

| Priority | Resolution Requirement | Acceptance Gate |
|----------|------------------------|-----------------|
| **P0** | Finding fully addressed in ADR revision | BLOCKING - cannot proceed |
| **P1** | Finding addressed OR deferred with justification recorded in the debate log | BLOCKING - requires justification AND a recorded deferral |
| **P2** | Documented for future work | Non-blocking |

**Critical**: A deferred P1 finding MUST appear in the debate log and in the final
recommendation to the owner. Deferral that is not recorded there = lost work.

## P1 Deferral Requirements

When a P1 finding is deferred (not fully resolved), it MUST:

1. **Have documented justification** in the ADR or debate log explaining why deferral is acceptable
2. **Be listed in the debate log** under "Deferred Findings" (template below)
3. **Be flagged to the owner** in the final recommendation, with the trigger that should reopen it
4. **Have keywords in its description** that match memory-index routing patterns

Do not run `gh issue create`, `new_issue.py`, or the GitHub MCP `issue_write` tool
to record a deferral. If the owner asks in the current request to track a
deferred finding as an issue, file it then, through the github skill's
`new_issue.py` with `--source human`.

### Surfacing Mechanism (How Amnesiac Agents Find Deferred Items)

Deferred P1 findings surface through TWO mechanisms:

| Mechanism | How It Works | When It Triggers |
|-----------|--------------|------------------|
| **Debate Log** | The deferral sits beside the ADR it came from, in the "Deferred Findings" table | Every ADR review reads the prior debate log for the same ADR |
| **Memory-Index Keywords** | A Serena memory carries keywords that match memory-index patterns | Session Start context retrieval surfaces the deferral |

Phase 0 still searches existing issues, including `label:adr-followup`, for related
work the owner already filed.

**Critical**: The trigger is NOT a calendar reminder. It's **keyword-based surfacing** during normal agent workflows.

### Practical Example

Deferred item: "ADR-007 needs reversibility assessment"

**Surfacing setup**:

> Serena writes to the checkout active at server start, not your current
> directory. In a linked git worktree, or when you cannot tell, do not call
> Serena memory mutation tools. Make the same change to this checkout's
> `.serena/memories/` files, or return it to the parent session
> (`universal.md` MUST NOT 11, issue #5061).

```bash
# 1. Create Serena memory for cross-session context
mcp__serena__write_memory(
  memory_file_name="adr-007-deferred-p1",
  content="P1 DEFERRED: ADR-007 needs reversibility assessment. Trigger: When any ADR-007 revision occurs or when reversibility patterns are discussed. Recorded in the ADR-007 debate log."
)

# 2. Add to memory-index routing (keywords -> memory)
# In memory-index, add row:
# | adr-007 reversibility rollback | adr-007-deferred-p1 |
```

**How it surfaces**:

1. Agent starts session working on "ADR-007 revision"
2. Session Start reads `memory-index`
3. Keywords "adr-007" match -> reads `adr-007-deferred-p1` memory
4. Memory contains: "P1 DEFERRED: needs reversibility assessment. Recorded in the ADR-007 debate log"
5. Agent is now aware and can address or acknowledge

## P2: Document and Flag

P2 (nice-to-have) findings that are not addressed during the review MUST be:

1. **Documented** in the debate log under "Residual P2 Findings"
2. **Linked** to the ADR for traceability
3. **Left unfiled**: the owner decides which P2 findings become issues

## Debate Log Update

After resolution, update the debate log:

```markdown
### Deferred Findings

| Priority | Finding | Agent | Justification | Trigger to reopen |
|----------|---------|-------|---------------|-------------------|
| P1 | [Finding title] | [agent] | [Why deferral is acceptable] | [Keyword or event] |

### Residual P2 Findings

| Finding | Agent | Description |
|---------|-------|-------------|
| [Finding title] | [agent] | [Brief description] |
```

## Resolution Summary Template

Add to final recommendations:

```markdown
### Finding Resolution Summary

| Priority | Count | Resolved | Deferred | Flagged to owner |
|----------|-------|----------|----------|------------------|
| P0 | [N] | [N] | 0 (not allowed) | N/A |
| P1 | [N] | [M] | [K] | [K] |
| P2 | [N] | [M] | N/A | [K] |

**Flagged to owner** (P1 deferred + P2, not filed as issues):
- [P1 DEFERRED] [title]
- [title]
```

**Validation**: The sum of (Resolved + Deferred) for each priority MUST equal Count. All deferred P1 findings MUST appear in the debate log and in the owner flag list.

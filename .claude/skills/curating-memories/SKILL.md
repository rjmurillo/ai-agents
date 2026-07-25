---
name: curating-memories
description: Guidance for maintaining memory quality through curation. Covers updating outdated memories, marking obsolete content, and linking related knowledge. Use when memories need modification, when new information supersedes old, or when building knowledge graph connections.
license: MIT
version: 1.1.0
---

# Curating Memories

Active curation keeps the knowledge base accurate and connected. Outdated memories pollute search results and reduce effectiveness.

## Triggers

| Trigger Phrase | Operation |
|----------------|-----------|
| `how do I update a memory` | update_memory with PATCH semantics |
| `how do I mark a memory obsolete` | mark_memory_obsolete with reason |
| `how do I link related memories` | link_memories bidirectional linking |
| `how do I deduplicate memories` | Curation workflow: query, analyze, merge |
| `how do I clean up stale memories` | Identify and mark obsolete outdated content |

---

## When to Update a Memory

Use `update_memory` when:

- Information needs correction or clarification
- Importance level changes (more/less relevant than thought)
- Content needs refinement
- Links to projects/artifacts/documents change

```javascript
execute_forgetful_tool("update_memory", {
  "memory_id": <id>,
  "content": "Updated content...",
  "importance": 8
})
```

Only specified fields are changed (PATCH semantics).

## When to Mark Obsolete

Use `mark_memory_obsolete` when:

- Memory is outdated or contradicted by newer information
- Decision has been reversed or superseded
- Referenced code/feature no longer exists
- Memory was created in error

```javascript
execute_forgetful_tool("mark_memory_obsolete", {
  "memory_id": <id>,
  "reason": "Superseded by new architecture decision",
  "superseded_by": <new_memory_id>  // optional
})
```

Obsolete memories are soft-deleted (preserved for audit, hidden from queries).

## When to Link Memories

Use `link_memories` when:

- Concepts are related but not caught by auto-linking
- Building explicit knowledge graph structure
- Connecting decisions to their implementations
- Relating patterns across projects

```javascript
execute_forgetful_tool("link_memories", {
  "memory_id": <source_id>,
  "related_ids": [<target_id_1>, <target_id_2>]
})
```

Links are bidirectional (A↔B created automatically).

## Curation Workflow

When creating new memories, check impact on existing knowledge:

### Step 1: Query Related Memories

```javascript
execute_forgetful_tool("query_memory", {
  "query": "<topic of new memory>",
  "query_context": "Checking for memories that may need curation",
  "k": 5
})
```

### Step 2: Analyze Each Result

For each existing memory, determine action:

| Situation | Action |
|-----------|--------|
| Existing memory is still accurate | Link to it |
| Existing memory has minor gaps | Update it |
| Existing memory is now wrong | Mark obsolete, create new |
| Existing memory is partially valid | Create new, link both |

### Step 3: Execute Curation Plan

Present plan to user before executing:

```text
Curation plan:
- Create: "New authentication approach" (importance: 8)
- Mark obsolete: #42 "Old auth pattern" (superseded)
- Link: New memory ↔ #38 "Security requirements"

Proceed? (y/n)
```

### Step 4: Execute and Report

After user confirms:

1. Create new memory
2. Mark obsolete memories
3. Create links
4. Report results with all changes made

## Signs of Poor Curation

Watch for these indicators:

- Multiple similar memories on same topic (deduplicate)
- Memories referencing deleted code (mark obsolete)
- Contradictory memories (resolve conflict)
- Low-importance memories (importance < 6) accumulating
- Orphaned memories with no links (consider linking or removing)

## Auto-Linking

Forgetful auto-links semantically similar memories (similarity >= 0.7) during creation. Manual linking is for:

- Explicit relationships auto-linking missed
- Cross-project connections
- Non-obvious conceptual links

Check `similar_memories` in create response to see what was auto-linked.

---

## When to Use

Use this skill when:

- Existing memories need correction or updated content
- New information supersedes an older memory
- Building explicit links between related knowledge
- Duplicate memories need consolidation
- Referenced code or features no longer exist

Use [using-forgetful-memory](../using-forgetful-memory/SKILL.md) instead when:

- Creating new memories from scratch
- Learning Forgetful tool parameters and constraints

Use [exploring-knowledge-graph](../exploring-knowledge-graph/SKILL.md) instead when:

- Traversing entity relationships for comprehensive context
- Investigating cross-project connections

---

## Process

1. Search for the target memory using `query_memory`
2. Evaluate whether the memory needs updating, linking, or marking obsolete
3. Apply the appropriate curation operation
4. Verify the change took effect

---

## Scripts: Supersession Sweep

The append-never-delete pattern is the failure this sweep targets: a memory
that is fully resolved or historical but still reads as live guidance, so a
fresh agent has to read past archaeology to reach current truth. Run the
sweep to surface those files. It **proposes** a disposition per file and
edits nothing; ratification is a separate, confirmed step.

```bash
uv run python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/curating-memories/scripts/supersession_sweep.py"
```

Add `--json` for machine-readable output, or `--root <dir>` to scan a
directory other than `.serena/memories`.

### The four buckets

| Bucket | Signal | Action |
|--------|--------|--------|
| `live` | No supersession markers | Leave alone |
| `healthy-supersession` | Struck-through obsolete content plus a dated banner, current truth visible | Leave alone; this is the target shape |
| `resolved-or-historical-but-present` | `Status: RESOLVED`/`BLOCKING` co-present with references to removed artifacts or per-section `(Historical)` tags | Propose archive, or collapse to a one-line changelog footer |
| `temporal-snapshot-as-live` | A dated point-in-time doc framed as current state | Propose a dated-snapshot banner |

### The constraint (non-negotiable)

The sweep is a generator self-report, which is the closed-loop-validator
trap. The classification is a **routing signal into verification, never a
verdict**:

- The sweep proposes a disposition. It does not edit or delete.
- Ratify with the [doc-accuracy](../doc-accuracy/SKILL.md) code-as-source-of-truth
  discipline: archive a memory only after confirming the artifacts it
  references are actually gone and no live path depends on it.
- A human or a second independent check confirms before any content is
  removed. A mis-flag on a load-bearing entry is the exact loss this
  proposal-only design prevents.

### The healthy-supersession target shape

When you collapse a `resolved-or-historical-but-present` file, do not bury
it. Strike through the obsolete content, add a dated banner explaining why,
and keep current truth visible inline. `cost/cost-summary-reference.md` is
the exemplar: obsolete rows struck through, a dated `IMPORTANT` banner,
history preserved, nothing hidden. Strikethrough density alone is a
healthy-supersession signal, never a rot signal; the sweep will not propose
archiving a file on strikethrough count.

---

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Deleting memories instead of marking obsolete | Loses audit trail | Use mark_memory_obsolete with reason |
| Creating duplicates of existing memories | Pollutes search results | Query first, update existing if found |
| Linking everything to everything | Dilutes relationship signal | Link only semantically meaningful connections |
| Skipping user confirmation on curation plans | May obsolete valuable content | Present plan and wait for approval |
| Ignoring low-importance memory accumulation | Degrades search quality over time | Periodically review and cull sub-6 importance |

---

## Verification

After curation operations:

- [ ] Reconciliation: paste the `update_memory` tool response showing the memory ID and updated fields (not a claim)
- [ ] Obsolete memories have a non-empty `reason` field in the `mark_memory_obsolete` response (paste the response)
- [ ] Reconciliation: paste the `link_memories` response confirming both directions created (A-to-B and B-to-A)
- [ ] Reconciliation: `query_memory` on the consolidated topic returns exactly 1 active result (paste the result count)
- [ ] Curation changes were confirmed by user before execution

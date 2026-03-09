---
name: curating-memories
version: 1.0.1
model: claude-sonnet-4-5
description: Guidance for maintaining memory quality through curation. Covers updating outdated memories, marking obsolete content, and linking related knowledge. Use when memories need modification, when new information supersedes old, or when building knowledge graph connections.
license: MIT
---

# Curating Memories

Active curation keeps the knowledge base accurate and connected. Outdated memories pollute search results and reduce effectiveness.

## Triggers

| Trigger | Operation |
|---------|-----------|
| `update a memory` | update_memory with PATCH semantics |
| `mark a memory obsolete` | mark_memory_obsolete with reason |
| `link related memories` | link_memories bidirectional linking |
| `deduplicate memories` | Curation workflow: query, analyze, merge |
| `clean up stale memories` | Identify and mark obsolete outdated content |

---

## Quick Start

```text
1. Search:  query_memory for the topic
2. Evaluate: Does the memory need updating, linking, or retiring?
3. Act:     Apply the appropriate curation operation
4. Verify:  Confirm the change took effect
```

---

## Quick Reference

| Situation | Action | Tool |
|-----------|--------|------|
| Information needs correction | Update in place | `update_memory` |
| Memory is outdated or wrong | Mark obsolete | `mark_memory_obsolete` |
| Related concepts not linked | Create link | `link_memories` |
| Duplicate memories found | Merge into one | Curation workflow |
| Referenced code deleted | Mark obsolete | `mark_memory_obsolete` |

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

### Step 1: Search for the Target Memory

```javascript
execute_forgetful_tool("query_memory", {
  "query": "<topic>",
  "query_context": "Checking for memories that may need curation",
  "k": 5
})
```

### Step 2: Evaluate Each Result

| Situation | Action |
|-----------|--------|
| Existing memory is still accurate | Link to it |
| Existing memory has minor gaps | Update it |
| Existing memory is now wrong | Mark obsolete, create new |
| Existing memory is partially valid | Create new, link both |

### Step 3: Present Curation Plan

Present plan to user before executing:

```text
Curation plan:
- Create: "New authentication approach" (importance: 8)
- Mark obsolete: #42 "Old auth pattern" (superseded)
- Link: New memory <-> #38 "Security requirements"

Proceed? (y/n)
```

### Step 4: Execute and Report

After user confirms:

1. Create new memory
2. Mark obsolete memories
3. Create links
4. Report results with all changes made

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

- [ ] Updated memories reflect accurate current state
- [ ] Obsolete memories have clear reason documented
- [ ] New links are bidirectional and meaningful
- [ ] No duplicate memories remain on the same topic
- [ ] Curation changes were confirmed by user before execution

---

<details>
<summary><strong>Deep Dive: Curation Operations</strong></summary>

### Updating a Memory

Use `update_memory` when:

- Information needs correction or clarification
- Importance level changes (more or less relevant than thought)
- Content needs refinement
- Links to projects, artifacts, or documents change

```javascript
execute_forgetful_tool("update_memory", {
  "memory_id": <id>,
  "content": "Updated content...",
  "importance": 8
})
```

Only specified fields are changed (PATCH semantics).

### Marking a Memory Obsolete

Use `mark_memory_obsolete` when:

- Memory is outdated or contradicted by newer information
- Decision has been reversed or superseded
- Referenced code or feature no longer exists
- Memory was created in error

```javascript
execute_forgetful_tool("mark_memory_obsolete", {
  "memory_id": <id>,
  "reason": "Superseded by new architecture decision",
  "superseded_by": <new_memory_id>  // optional
})
```

Obsolete memories are soft-deleted (preserved for audit, hidden from queries).

### Linking Memories

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

Links are bidirectional (A<->B created automatically).

### Auto-Linking

Forgetful auto-links semantically similar memories (similarity >= 0.7) during creation. Manual linking is for:

- Explicit relationships auto-linking missed
- Cross-project connections
- Non-obvious conceptual links

Check `similar_memories` in create response to see what was auto-linked.

</details>

<details>
<summary><strong>Deep Dive: Signs of Poor Curation</strong></summary>

Watch for these indicators:

- Multiple similar memories on same topic (deduplicate)
- Memories referencing deleted code (mark obsolete)
- Contradictory memories (resolve conflict)
- Low-importance memories (importance < 6) accumulating
- Orphaned memories with no links (consider linking or removing)

</details>

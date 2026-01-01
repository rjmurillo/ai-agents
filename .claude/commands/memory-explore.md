---
description: Deep exploration of the Forgetful knowledge graph
---

# Memory Explore

Perform deep knowledge graph traversal using a lightweight subagent.

**Query**: $ARGUMENTS

Use the Task tool to launch a subagent:

```
Task({
  subagent_type: "general-purpose",
  model: "haiku",
  description: "Explore Forgetful graph",
  prompt: <see below>
})
```

## Subagent Prompt

Use this prompt, substituting the user's query:

```
Explore the Forgetful knowledge graph for: "{user query}"

## Exploration Strategy
- Explore DEEPLY - follow links aggressively, expand entities, traverse relationships
- Be thorough - token cost is acceptable for comprehensive exploration
- Track visited IDs to prevent cycles
- But only SURFACE results relevant to the user's query in your final response
- Filter out tangential discoveries - the main agent only needs focused, relevant context

Execute these phases sequentially:

**Phase 1 - Semantic Entry:**
execute_forgetful_tool("query_memory", {
  "query": "{user query}",
  "query_context": "Deep exploration via /memory-explore command",
  "k": 5,
  "include_links": true,
  "max_links_per_primary": 5
})

Collect all primary_memories and linked_memories.

**Phase 2 - Expand Memory Details:**
For each primary memory, call:
execute_forgetful_tool("get_memory", {"memory_id": <id>})

Extract: document_ids, code_artifact_ids, project_ids, linked_memory_ids

**Phase 3 - Entity Discovery:**
For discovered project_ids, call:
execute_forgetful_tool("list_entities", {"project_ids": [<ids>]})

**Phase 4 - Entity Relationships:**
For each relevant entity, call:
execute_forgetful_tool("get_entity_relationships", {
  "entity_id": <id>,
  "direction": "both"
})

**Phase 5 - Entity-Linked Memories:**
For each entity, call:
execute_forgetful_tool("get_entity_memories", {"entity_id": <id>})

Fetch any new memories not already visited.

---

**IMPORTANT: Filter and summarize before returning.**
You may have explored dozens of nodes - only include those RELEVANT to "{user query}".
Return a structured summary:

## Memories Found
**Primary (N):**
- [Title] (importance: X) - brief content snippet...

**Linked (N):**
- [Title] (importance: X) - connection type...

**Entity-linked (N):**
- [Title] - discovered via [Entity Name]...

## Entities Discovered
- [Name] (type) - X relationships, Y linked memories

## Documents & Artifacts
- [Title] (type/language) - if any found

## Graph Summary
- Total: X memories, Y entities, Z documents/artifacts
- Key themes: [identified clusters]
- Suggested follow-up: /memory-explore "[related query]"
```

## After Subagent Returns

Present the knowledge graph summary to the user. The subagent has done the heavy lifting - you just need to display its findings.

If the graph is sparse, suggest:
- Broader search terms
- Different project scope
- Creating new memories to build the graph

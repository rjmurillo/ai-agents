---
description: Search memories semantically using Forgetful with query context for improved ranking. Use when retrieving specific knowledge or verifying memory existence.
argument-hint: <search-query>
allowed-tools:
  - mcp__forgetful__*
---

# Memory Search

> **Interface Selection**: This is the CLI interface. See [Memory Interface Decision Matrix](../../../../AGENTS.md#memory-interface-decision-matrix) for when to use other interfaces.

Search the Forgetful knowledge base for relevant memories.

## Your Task

Perform a semantic search using `execute_forgetful_tool("query_memory", {...})` with the user's query.

**Query**: $ARGUMENTS

## Search Parameters

Use these parameters for the search:

```json
{
  "query": "<user's search query>",
  "query_context": "User initiated search via /memory-search command",
  "k": 5,
  "include_links": true,
  "max_links_per_primary": 3
}
```

If the query mentions a specific project, add `project_ids` filter.

## Response Format

Present results clearly:

1. **Summary**: Brief overview of what was found (or "No relevant memories found")
2. **Primary Memories**: For each memory show:
   - Title (with importance score)
   - Key content snippet
   - Tags
   - Linked memories if relevant
3. **Suggestions**: If results seem incomplete, suggest refining the query or creating a new memory

## Example

User: `/memory-search authentication patterns`

You search and respond:

```text
Found 3 memories about authentication patterns:

1. **FastAPI JWT Authentication** (Importance: 9)
   JWT middleware using httponly cookies for security...
   Tags: security, authentication, fastapi

2. **OAuth2 Decision** (Importance: 8)
   Chose OAuth2 over API keys for user-facing auth...
   Tags: decision, oauth, security

Related: Memory #45 (Session management approach)
```

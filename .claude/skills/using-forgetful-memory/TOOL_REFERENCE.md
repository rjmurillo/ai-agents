# Forgetful Tool Reference

Complete reference for all Forgetful MCP tools. Call via `execute_forgetful_tool(tool_name, args)`.

---

## Memory Tools

### query_memory
Semantic search across memories.

**Required:**
- `query` (str): Natural language search
- `query_context` (str): WHY you're searching (improves ranking)

**Optional:**
- `k` (int): Results count, 1-20 (default 5)
- `include_links` (bool): Include linked memories
- `max_links_per_primary` (int): Max links per result
- `importance_threshold` (int): Minimum importance 1-10
- `project_ids` (List[int]): Filter to projects
- `strict_project_filter` (bool): Links must also match projects

**Returns:** `{primary_memories, linked_memories, total_count, token_count, truncated}`

```python
execute_forgetful_tool("query_memory", {
  "query": "authentication patterns",
  "query_context": "building API login",
  "k": 5,
  "include_links": true
})
```

---

### create_memory
Store atomic memory with auto-linking.

**Required:**
- `title` (str): Max 200 chars
- `content` (str): Max 2000 chars (~300-400 words)
- `context` (str): WHY this matters, max 500 chars
- `keywords` (List[str]): Max 10, for semantic matching
- `tags` (List[str]): Max 10, for categorization
- `importance` (int): 1-10 scale

**Optional:**
- `project_ids` (List[int]): Link to projects
- `code_artifact_ids` (List[int]): Link to code artifacts
- `document_ids` (List[int]): Link to documents

**Returns:** `{id, title, linked_memory_ids, similar_memories}`

```python
execute_forgetful_tool("create_memory", {
  "title": "FastAPI auth pattern",
  "content": "Use JWT with httponly cookies for session management...",
  "context": "Security decision for API project",
  "keywords": ["auth", "jwt", "fastapi"],
  "tags": ["security", "pattern"],
  "importance": 9,
  "project_ids": [1]
})
```

---

### get_memory
Retrieve complete memory by ID.

**Required:**
- `memory_id` (int)

**Returns:** Complete Memory object with all fields

```python
execute_forgetful_tool("get_memory", {"memory_id": 42})
```

---

### update_memory
Update memory fields (PATCH semantics).

**Required:**
- `memory_id` (int)

**Optional (only changed fields):**
- `title`, `content`, `context` (str)
- `keywords`, `tags` (List[str])
- `importance` (int)
- `project_ids`, `code_artifact_ids`, `document_ids` (List[int])

```python
execute_forgetful_tool("update_memory", {
  "memory_id": 42,
  "importance": 9,
  "tags": ["updated", "verified"]
})
```

---

### link_memories
Create bidirectional links between memories.

**Required:**
- `memory_id` (int): Source memory
- `related_ids` (List[int]): Target memories to link

```python
execute_forgetful_tool("link_memories", {
  "memory_id": 42,
  "related_ids": [10, 15, 20]
})
```

---

### unlink_memories
Remove link between two memories.

**Required:**
- `source_id` (int)
- `target_id` (int)

```python
execute_forgetful_tool("unlink_memories", {
  "source_id": 42,
  "target_id": 57
})
```

---

### mark_memory_obsolete
Soft delete with audit trail.

**Required:**
- `memory_id` (int)
- `reason` (str): Why obsolete

**Optional:**
- `superseded_by` (int): Replacement memory ID

```python
execute_forgetful_tool("mark_memory_obsolete", {
  "memory_id": 42,
  "reason": "Superseded by newer decision",
  "superseded_by": 100
})
```

---

### get_recent_memories
Get newest memories sorted by creation.

**Optional:**
- `limit` (int): 1-100, default 10
- `project_ids` (List[int]): Filter to projects

```python
execute_forgetful_tool("get_recent_memories", {"limit": 5})
```

---

## Project Tools

### list_projects
List all projects with optional filtering.

**Optional:**
- `status` (str): "active", "archived", "completed"
- `repo_name` (str): Filter by "owner/repo"

**Returns:** `{projects: [...], count: N}`

```python
execute_forgetful_tool("list_projects", {})
execute_forgetful_tool("list_projects", {"repo_name": "owner/repo"})
```

---

### create_project
Create project container.

**Required:**
- `name` (str): Max 500 chars
- `description` (str): Purpose/scope
- `project_type` (str): "personal", "work", "learning", "development", "infrastructure", "template", "product", "marketing", "finance", "documentation", "development-environment", "third-party-library", "open-source"

**Optional:**
- `status` (str): "active", "archived", "completed"
- `repo_name` (str): "owner/repo" format
- `notes` (str): Workflow notes

```python
execute_forgetful_tool("create_project", {
  "name": "my-project",
  "description": "A new development project",
  "project_type": "development",
  "repo_name": "owner/my-project"
})
```

---

### get_project
Get project details by ID.

**Required:**
- `project_id` (int)

```python
execute_forgetful_tool("get_project", {"project_id": 1})
```

---

### update_project
Update project metadata (PATCH semantics).

**Required:**
- `project_id` (int)

**Optional:**
- `name`, `description`, `notes` (str)
- `project_type`, `status`, `repo_name` (str)

```python
execute_forgetful_tool("update_project", {
  "project_id": 1,
  "status": "archived"
})
```

---

### delete_project
Delete project (memories preserved).

**Required:**
- `project_id` (int)

```python
execute_forgetful_tool("delete_project", {"project_id": 1})
```

---

## Entity Tools

### create_entity
Create organization, person, team, or device.

**Required:**
- `name` (str)
- `entity_type` (str): "organization", "individual", "team", "device", "other"

**Optional:**
- `custom_type` (str): If type is "other"
- `notes` (str): Additional info
- `tags` (List[str]): Categorization
- `aka` (List[str]): Alternative names (searchable)
- `project_ids` (List[int]): Link to projects

```python
execute_forgetful_tool("create_entity", {
  "name": "Anthropic",
  "entity_type": "organization",
  "aka": ["Claude AI", "Anthropic AI"],
  "tags": ["ai", "research"]
})
```

---

### get_entity
Get entity by ID.

**Required:**
- `entity_id` (int)

```python
execute_forgetful_tool("get_entity", {"entity_id": 1})
```

---

### list_entities
List entities with filtering.

**Optional:**
- `project_ids` (List[int])
- `entity_type` (str)
- `tags` (List[str])

```python
execute_forgetful_tool("list_entities", {"entity_type": "organization"})
```

---

### search_entities
Text search by name or aliases.

**Required:**
- `query` (str): Search text (case-insensitive)

**Optional:**
- `entity_type` (str)
- `tags` (List[str])
- `limit` (int): 1-100

```python
execute_forgetful_tool("search_entities", {"query": "tech"})
```

---

### update_entity
Update entity (PATCH semantics).

**Required:**
- `entity_id` (int)

**Optional:**
- `name`, `entity_type`, `custom_type`, `notes` (str)
- `tags`, `aka` (List[str])
- `project_ids` (List[int])

```python
execute_forgetful_tool("update_entity", {
  "entity_id": 1,
  "aka": ["NewAlias", "AnotherName"]
})
```

---

### delete_entity
Delete entity (cascades links and relationships).

**Required:**
- `entity_id` (int)

```python
execute_forgetful_tool("delete_entity", {"entity_id": 1})
```

---

### link_entity_to_memory
Connect entity to memory.

**Required:**
- `entity_id` (int)
- `memory_id` (int)

```python
execute_forgetful_tool("link_entity_to_memory", {
  "entity_id": 1,
  "memory_id": 5
})
```

---

### unlink_entity_from_memory
Remove entity-memory connection.

**Required:**
- `entity_id` (int)
- `memory_id` (int)

```python
execute_forgetful_tool("unlink_entity_from_memory", {
  "entity_id": 1,
  "memory_id": 5
})
```

---

### get_entity_memories
Get all memories linked to entity.

**Required:**
- `entity_id` (int)

**Returns:** `{memory_ids: [...], count: N}`

```python
execute_forgetful_tool("get_entity_memories", {"entity_id": 42})
```

---

### create_entity_relationship
Create typed relationship between entities (knowledge graph edge).

**Required:**
- `source_entity_id` (int)
- `target_entity_id` (int)
- `relationship_type` (str): "works_for", "member_of", "owns", "reports_to", "collaborates_with", "uses", "depends_on", "calls", "extends", "implements", etc.

**Optional:**
- `strength` (float): 0.0-1.0
- `confidence` (float): 0.0-1.0
- `metadata` (dict): Additional data

```python
execute_forgetful_tool("create_entity_relationship", {
  "source_entity_id": 1,
  "target_entity_id": 2,
  "relationship_type": "uses",
  "strength": 0.9
})
```

---

### get_entity_relationships
Get relationships for entity.

**Required:**
- `entity_id` (int)

**Optional:**
- `direction` (str): "outgoing", "incoming", "both"
- `relationship_type` (str)

```python
execute_forgetful_tool("get_entity_relationships", {
  "entity_id": 1,
  "direction": "both"
})
```

---

### update_entity_relationship
Update relationship (PATCH semantics).

**Required:**
- `relationship_id` (int)

**Optional:**
- `relationship_type` (str)
- `strength`, `confidence` (float)
- `metadata` (dict)

```python
execute_forgetful_tool("update_entity_relationship", {
  "relationship_id": 1,
  "strength": 0.95
})
```

---

### delete_entity_relationship
Delete relationship.

**Required:**
- `relationship_id` (int)

```python
execute_forgetful_tool("delete_entity_relationship", {"relationship_id": 1})
```

---

## Document Tools

### create_document
Store long-form content (>300 words).

**Required:**
- `title` (str)
- `description` (str): Brief overview
- `content` (str): Full document text

**Optional:**
- `document_type` (str): "text", "markdown", "code"
- `filename` (str)
- `tags` (List[str])
- `project_id` (int)

```python
execute_forgetful_tool("create_document", {
  "title": "API Documentation",
  "description": "REST API endpoints reference",
  "content": "# API Endpoints\n\n## GET /users...",
  "document_type": "markdown",
  "project_id": 1
})
```

---

### get_document
Get document by ID.

**Required:**
- `document_id` (int)

```python
execute_forgetful_tool("get_document", {"document_id": 1})
```

---

### list_documents
List documents with filtering.

**Optional:**
- `project_id` (int)
- `document_type` (str)
- `tags` (List[str])

```python
execute_forgetful_tool("list_documents", {"project_id": 1})
```

---

### update_document
Update document (PATCH semantics).

**Required:**
- `document_id` (int)

**Optional:**
- `title`, `description`, `content`, `document_type`, `filename` (str)
- `tags` (List[str])
- `project_id` (int)

```python
execute_forgetful_tool("update_document", {
  "document_id": 1,
  "content": "Updated content..."
})
```

---

### delete_document
Delete document (cascades memory associations).

**Required:**
- `document_id` (int)

```python
execute_forgetful_tool("delete_document", {"document_id": 1})
```

---

## Code Artifact Tools

### create_code_artifact
Store reusable code snippets.

**Required:**
- `title` (str)
- `description` (str): What it does, when to use
- `code` (str): The actual code
- `language` (str): "python", "javascript", "typescript", etc.

**Optional:**
- `tags` (List[str])
- `project_id` (int)

```python
execute_forgetful_tool("create_code_artifact", {
  "title": "JWT Middleware",
  "description": "FastAPI middleware for JWT authentication",
  "code": "async def jwt_middleware(request, call_next):\n    ...",
  "language": "python",
  "tags": ["middleware", "auth"],
  "project_id": 1
})
```

---

### get_code_artifact
Get artifact by ID.

**Required:**
- `artifact_id` (int)

```python
execute_forgetful_tool("get_code_artifact", {"artifact_id": 1})
```

---

### list_code_artifacts
List artifacts with filtering.

**Optional:**
- `project_id` (int)
- `language` (str)
- `tags` (List[str])

```python
execute_forgetful_tool("list_code_artifacts", {"language": "python"})
```

---

### update_code_artifact
Update artifact (PATCH semantics).

**Required:**
- `artifact_id` (int)

**Optional:**
- `title`, `description`, `code`, `language` (str)
- `tags` (List[str])
- `project_id` (int)

```python
execute_forgetful_tool("update_code_artifact", {
  "artifact_id": 1,
  "tags": ["updated", "refactored"]
})
```

---

### delete_code_artifact
Delete artifact (cascades memory associations).

**Required:**
- `artifact_id` (int)

```python
execute_forgetful_tool("delete_code_artifact", {"artifact_id": 1})
```

---

## User Tools

### get_current_user
Get authenticated user info.

**Required:** (none)

**Returns:** `{id, external_id, name, email, notes, timestamps}`

```python
execute_forgetful_tool("get_current_user", {})
```

---

### update_user_notes
Store user preferences/notes.

**Required:**
- `user_notes` (str)

```python
execute_forgetful_tool("update_user_notes", {
  "user_notes": "Prefers React over Vue, uses VSCode, timezone: PST"
})
```

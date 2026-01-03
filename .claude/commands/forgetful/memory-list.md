---
description: List recent memories from Forgetful with optional project filtering. Use when exploring stored knowledge or verifying memory creation.
argument-hint: [project-name]
allowed-tools: [mcp__forgetful__*]
---

# List Recent Memories

Show the most recently created memories from Forgetful.

## Your Task

Retrieve recent memories using `execute_forgetful_tool("get_recent_memories", {...})`.

**Arguments**: $ARGUMENTS

## Parameters

Parse the arguments for:

- **Number**: If user specifies a count (e.g., "10", "last 5"), use that as `limit`
- **Project**: If user mentions a project name, first list projects to get the ID, then filter

Default: `{"limit": 10}`

## Response Format

Present memories in a clean, scannable format:

```text
Recent Memories (showing X of Y):

1. [Title] (Importance: X, Created: date)
   Tags: [tags]

2. [Title] (Importance: X, Created: date)
   Tags: [tags]

...
```

## Optional Enhancements

If the user asks for more detail on any memory, use `get_memory` to retrieve full content.

If filtering by project and no project_id provided, first call:

```javascript
execute_forgetful_tool("list_projects", {})
```

Then let the user select or infer from context.

## Examples

**Basic usage:**

```text
/memory-list
```

Returns last 10 memories across all projects.

**With count:**

```text
/memory-list 5
```

Returns last 5 memories.

**With project filter:**

```text
/memory-list forgetful project
```

Lists projects, finds "forgetful" project ID, returns recent memories for that project.

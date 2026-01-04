---
description: Gather comprehensive context from Forgetful Memory, Context7 docs, and web sources before planning or implementation. Use when starting complex tasks requiring multi-source context.
argument-hint: <task-or-technology>
allowed-tools: [mcp__forgetful__*, mcp__context7__*, mcp__serena__*, mcp__plugin_claude-mem_mcp-search__*, mcp__deepwiki__*, WebSearch, WebFetch]
model: opus
---

# Context Retrieval Command

**Purpose**: Gather relevant context from Forgetful Memory, Context7, and web sources before planning or implementing code.

**Usage**: `/context_gather <detailed task description>`

---

Use the **context-retrieval** subagent to gather context for the following task:

{TASK_DESCRIPTION}

The context-retrieval subagent will:

- Search Forgetful Memory across ALL projects for relevant patterns, decisions, and code
- Read linked code artifacts and documents
- Query Context7 for framework-specific guidance if applicable
- Explore the knowledge graph to find connected patterns
- Return a focused summary with code snippets and architectural insights

Wait for the subagent to return its findings before proceeding.

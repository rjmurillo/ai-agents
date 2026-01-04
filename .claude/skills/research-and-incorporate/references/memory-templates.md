# Memory Templates

Templates for creating atomic Forgetful memories from research.

---

## Atomic Memory Principles

Each memory must pass the atomicity test:

1. Can you understand it at first glance?
2. Can you title it in 5-50 words?
3. Does it represent ONE concept/fact/decision?

### Constraints

| Field | Limit | Guidance |
|-------|-------|----------|
| Title | 200 chars | Short, searchable phrase |
| Content | 2000 chars | Single concept (~300-400 words) |
| Context | 500 chars | WHY this matters |
| Keywords | 10 max | For semantic clustering |
| Tags | 10 max | For categorization |

---

## Memory Categories and Templates

### 1. Core Principle Memory

For foundational concepts that define the topic.

```python
mcp__forgetful__execute_forgetful_tool("create_memory", {
    "title": "{Topic}: Core Principle",
    "content": """{Topic} is [definition in 1-2 sentences].

Origin: [Where it comes from, who coined it]

Core insight: [The fundamental idea in plain language]

Decision rule: [How to apply this principle]
1. [Step 1]
2. [Step 2]
3. [Step 3]

Key heuristic: [One-line test for correct application]""",
    "context": "Researched {TOPIC} - core principle for project integration",
    "keywords": ["{topic}", "principle", "foundation", "{domain}"],
    "tags": ["research", "principles", "core-concept"],
    "importance": 9
})
```

### 2. Framework Memory

For decision frameworks, models, or structured approaches.

```python
mcp__forgetful__execute_forgetful_tool("create_memory", {
    "title": "{Topic}: {Framework Name} Framework",
    "content": """The {Framework Name} provides a structured approach to [purpose].

Phases/Steps:
1. **[Phase 1]**: [Description] - [Key question to answer]
2. **[Phase 2]**: [Description] - [Key question to answer]
3. **[Phase 3]**: [Description] - [Key question to answer]
4. **[Phase 4]**: [Description] - [Key question to answer]

When to use: [Conditions that trigger this framework]

Output: [What applying this framework produces]

Integration: [How this connects to ai-agents workflows]""",
    "context": "Researched {TOPIC} - decision framework for structured application",
    "keywords": ["{topic}", "framework", "decision", "process"],
    "tags": ["research", "frameworks", "decision-making"],
    "importance": 9
})
```

### 3. Application Pattern Memory

For concrete ways to apply the concept.

```python
mcp__forgetful__execute_forgetful_tool("create_memory", {
    "title": "{Topic}: {Application Area} Application",
    "content": """Applying {Topic} to {Application Area}:

Context: [When this pattern applies]

Pattern:
1. [Recognition step - how to identify the situation]
2. [Investigation step - what to examine]
3. [Evaluation step - how to assess findings]
4. [Action step - what to do based on evaluation]

Example: [Concrete instance from ai-agents or software engineering]

Pitfall to avoid: [Common mistake in this application]

Connection: [How this relates to existing project patterns]""",
    "context": "Researched {TOPIC} - practical application pattern",
    "keywords": ["{topic}", "application", "{area}", "pattern"],
    "tags": ["research", "patterns", "application"],
    "importance": 8
})
```

### 4. Failure Mode Memory

For anti-patterns and what to avoid.

```python
mcp__forgetful__execute_forgetful_tool("create_memory", {
    "title": "{Topic}: {Failure Name} Anti-Pattern",
    "content": """Anti-pattern: {Failure Name}

Description: [What this failure looks like in practice]

Why it happens: [Root cause of this failure]

Consequences: [What goes wrong when this occurs]

Detection: [How to recognize this failure mode]

Correction: [How to fix or prevent it]

Example: [Concrete instance where this occurred]

Related: [Other concepts this connects to]""",
    "context": "Researched {TOPIC} - failure mode to avoid",
    "keywords": ["{topic}", "anti-pattern", "failure", "{failure-type}"],
    "tags": ["research", "anti-patterns", "warnings"],
    "importance": 8
})
```

### 5. Project Integration Memory

For specific connections to ai-agents project.

```python
mcp__forgetful__execute_forgetful_tool("create_memory", {
    "title": "{Topic}: ai-agents Integration Pattern",
    "content": """{Topic} integrates with ai-agents project through [mechanism].

Integration points:
- **Agent**: [Which agent, specific application]
- **Protocol**: [Which protocol, enhancement opportunity]
- **Skill**: [Which skill, improvement area]
- **Memory**: [How this informs memory operations]

Implementation approach:
1. [Step 1 with file/component reference]
2. [Step 2 with file/component reference]
3. [Step 3 with file/component reference]

Verification: [How to confirm correct integration]

Related memories: [IDs of connected memories]""",
    "context": "Researched {TOPIC} - project integration pattern",
    "keywords": ["{topic}", "ai-agents", "integration", "{component}"],
    "tags": ["research", "integration", "project-specific"],
    "importance": 8
})
```

### 6. Relationship Memory

For connections between concepts.

```python
mcp__forgetful__execute_forgetful_tool("create_memory", {
    "title": "{Topic}: Relationship to {Other Concept}",
    "content": """{Topic} relates to {Other Concept} through [relationship type].

Similarity: [What they have in common]

Difference: [Where they diverge]

Synergy: [How they work together]

When to use each:
- Use {Topic} when: [conditions]
- Use {Other Concept} when: [conditions]
- Use both when: [conditions]

Practical guidance: [How to decide between them in ai-agents context]""",
    "context": "Researched {TOPIC} - relationship mapping for knowledge graph",
    "keywords": ["{topic}", "{other-concept}", "relationship", "comparison"],
    "tags": ["research", "relationships", "knowledge-graph"],
    "importance": 7
})
```

### 7. Decision Heuristic Memory

For quick decision rules derived from the topic.

```python
mcp__forgetful__execute_forgetful_tool("create_memory", {
    "title": "{Topic}: Decision Heuristic for {Situation}",
    "content": """When facing {Situation}, apply this heuristic:

Question: [The key question to ask]

Decision matrix:
| Condition | Action |
|-----------|--------|
| [Condition 1] | [Action 1] |
| [Condition 2] | [Action 2] |
| [Condition 3] | [Action 3] |

Default: [What to do if uncertain]

Rationale: [Why this heuristic works, traced to {Topic}]

Example: [Concrete application of this heuristic]""",
    "context": "Researched {TOPIC} - decision heuristic for rapid application",
    "keywords": ["{topic}", "heuristic", "decision", "{situation}"],
    "tags": ["research", "heuristics", "quick-reference"],
    "importance": 8
})
```

---

## Importance Scoring Guide

| Score | Use For | Example |
|-------|---------|---------|
| 10 | Foundational principles that inform multiple systems | Memory-first architecture principle |
| 9 | Critical frameworks that guide major decisions | Four-phase decision framework |
| 8 | Practical patterns with broad applicability | Application patterns, failure modes |
| 7 | Specific applications with clear value | Relationships, niche applications |

---

## Linking Strategy

After creating memories:

1. **Auto-linking**: Forgetful automatically links memories with cosine similarity ≥0.7
2. **Manual linking**: Connect related memories that auto-linking might miss

```python
# Query for related memories
mcp__forgetful__execute_forgetful_tool("query_memory", {
    "query": "{related-concept}",
    "query_context": "Finding memories to link with {TOPIC}"
})

# Link memories bidirectionally
mcp__forgetful__execute_forgetful_tool("link_memories", {
    "memory_id": new_memory_id,
    "related_ids": [id1, id2, id3]
})
```

**Link when:**

- Concepts are complementary (use together)
- Concepts are alternatives (choose between)
- Concepts share a domain
- One concept implements another

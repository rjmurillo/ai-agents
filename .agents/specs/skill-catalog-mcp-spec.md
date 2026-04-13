# Skill Catalog MCP Technical Specification

> **Status**: Draft
> **Version**: 0.1.0
> **ADR**: [ADR-012](../architecture/ADR-012-skill-catalog-mcp.md)
> **Date**: 2025-12-21

## Overview

The Skill Catalog MCP provides unified discovery, search, and usage tracking for both executable skills (`.claude/skills/`) and learned patterns (`.agents/skills/`).

---

## Architecture Diagram

```
┌────────────────────────────────────────────────────────────────────┐
│                          Claude Code CLI                            │
│                                                                      │
│  "search_skills()"  ───>  Skill Catalog MCP  <───>  Serena MCP     │
│  "check_skill_exists()"         │                       │           │
│  "cite_skill()"                 v                       v           │
│                          ┌─────────────┐         ┌──────────┐       │
│                          │ Skill Index │         │ Memories │       │
│                          └─────────────┘         └──────────┘       │
└────────────────────────────────────────────────────────────────────┘
                                  │
         ┌────────────────────────┼────────────────────────┐
         │                        │                        │
         v                        v                        v
┌─────────────────┐    ┌──────────────────┐    ┌───────────────────┐
│ .claude/skills/ │    │ .agents/skills/  │    │ .serena/memories/ │
│                 │    │                  │    │                   │
│ github/         │    │ linting.md       │    │ skills-*.md       │
│   SKILL.md      │    │ documentation.md │    │                   │
│   scripts/*.ps1 │    │ workflow.md      │    │                   │
└─────────────────┘    └──────────────────┘    └───────────────────┘
```

---

## Skill Index Schema

```typescript
interface SkillIndex {
  version: string;
  built_at: string;
  skills: IndexedSkill[];
  categories: Record<string, CategoryInfo>;
  capability_map: Record<string, Record<string, string>>;
}

interface IndexedSkill {
  id: string;                      // e.g., "github/pr/Get-PRContext"
  type: "executable" | "learned";
  category: string;
  name: string;
  statement: string;
  location: string;

  // Executable-specific
  script_path?: string;
  parameters?: Parameter[];

  // Learned-specific
  atomicity?: number;
  evidence?: string;
  is_anti_pattern?: boolean;

  search_tokens: string[];
}
```

---

## Tool Implementations

### search_skills

```typescript
interface SearchSkillsParams {
  query: string;
  category?: string;
  type?: "executable" | "learned";
  limit?: number;  // default: 10
}

interface SearchSkillsResult {
  skills: SkillSummary[];
  total_count: number;
}
```

**Algorithm:**
1. Tokenize query into search terms
2. Filter by category/type if specified
3. Score each skill by token overlap + field weights
4. Sort by relevance, return top N

### check_skill_exists

```typescript
interface CheckSkillExistsParams {
  operation: "gh" | "git" | "npm";
  subcommand?: string;
}

interface CheckSkillExistsResult {
  exists: boolean;
  skill_id?: string;
  skill_path?: string;
  usage_example?: string;
  blocking: boolean;
  message: string;
}
```

**Capability Map:**

| Operation | Subcommand | Skill |
|-----------|------------|-------|
| gh | pr view | github/pr/Get-PRContext |
| gh | pr comment | github/pr/Post-PRCommentReply |
| gh | issue edit --add-label | github/issue/Set-IssueLabels |
| gh | issue comment | github/issue/Post-IssueComment |

### cite_skill

```typescript
interface CiteSkillParams {
  skill_id: string;
  context: string;
  outcome?: "success" | "failure";
}

interface CiteSkillResult {
  citation_id: string;
  recorded: boolean;
}
```

Persists to Serena memory `skill-usage-citations`.

### suggest_skills

```typescript
interface SuggestSkillsParams {
  task: string;
  operations_planned?: string[];
}

interface SuggestSkillsResult {
  suggestions: SkillSuggestion[];
  warnings: string[];  // Raw command violations
}
```

---

## Serena Integration

| Memory | Purpose | Format |
|--------|---------|--------|
| `skill-catalog-index` | Cached search index | JSON in markdown |
| `skill-usage-citations` | Citation history | Markdown table |

### Index Refresh

```typescript
async function getOrBuildIndex(): Promise<SkillIndex> {
  const cached = await serena.read_memory("skill-catalog-index");
  if (cached && !isStale(cached)) {
    return parseIndex(cached);
  }
  const fresh = await buildIndex();
  await serena.write_memory("skill-catalog-index", serializeIndex(fresh));
  return fresh;
}
```

---

## Integration with Other MCPs

### Session State MCP

- On `SKILL_VALIDATION` phase, invoke `check_skill_exists` for planned operations
- Record skill citations in session evidence

### Agent Orchestration MCP

- Before `invoke_agent`, run `suggest_skills` on prompt
- Return warnings if raw commands detected

---

## References

- [ADR-012](../architecture/ADR-012-skill-catalog-mcp.md)
- [skill-usage-mandatory](../../.serena/memories/skill-usage-mandatory.md)

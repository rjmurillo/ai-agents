# ADR-012: Skill Catalog MCP

## Status

Proposed

## Date

2025-12-21

## Context

The ai-agents project maintains two skill repositories:

1. **Claude Skills** (`.claude/skills/`): Executable PowerShell scripts for GitHub operations, steering matching
2. **Agent Skills** (`.agents/skills/`): Learned patterns with evidence, organized by category

Evidence from retrospectives shows skill usage violations are common:

- **Session 15**: 5+ violations of `skill-usage-mandatory` - agents used raw `gh` commands despite skill availability
- **Root cause**: Agents don't check skill inventory before writing code
- **Pattern**: Trust-based reminders fail; verification-based gates succeed

### Current State

| Repository | Location | Format | Purpose |
|------------|----------|--------|---------|
| Claude Skills | `.claude/skills/` | PowerShell + SKILL.md | Executable operations |
| Agent Skills | `.agents/skills/` | Markdown | Learned patterns |
| Serena Memories | `.serena/memories/skills-*` | Markdown | Category indexes |

### Problems

1. **No unified search**: Must know exact file path to find skills
2. **No usage tracking**: Can't verify if skill was actually used
3. **Duplicate implementations**: Agents write inline code duplicating skills
4. **No citation mechanism**: Can't trace which skill guided a decision

## Decision

Create a **Skill Catalog MCP** that:

1. Indexes both skill repositories into a unified searchable catalog
2. Provides skill search by keyword, category, and capability
3. Tracks skill usage with citations
4. Validates skill existence before allowing raw commands
5. Suggests relevant skills based on task context

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Skill Catalog MCP                           │
├─────────────────────────────────────────────────────────────────┤
│  TOOLS                           │  RESOURCES                    │
│  ─────                           │  ─────────                    │
│  search_skills(query)            │  skills://catalog             │
│  get_skill(id)                   │  skills://categories          │
│  check_skill_exists(operation)   │  skills://usage               │
│  cite_skill(id, context)         │  skills://suggestions         │
│  suggest_skills(task)            │                               │
│  validate_no_raw_commands()      │                               │
├─────────────────────────────────────────────────────────────────┤
│                    SKILL SOURCES                                 │
│  ─────────────────────────────────────────────────────────────  │
│  .claude/skills/                                                 │
│  ├── github/                                                     │
│  │   ├── SKILL.md (capability index)                            │
│  │   └── scripts/**/*.ps1 (executable skills)                   │
│  └── steering-matcher/                                           │
│      └── Get-ApplicableSteering.ps1                             │
│                                                                  │
│  .agents/skills/                                                 │
│  ├── linting.md (Skill-Lint-001 through 009)                    │
│  ├── documentation.md (Skill-Doc-*)                             │
│  └── multi-agent-workflow.md (Skill-Workflow-*)                 │
│                                                                  │
│  .serena/memories/skills-*.md (category indexes)                │
└─────────────────────────────────────────────────────────────────┘
```

## Tool Interface Design

### search_skills

Search for skills by keyword, category, or capability.

```typescript
interface SearchSkillsParams {
  query: string;                   // Free-text search
  category?: string;               // Filter by category (github, linting, workflow)
  type?: "executable" | "learned"; // Filter by skill type
  capability?: string;             // Filter by capability (pr, issue, lint)
  limit?: number;                  // Max results (default: 10)
}

interface SearchSkillsResult {
  skills: SkillSummary[];
  total_count: number;
  categories_matched: string[];
}

interface SkillSummary {
  id: string;                      // e.g., "Skill-Lint-001" or "github/pr/Get-PRContext"
  name: string;                    // Human-readable name
  type: "executable" | "learned";
  category: string;
  statement: string;               // One-line description
  location: string;                // File path
  relevance_score: number;         // 0-100 match score
}
```

**Search Index Structure:**

| Field | Source | Weight |
|-------|--------|--------|
| id | Skill ID (Skill-*) or script name | 1.0 |
| statement | Statement/description field | 0.9 |
| context | Context/when to use field | 0.8 |
| evidence | Evidence field | 0.5 |
| tags | Tags/categories | 0.7 |
| file_path | Full path | 0.3 |

### get_skill

Retrieve full skill definition including examples and evidence.

```typescript
interface GetSkillParams {
  id: string;                      // Skill ID or path
  include_examples?: boolean;      // Include usage examples
  include_evidence?: boolean;      // Include validation evidence
}

interface GetSkillResult {
  id: string;
  type: "executable" | "learned";
  name: string;
  category: string;
  statement: string;
  context: string;                 // When to use
  location: string;

  // For executable skills
  script_path?: string;
  parameters?: Parameter[];
  examples?: Example[];
  exit_codes?: ExitCode[];

  // For learned skills
  atomicity?: number;              // 0-100%
  evidence?: string;
  impact?: string;
  tags?: string[];
  anti_pattern?: boolean;

  // Usage tracking
  last_cited?: string;             // ISO timestamp
  citation_count?: number;
}
```

### check_skill_exists

**BLOCKING gate**: Verify if a skill exists for a given operation before allowing raw commands.

```typescript
interface CheckSkillExistsParams {
  operation: "gh" | "git" | "npm" | "pwsh";
  subcommand?: string;             // e.g., "pr view", "issue create"
  capability?: string;             // e.g., "post comment", "get context"
}

interface CheckSkillExistsResult {
  exists: boolean;
  skill_id?: string;               // If exists, which skill
  skill_path?: string;             // Path to skill
  usage_example?: string;          // How to use instead
  blocking: boolean;               // Should block raw command
  message: string;                 // Human-readable guidance
}
```

**Capability Mapping:**

| Operation | Subcommand | Skill Path | Exists |
|-----------|------------|------------|--------|
| gh | pr view | .claude/skills/github/scripts/pr/Get-PRContext.ps1 | ✅ |
| gh | pr comment | .claude/skills/github/scripts/pr/Post-PRCommentReply.ps1 | ✅ |
| gh | issue create | (none) | ❌ |
| gh | issue edit --add-label | .claude/skills/github/scripts/issue/Set-IssueLabels.ps1 | ✅ |
| gh | api | Varies by endpoint | Partial |

### cite_skill

Record that a skill was used, enabling usage tracking and validation.

```typescript
interface CiteSkillParams {
  skill_id: string;
  context: string;                 // What task used this skill
  outcome?: "success" | "failure"; // Result of using skill
  notes?: string;                  // Additional context
}

interface CiteSkillResult {
  citation_id: string;             // Unique citation reference
  skill_id: string;
  timestamp: string;
  session_id?: string;             // If Session State MCP active
  recorded: boolean;
}
```

### suggest_skills

Given a task description, suggest relevant skills.

```typescript
interface SuggestSkillsParams {
  task: string;                    // Task description
  files_affected?: string[];       // Files being modified
  operations_planned?: string[];   // Operations agent plans to perform
}

interface SuggestSkillsResult {
  suggestions: SkillSuggestion[];
  warnings: string[];              // e.g., "Raw gh command detected"
}

interface SkillSuggestion {
  skill_id: string;
  relevance: "high" | "medium" | "low";
  reason: string;                  // Why this skill is relevant
  usage_hint: string;              // Quick usage example
}
```

### validate_no_raw_commands

**Validation tool**: Check if planned commands violate skill-usage-mandatory.

```typescript
interface ValidateNoRawCommandsParams {
  commands: string[];              // Commands agent plans to execute
}

interface ValidateNoRawCommandsResult {
  valid: boolean;
  violations: Violation[];
  suggested_alternatives: Alternative[];
}

interface Violation {
  command: string;
  reason: string;
  skill_alternative: string;
}
```

## Resource URIs

### skills://catalog

Full skill catalog with all indexed skills.

```json
{
  "total_skills": 45,
  "by_type": {
    "executable": 15,
    "learned": 30
  },
  "by_category": {
    "github": 12,
    "linting": 9,
    "workflow": 10,
    "documentation": 10,
    "other": 4
  },
  "skills": [
    {
      "id": "github/pr/Get-PRContext",
      "type": "executable",
      "category": "github",
      "statement": "Get PR metadata, diff, and changed files",
      "location": ".claude/skills/github/scripts/pr/Get-PRContext.ps1"
    },
    {
      "id": "Skill-Lint-001",
      "type": "learned",
      "category": "linting",
      "statement": "Run markdownlint --fix before manual edits to auto-resolve spacing violations",
      "location": ".agents/skills/linting.md"
    }
  ]
}
```

### skills://categories

Category hierarchy with skill counts.

```json
{
  "categories": [
    {
      "name": "github",
      "subcategories": ["pr", "issue", "reactions"],
      "skill_count": 12,
      "description": "GitHub CLI operations"
    },
    {
      "name": "linting",
      "subcategories": [],
      "skill_count": 9,
      "description": "Code quality and documentation standards"
    },
    {
      "name": "workflow",
      "subcategories": [],
      "skill_count": 10,
      "description": "Multi-agent coordination patterns"
    }
  ]
}
```

### skills://usage

Usage tracking and citation history.

```json
{
  "citations": [
    {
      "citation_id": "cite-001",
      "skill_id": "github/pr/Get-PRContext",
      "timestamp": "2025-12-21T15:00:00Z",
      "session_id": "2025-12-21-session-01",
      "context": "Getting PR context for review",
      "outcome": "success"
    }
  ],
  "most_cited": [
    { "skill_id": "Skill-Lint-001", "count": 15 },
    { "skill_id": "github/pr/Get-PRContext", "count": 12 }
  ],
  "never_cited": [
    "Skill-Doc-003",
    "github/reactions/Add-CommentReaction"
  ]
}
```

### skills://suggestions

Context-aware skill suggestions based on current task.

```json
{
  "current_context": {
    "task": "Address PR review comments",
    "files_affected": [".github/workflows/ai-issue-triage.yml"],
    "operations_detected": ["gh pr comment", "gh api"]
  },
  "suggestions": [
    {
      "skill_id": "github/pr/Post-PRCommentReply",
      "relevance": "high",
      "reason": "Detected 'gh pr comment' - use skill instead"
    },
    {
      "skill_id": "Skill-Workflow-001",
      "relevance": "medium",
      "reason": "Multi-file change - consider full agent pipeline"
    }
  ]
}
```

## Serena Integration

### Memory Schema

| Memory Name | Purpose | Update Frequency |
|-------------|---------|------------------|
| `skill-catalog-index` | Full searchable index | On index rebuild |
| `skill-usage-citations` | Citation history | On each cite_skill |
| `skill-suggestions-cache` | Recent suggestions | On suggest_skills |

### Index Building

```typescript
async function buildSkillIndex(): Promise<SkillIndex> {
  const index: SkillIndex = { skills: [], categories: {} };

  // 1. Index Claude Skills (executable)
  const claudeSkills = await glob(".claude/skills/**/SKILL.md");
  for (const skillFile of claudeSkills) {
    const skill = await parseSkillMd(skillFile);
    const scripts = await glob(dirname(skillFile) + "/scripts/**/*.ps1");
    for (const script of scripts) {
      index.skills.push({
        id: pathToId(script),
        type: "executable",
        category: skill.name,
        statement: await extractDescription(script),
        location: script,
        parameters: await parseParameters(script)
      });
    }
  }

  // 2. Index Agent Skills (learned)
  const agentSkills = await glob(".agents/skills/*.md");
  for (const skillFile of agentSkills) {
    const skills = await parseAgentSkillsMd(skillFile);
    for (const skill of skills) {
      index.skills.push({
        id: skill.id,
        type: "learned",
        category: skill.category,
        statement: skill.statement,
        location: skillFile,
        atomicity: skill.atomicity,
        evidence: skill.evidence
      });
    }
  }

  // 3. Index Serena skill memories
  const skillMemories = await serena.list_memories();
  const relevantMemories = skillMemories.filter(m => m.startsWith("skills-"));
  for (const memory of relevantMemories) {
    const content = await serena.read_memory(memory);
    const skills = await parseMemorySkills(content);
    // Merge with existing, avoiding duplicates
  }

  // 4. Persist index
  await serena.write_memory("skill-catalog-index", JSON.stringify(index));

  return index;
}
```

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Manual skill lookup | No new tooling | Proven to fail (Session 15) | Agents don't check |
| Pre-commit hook only | Catches violations | Post-hoc, requires rework | Doesn't prevent |
| Inline documentation | Simple | Already exists, ignored | Not searchable |
| Single skill format | Consistency | Major migration effort | Both formats valuable |

### Trade-offs

**Index freshness vs performance**: Building index on every query is slow. Solution: Cache in Serena memory, rebuild on file changes.

**Strict enforcement vs flexibility**: Blocking all raw commands is aggressive. Solution: Only block when skill exists.

## Consequences

### Positive

- Unified skill discovery across both repositories
- Usage tracking enables skill effectiveness measurement
- Citation mechanism provides audit trail
- Proactive suggestions prevent violations
- Integration with Session State MCP for session-level tracking

### Negative

- Index maintenance overhead
- New MCP to develop and maintain
- Potential false positives in capability matching

### Neutral

- Existing skill files unchanged (read-only integration)
- `skill-usage-mandatory` memory remains (MCP enforces it)

## Implementation Notes

### Phase 1: Core Catalog (P0)

1. Implement skill index builder
2. Add search_skills and get_skill tools
3. Create skills://catalog resource

### Phase 2: Validation (P1)

1. Add check_skill_exists tool
2. Integrate with Session State MCP Phase 1.5
3. Add validate_no_raw_commands

### Phase 3: Usage Tracking (P2)

1. Implement cite_skill with Serena persistence
2. Add skills://usage resource
3. Create usage analytics

### Phase 4: Smart Suggestions (P3)

1. Implement suggest_skills with context analysis
2. Add skills://suggestions resource
3. Integrate with orchestrator

## Related Decisions

- [ADR-005: PowerShell-Only Scripting](./ADR-005-powershell-only-scripting.md)
- [ADR-006: Thin Workflows, Testable Modules](./ADR-006-thin-workflows-testable-modules.md)
- [ADR-011: Session State MCP](./ADR-011-session-state-mcp.md)

## References

- [skill-usage-mandatory](../.serena/memories/skill-usage-mandatory.md) - Enforcement requirements
- [.claude/skills/github/SKILL.md](../../.claude/skills/github/SKILL.md) - Executable skill structure
- [.agents/skills/README.md](../.agents/skills/README.md) - Learned skill structure

---

*Template Version: 1.0*
*Created: 2025-12-21*

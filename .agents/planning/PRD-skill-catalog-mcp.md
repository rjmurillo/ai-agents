# PRD: Skill Catalog MCP

> **Status**: Draft
> **Version**: 1.0.0
> **Date**: 2025-12-21
> **ADR**: [ADR-012](../architecture/ADR-012-skill-catalog-mcp.md)
> **Spec**: [Technical Specification](../specs/skill-catalog-mcp-spec.md)

---

## 1. Executive Summary

**Problem**: Agents repeatedly violate skill-usage-mandatory by writing raw `gh` commands instead of using tested, validated skills from `.claude/skills/github/`. Session 15 logged 5+ violations despite explicit reminders and enforcement memories.

**Root Cause**: No unified discovery mechanism for skills across two repositories (`.claude/skills/` executable PowerShell, `.agents/skills/` learned patterns). Agents must manually search file paths, leading to habit-driven inline code instead of skill reuse.

**Solution**: Build a **Skill Catalog MCP** that indexes both skill repositories, provides semantic search, validates skill existence before allowing raw commands, tracks usage via citations, and suggests relevant skills based on task context.

**Business Value**:
- **Reduce violations**: BLOCKING gate prevents raw commands when skills exist
- **Increase skill adoption**: Search discovers skills agents didn't know existed
- **Measure effectiveness**: Usage tracking identifies underutilized vs. high-value skills
- **Prevent duplication**: Citation mechanism provides audit trail

---

## 2. Background & Problem Statement

### 2.1 Current State

The ai-agents project maintains skill knowledge in three locations:

| Repository | Location | Format | Purpose |
|------------|----------|--------|---------|
| Claude Skills | `.claude/skills/` | PowerShell + SKILL.md | Executable GitHub operations with Pester tests |
| Agent Skills | `.agents/skills/` | Markdown | Learned patterns with evidence (Skill-Lint-001, etc.) |
| Serena Memories | `.serena/memories/skills-*.md` | Markdown | Category indexes manually maintained |

**Example Executable Skill** (`.claude/skills/github/scripts/pr/Get-PRContext.ps1`):
- Fetches PR metadata, diff, and changed files
- Handles pagination automatically
- Returns structured JSON
- Exit code 0 on success, 2 if PR not found

**Example Learned Skill** (`Skill-Lint-001` from `.agents/skills/linting.md`):
- Statement: "Run markdownlint --fix before manual edits"
- Evidence: "Reduced manual edit effort by 60% in Session 13"
- Atomicity: 95%

### 2.2 Pain Points

#### Evidence from Session 15 Violations

From `.serena/memories/skill-usage-mandatory.md`:

**Violation Pattern**:
```bash
# Agent wrote this:
gh pr view $PR_NUMBER --json title,body,files

# Should have used:
pwsh .claude/skills/github/scripts/pr/Get-PRContext.ps1 -PullRequest $PR_NUMBER -IncludeChangedFiles
```

**Violation Count**: 5+ instances in a single session

**Root Causes**:
1. **No discovery mechanism**: Agent must know exact file path `.claude/skills/github/scripts/pr/Get-PRContext.ps1`
2. **Habit-driven behavior**: Default to inline bash despite reminders
3. **No verification gate**: Trust-based enforcement fails; agents don't check before writing
4. **No usage tracking**: Can't measure if skill was actually invoked vs. documented

#### Current Search Experience

**To find skills today, agents must**:
1. Know skill exists
2. Know exact category (`pr/`, `issue/`, `linting/`, `workflow/`)
3. Navigate to specific markdown file or PowerShell script
4. Parse structure manually

**No support for**:
- "Find all skills related to PR comments"
- "Is there a skill for adding labels to issues?"
- "What linting skills exist?"

### 2.3 Why This Matters

**Skill development is expensive**:
- GitHub skill scripts have Pester tests, error handling, pagination
- Learned skills capture organizational knowledge from retrospectives

**Inline code duplication is costly**:
- No tests (brittle)
- No error handling (silent failures)
- No reuse (reinventing wheel)
- No updates (stale patterns)

**Example**: `Get-PRReviewers.ps1` enumerates all reviewers including bots. Inline `gh pr view` only returns requested reviewers, missing actual review activity (Skill-PR-001 violation).

---

## 3. Goals & Non-Goals

### 3.1 Goals

1. **Unified Discovery**: Single search interface for all skills (executable + learned)
2. **Violation Prevention**: BLOCKING validation gate before raw command execution
3. **Usage Analytics**: Track which skills are used, when, and in what context
4. **Proactive Suggestions**: Recommend relevant skills based on task description
5. **Integration**: Seamless Serena MCP integration for index persistence

### 3.2 Non-Goals

1. **NOT building skill execution engine**: Scripts execute via existing `Bash(pwsh:*)` tool
2. **NOT migrating skill formats**: Both `.claude/skills/` and `.agents/skills/` remain as-is
3. **NOT replacing skill-usage-mandatory memory**: MCP enforces it, doesn't replace it
4. **NOT version control**: Skills use git for versioning, not MCP-level versioning
5. **NOT skill authoring tools**: Out of scope for v1.0

---

## 4. User Stories

### 4.1 Agent Personas

**Orchestrator Agent**: Routes tasks to specialized agents, needs to suggest relevant skills before delegation

**Implementer Agent**: Writes code, needs to verify skills exist before writing raw commands

**PR Comment Responder Agent**: Posts PR comments, must use `Post-PRCommentReply.ps1` skill

**QA Agent**: Validates session quality, needs to check skill citation compliance

### 4.2 Stories

#### Story 1: Discover Skills Before Writing Code

**As an** implementer agent
**I want to** search for skills by capability (e.g., "add labels to issue")
**So that** I can reuse tested code instead of writing inline scripts

**Acceptance Criteria**:
- Search `search_skills(query="add labels")` returns `Set-IssueLabels.ps1`
- Result includes full path, parameters, and usage example
- Search works across both executable and learned skills

---

#### Story 2: Block Raw Commands When Skill Exists

**As a** QA agent
**I want to** validate that agents check skill existence before raw commands
**So that** skill-usage-mandatory violations are prevented proactively

**Acceptance Criteria**:
- `check_skill_exists(operation="gh", subcommand="pr view")` returns `exists: true, skill_id: "github/pr/Get-PRContext"`
- If skill exists, `blocking: true` prevents raw `gh pr view`
- Validation provides usage example as alternative

**Evidence**: Session 15 had 5 violations. With BLOCKING gate, violations MUST be 0.

---

#### Story 3: Track Skill Usage for Analytics

**As a** retrospective agent
**I want to** see which skills were used in a session
**So that** I can identify underutilized skills or missing capabilities

**Acceptance Criteria**:
- `cite_skill(skill_id="github/pr/Get-PRContext", context="Fetching PR #50 for review")` records citation
- `skills://usage` resource shows citation count per skill
- Session log includes skill citations in evidence section

---

#### Story 4: Suggest Skills Based on Task

**As an** orchestrator agent
**I want to** get skill suggestions when routing tasks
**So that** I can include relevant skills in delegation prompt

**Acceptance Criteria**:
- `suggest_skills(task="Address PR review comments", operations_planned=["gh pr comment"])` returns `Post-PRCommentReply.ps1` as high-relevance
- Warnings flag raw command usage
- Suggestions include usage hints

---

## 5. Functional Requirements

> **RFC 2119 Key Words**: MUST (required), SHOULD (recommended), MAY (optional)

### 5.1 Skill Indexing (P0)

**REQ-INDEX-001** (MUST): MCP MUST index all `.claude/skills/**/SKILL.md` files and associated PowerShell scripts

**REQ-INDEX-002** (MUST): MCP MUST index all `.agents/skills/*.md` files and parse individual Skill-* entries

**REQ-INDEX-003** (MUST): MCP MUST index Serena memories matching pattern `skills-*.md`

**REQ-INDEX-004** (MUST): Index schema MUST include:
- `id`: Unique identifier (e.g., `github/pr/Get-PRContext` or `Skill-Lint-001`)
- `type`: `executable` or `learned`
- `category`: Skill category (github, linting, workflow, documentation)
- `statement`: One-line description
- `location`: Absolute file path
- `search_tokens`: Tokenized searchable fields

**REQ-INDEX-005** (SHOULD): Index SHOULD include optional fields:
- `parameters`: For executable skills (PowerShell script parameters)
- `atomicity`: For learned skills (0-100% reliability score)
- `evidence`: For learned skills (retrospective evidence)
- `tags`: Category tags for filtering

**REQ-INDEX-006** (MUST): Index MUST be persisted to Serena memory `skill-catalog-index`

**REQ-INDEX-007** (SHOULD): Index refresh SHOULD be triggered on file changes to skill directories

### 5.2 Skill Search (P0)

**REQ-SEARCH-001** (MUST): `search_skills` tool MUST support free-text query search

**REQ-SEARCH-002** (MUST): Search MUST score results by relevance using weighted fields:
| Field | Weight |
|-------|--------|
| id (exact match) | 1.0 |
| statement | 0.9 |
| context | 0.8 |
| tags | 0.7 |
| evidence | 0.5 |

**REQ-SEARCH-003** (SHOULD): Search SHOULD support filtering by:
- `category`: Filter to specific category (github, linting)
- `type`: Filter to `executable` or `learned`
- `capability`: Filter by capability keyword (pr, issue, lint)

**REQ-SEARCH-004** (MUST): Search results MUST include:
- Skill summary (id, name, statement, location)
- Relevance score (0-100)
- Total count of matches

**REQ-SEARCH-005** (MUST): Default result limit MUST be 10, MAY be overridden via `limit` parameter

### 5.3 Skill Retrieval (P0)

**REQ-GET-001** (MUST): `get_skill` tool MUST retrieve full skill definition by ID or path

**REQ-GET-002** (MUST): Response MUST include all indexed fields plus:
- `examples`: Usage examples (if available)
- `exit_codes`: For executable skills (PowerShell exit code meanings)

**REQ-GET-003** (SHOULD): Response SHOULD include usage tracking:
- `last_cited`: ISO timestamp of most recent citation
- `citation_count`: Total citations across all sessions

**REQ-GET-004** (MUST): Tool MUST return error if skill ID not found

### 5.4 Skill Existence Validation (P1)

**REQ-VALIDATE-001** (MUST): `check_skill_exists` tool MUST verify if skill exists for given operation

**REQ-VALIDATE-002** (MUST): Tool MUST support operations:
- `gh` (GitHub CLI)
- `git` (Git CLI)
- `npm` (Node Package Manager)
- `pwsh` (PowerShell general)

**REQ-VALIDATE-003** (MUST): For GitHub operations, MUST maintain capability map:

| Operation | Subcommand | Skill ID | Blocking |
|-----------|------------|----------|----------|
| gh | pr view | github/pr/Get-PRContext | ✅ |
| gh | pr comment | github/pr/Post-PRCommentReply | ✅ |
| gh | issue edit --add-label | github/issue/Set-IssueLabels | ✅ |
| gh | issue comment | github/issue/Post-IssueComment | ✅ |
| gh | api /repos/.../reactions | github/reactions/Add-CommentReaction | ⚠️ Conditional |

**REQ-VALIDATE-004** (MUST): Response MUST include:
- `exists`: Boolean
- `blocking`: Whether to block raw command
- `message`: Human-readable guidance
- `skill_id`: If exists, which skill
- `usage_example`: How to use skill instead

**REQ-VALIDATE-005** (MUST): For operations with existing skills, `blocking` MUST be `true`

**REQ-VALIDATE-006** (SHOULD): For `gh api` endpoints, SHOULD check if specific endpoint has skill wrapper

### 5.5 Usage Tracking (P2)

**REQ-USAGE-001** (MUST): `cite_skill` tool MUST record skill usage with:
- `skill_id`: Skill being cited
- `context`: Task description
- `timestamp`: ISO 8601 timestamp
- `outcome`: `success` or `failure` (optional)

**REQ-USAGE-002** (MUST): Citations MUST be persisted to Serena memory `skill-usage-citations`

**REQ-USAGE-003** (SHOULD): If Session State MCP is active, citation SHOULD include `session_id`

**REQ-USAGE-004** (MUST): `skills://usage` resource MUST provide:
- All citations (chronological)
- Most cited skills (ranked by count)
- Never cited skills (for cleanup)

**REQ-USAGE-005** (SHOULD): Citation deduplication SHOULD prevent multiple citations of same skill in same context

### 5.6 Skill Suggestions (P3)

**REQ-SUGGEST-001** (MUST): `suggest_skills` tool MUST analyze task description and return relevant skills

**REQ-SUGGEST-002** (SHOULD): Tool SHOULD accept:
- `task`: Free-text task description
- `files_affected`: List of file paths (optional)
- `operations_planned`: List of operations agent plans (optional)

**REQ-SUGGEST-003** (MUST): Response MUST include:
- `suggestions`: List of skills with relevance (high/medium/low) and reason
- `warnings`: List of detected raw command violations

**REQ-SUGGEST-004** (SHOULD): Suggestions SHOULD be ranked by:
1. Exact capability match (e.g., task mentions "PR comment" → `Post-PRCommentReply.ps1`)
2. Category match (e.g., task involves linting → all linting skills)
3. Keyword overlap (task tokens match skill tokens)

**REQ-SUGGEST-005** (MAY): Suggestions MAY be cached in Serena memory `skill-suggestions-cache` for performance

### 5.7 Resources (P1)

**REQ-RESOURCE-001** (MUST): `skills://catalog` resource MUST return full skill catalog

**REQ-RESOURCE-002** (MUST): `skills://categories` resource MUST return category hierarchy with counts

**REQ-RESOURCE-003** (SHOULD): `skills://usage` resource SHOULD return usage analytics

**REQ-RESOURCE-004** (MAY): `skills://suggestions` resource MAY return context-aware suggestions for current task

---

## 6. Technical Requirements

### 6.1 Architecture

**TECH-001** (MUST): MCP MUST be implemented as TypeScript MCP server

**TECH-002** (MUST): MCP MUST integrate with Serena MCP via `mcp__serena__*` tools

**TECH-003** (SHOULD): MCP SHOULD use Model Context Protocol SDK v1.0+

**TECH-004** (MUST): All file paths MUST be absolute, not relative

### 6.2 Index Building

**TECH-005** (MUST): Index builder MUST parse:
- **SKILL.md** frontmatter (name, description, allowed-tools)
- **PowerShell scripts** (parameters via `param()` block, synopsis via comment-based help)
- **Agent skills markdown** (YAML-like structure with id, statement, evidence)

**TECH-006** (MUST): Tokenization MUST split on:
- Whitespace
- Camelcase boundaries (`GetPRContext` → `Get`, `PR`, `Context`)
- Hyphens and underscores

**TECH-007** (SHOULD): Index rebuild SHOULD complete in <5 seconds for 50 skills

**TECH-008** (MUST): Index MUST detect and resolve duplicate skill IDs (error if duplicate)

### 6.3 Search Performance

**TECH-009** (MUST): Search MUST return results in <500ms for index of 50 skills

**TECH-010** (SHOULD): Search SHOULD use in-memory index for performance

**TECH-011** (MAY): Search MAY implement caching for repeated queries

### 6.4 Serena Integration

**TECH-012** (MUST): MCP MUST use Serena memories for persistence:

| Memory Name | Content | Format |
|-------------|---------|--------|
| `skill-catalog-index` | Full skill index | JSON in markdown code block |
| `skill-usage-citations` | Citation history | Markdown table |
| `skill-suggestions-cache` | Recent suggestions | JSON in markdown code block |

**TECH-013** (SHOULD): Index refresh SHOULD check Serena memory first, rebuild only if stale

**TECH-014** (MUST): Staleness MUST be determined by:
- Memory age >24 hours, OR
- File modification time newer than index `built_at` timestamp

### 6.5 Error Handling

**TECH-015** (MUST): All tools MUST return structured errors with:
- `error`: Boolean
- `code`: Error code (NOT_FOUND, PARSE_ERROR, SERENA_ERROR)
- `message`: Human-readable error description

**TECH-016** (SHOULD): Parse errors in skill files SHOULD log warning but not fail index build

**TECH-017** (MUST): Serena MCP failures MUST degrade gracefully (rebuild index in-memory, skip citations)

### 6.6 Session State MCP Integration (P2)

**TECH-018** (SHOULD): If Session State MCP is available, MCP SHOULD:
- Invoke `check_skill_exists` during `SKILL_VALIDATION` phase
- Record skill citations in session evidence
- Include skill usage in session summary

**TECH-019** (MAY): Session State MCP MAY expose skill violations as blocker in `validate_session_end`

---

## 7. Success Metrics

### 7.1 Primary Metrics

| Metric | Baseline (Session 15) | Target (Post-MCP) | Measurement |
|--------|----------------------|-------------------|-------------|
| **Skill Violations** | 5+ per session | 0 per session | Count of raw `gh` commands when skill exists |
| **Skill Discovery Time** | ~5 min (manual search) | <30 sec (search tool) | Time from task to finding skill |
| **Skill Citation Rate** | 0% (no tracking) | >80% of skill uses | Citations / total skill invocations |

### 7.2 Secondary Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Search Precision** | >90% relevant in top 5 | User feedback on search results |
| **Index Rebuild Time** | <5 sec for 50 skills | CI pipeline measurement |
| **Search Response Time** | <500ms | Tool invocation latency |
| **False Positive Blocks** | <5% of validations | Manual review of blocked commands |

### 7.3 Qualitative Metrics

**Skill Effectiveness**:
- Most cited skills → High-value, maintain and extend
- Never cited skills → Candidates for deprecation or documentation improvement
- High `outcome: failure` rate → Skill needs debugging

**Agent Satisfaction**:
- Reduction in "I didn't know that skill existed" feedback
- Increase in skill reuse vs. inline code

---

## 8. Risks & Mitigations

### 8.1 Risk: Index Staleness

**Description**: Index doesn't reflect newly added skills or skill modifications

**Likelihood**: Medium
**Impact**: High (agents use outdated skill list)

**Mitigation**:
1. File watcher triggers index rebuild on skill directory changes (P1)
2. 24-hour TTL forces periodic refresh
3. Manual rebuild command for emergencies

### 8.2 Risk: False Positive Blocking

**Description**: `check_skill_exists` blocks legitimate raw commands where skill doesn't fit

**Likelihood**: Medium
**Impact**: Medium (agent workflow disruption)

**Mitigation**:
1. Capability map only blocks exact matches (e.g., `gh pr view` blocked, `gh pr view --json customField` not blocked)
2. Override mechanism: Agent explains why skill doesn't fit, proceeds with warning
3. Feedback loop: Log false positives for capability map refinement

### 8.3 Risk: Performance Degradation

**Description**: Search/validation adds latency to agent workflows

**Likelihood**: Low
**Impact**: Medium (slower agent responses)

**Mitigation**:
1. In-memory index cache
2. <500ms response time SLO
3. Parallel execution (don't block on citation recording)

### 8.4 Risk: Parsing Failures

**Description**: Malformed skill files break index build

**Likelihood**: Medium
**Impact**: Low (one bad file shouldn't break catalog)

**Mitigation**:
1. Graceful degradation: Log error, skip file, continue indexing
2. Pre-commit validation: Lint skill files before merge
3. Schema validation: Detect missing required fields early

### 8.5 Risk: Serena MCP Dependency

**Description**: Serena MCP unavailable → no persistence, no index

**Likelihood**: Low
**Impact**: Medium (loss of citations, must rebuild index)

**Mitigation**:
1. In-memory fallback mode (index works without persistence)
2. File-based persistence fallback (write to `.agents/.skill-catalog-index.json`)
3. Detect Serena unavailability and log warning

---

## 9. Dependencies

### 9.1 Hard Dependencies

**DEP-001** (MUST): Serena MCP for index persistence and citation storage

**DEP-002** (MUST): Node.js v18+ for TypeScript MCP runtime

**DEP-003** (MUST): Access to `.claude/skills/` and `.agents/skills/` directories

### 9.2 Soft Dependencies

**DEP-004** (SHOULD): Session State MCP Phase 1.5 for `SKILL_VALIDATION` phase integration

**DEP-005** (SHOULD): File system watcher (e.g., `chokidar`) for auto-refresh on skill file changes

**DEP-006** (MAY): Agent Orchestration MCP for pre-delegation skill suggestions

### 9.3 Reverse Dependencies (What Depends on This)

**DEP-007**: Session State MCP Phase 1.5 `SKILL_VALIDATION` phase

**DEP-008**: QA agent for session-end validation

**DEP-009**: Retrospective agent for skill effectiveness analysis

---

## 10. Implementation Phases

### Phase 0: Foundation (P0) - Week 1

**Deliverables**:
- TypeScript MCP server scaffold
- Serena MCP integration (read/write memories)
- Basic index schema and builder

**Acceptance Criteria**:
- `buildIndex()` parses `.claude/skills/github/SKILL.md` and scripts
- Index written to Serena memory `skill-catalog-index`
- Index JSON schema validated

**Blockers**: None

---

### Phase 1: Core Catalog (P0) - Week 2

**Deliverables**:
- `search_skills` tool with relevance scoring
- `get_skill` tool for full retrieval
- `skills://catalog` resource
- `skills://categories` resource

**Acceptance Criteria**:
- Search for "pr comment" returns `Post-PRCommentReply.ps1`
- Search for "lint" returns all `Skill-Lint-*` skills
- `get_skill(id="github/pr/Get-PRContext")` returns full definition with parameters

**Blockers**: Phase 0 complete

**Testing**:
- Unit tests for search scoring
- Integration test with real skill files

---

### Phase 2: Validation Gate (P1) - Week 3

**Deliverables**:
- `check_skill_exists` tool
- Capability map for GitHub operations
- `validate_no_raw_commands` tool
- Session State MCP Phase 1.5 integration

**Acceptance Criteria**:
- `check_skill_exists(operation="gh", subcommand="pr view")` returns `blocking: true`
- Session State MCP invokes validation during `SKILL_VALIDATION` phase
- QA agent can query blocked commands in session

**Blockers**: Session State MCP Phase 1.5

**Testing**:
- Test all capability map entries
- Test false positive handling (unmapped subcommands)

---

### Phase 3: Usage Tracking (P2) - Week 4

**Deliverables**:
- `cite_skill` tool
- `skills://usage` resource with analytics
- Session State MCP citation integration

**Acceptance Criteria**:
- `cite_skill(skill_id="Skill-Lint-001", context="Running markdownlint")` persists to Serena
- `skills://usage` shows citation count per skill
- Session log includes skill citations

**Blockers**: Phase 1 complete

**Testing**:
- Citation deduplication
- Analytics accuracy (most cited, never cited)

---

### Phase 4: Smart Suggestions (P3) - Week 5-6

**Deliverables**:
- `suggest_skills` tool with context analysis
- `skills://suggestions` resource
- Orchestrator integration for pre-delegation suggestions

**Acceptance Criteria**:
- `suggest_skills(task="Address PR comments")` returns `Post-PRCommentReply.ps1` as high relevance
- Detects raw `gh` commands in `operations_planned` and warns
- Suggestions cached for performance

**Blockers**: Phase 1 complete

**Testing**:
- Relevance ranking accuracy
- Warning detection (raw command patterns)

---

## 11. Open Questions

### Q1: Index Refresh Strategy

**Question**: How should we trigger index rebuilds?

**Options**:
1. **On-demand**: Rebuild on first search after staleness detected
2. **Background**: File watcher triggers rebuild on skill file changes
3. **Periodic**: Cron-style rebuild every N hours

**Recommendation**: Hybrid - file watcher for dev, 24hr TTL for prod

**Decision needed by**: Phase 1 start

---

### Q2: Skill Versioning

**Question**: Should skills have version numbers? How do we handle breaking changes?

**Options**:
1. **Git-based**: Skills versioned via git SHA
2. **Explicit**: Add `version` field to skill metadata
3. **None**: Breaking changes update in-place, citations reference point-in-time

**Recommendation**: Git-based versioning (current practice), citations include git SHA

**Decision needed by**: Phase 3 (usage tracking)

---

### Q3: Capability Map Maintenance

**Question**: Who maintains the capability map? How do we keep it in sync with new skills?

**Options**:
1. **Manual**: Developer updates map when adding skill
2. **Auto-detected**: Parse skill metadata for `replaces_command` field
3. **Generated**: Script parses PowerShell scripts for `gh` command equivalents

**Recommendation**: Auto-detected via `replaces_command` metadata field in SKILL.md

**Decision needed by**: Phase 2 start

**Example**:
```yaml
# In .claude/skills/github/SKILL.md
capabilities:
  - id: github/pr/Get-PRContext
    replaces_command: "gh pr view"
    required_params: ["PullRequest"]
```

---

### Q4: Multi-Repository Support

**Question**: Should Skill Catalog MCP support indexing skills from external repositories?

**Use Case**: Team has shared skills in separate org repo

**Options**:
1. **Single repo only**: Index only current project skills
2. **Multi-repo**: Configure additional skill sources in MCP config
3. **Plugin model**: Skills can be npm packages

**Recommendation**: Phase 1 single-repo, Phase 5+ multi-repo via config

**Decision needed by**: Phase 0 (impacts architecture)

---

### Q5: Skill Deprecation

**Question**: How do we handle deprecated skills?

**Options**:
1. **Hard delete**: Remove from index
2. **Soft delete**: Mark as deprecated, exclude from search by default
3. **Redirect**: Point to replacement skill

**Recommendation**: Soft delete with redirect to replacement

**Example**:
```json
{
  "id": "github/pr/Get-PRInfo",
  "deprecated": true,
  "replaced_by": "github/pr/Get-PRContext",
  "deprecation_date": "2025-11-01"
}
```

**Decision needed by**: Phase 3 (usage tracking will surface unused skills)

---

## 12. Appendix A: Skill Structure Examples

### A.1 Executable Skill (PowerShell)

**File**: `.claude/skills/github/scripts/pr/Get-PRContext.ps1`

```powershell
<#
.SYNOPSIS
Get PR metadata, diff, and changed files

.PARAMETER PullRequest
PR number (required)

.PARAMETER Owner
Repository owner (auto-detected if omitted)

.PARAMETER Repo
Repository name (auto-detected if omitted)

.PARAMETER IncludeChangedFiles
Include list of changed files

.EXAMPLE
pwsh Get-PRContext.ps1 -PullRequest 50 -IncludeChangedFiles

.OUTPUTS
JSON object with PR metadata
#>

param(
    [Parameter(Mandatory)]
    [int]$PullRequest,

    [string]$Owner,
    [string]$Repo,
    [switch]$IncludeChangedFiles
)

# Implementation...
```

**Index Entry**:
```json
{
  "id": "github/pr/Get-PRContext",
  "type": "executable",
  "category": "github",
  "name": "Get PR Context",
  "statement": "Get PR metadata, diff, and changed files",
  "location": "/home/richard/ai-agents/.claude/skills/github/scripts/pr/Get-PRContext.ps1",
  "script_path": "scripts/pr/Get-PRContext.ps1",
  "parameters": [
    { "name": "PullRequest", "type": "int", "required": true },
    { "name": "Owner", "type": "string", "required": false },
    { "name": "Repo", "type": "string", "required": false },
    { "name": "IncludeChangedFiles", "type": "switch", "required": false }
  ],
  "search_tokens": ["get", "pr", "context", "metadata", "diff", "files"]
}
```

### A.2 Learned Skill (Markdown)

**File**: `.agents/skills/linting.md`

```markdown
## Skill-Lint-001: Autofix Before Manual Edits

- **Statement**: Run `markdownlint --fix` before manual edits to auto-resolve spacing violations
- **Context**: Large-scale markdown linting with 100+ files
- **Atomicity**: 95%
- **Evidence**: 2025-12-13 markdown linting - auto-fixed 800+ MD031/MD032/MD022 spacing errors instantly
- **Impact**: Reduced manual edit effort by 60%
- **Tags**: helpful, high-impact
```

**Index Entry**:
```json
{
  "id": "Skill-Lint-001",
  "type": "learned",
  "category": "linting",
  "name": "Autofix Before Manual Edits",
  "statement": "Run markdownlint --fix before manual edits to auto-resolve spacing violations",
  "location": "/home/richard/ai-agents/.agents/skills/linting.md",
  "atomicity": 95,
  "evidence": "2025-12-13 markdown linting - auto-fixed 800+ MD031/MD032/MD022 spacing errors instantly",
  "impact": "Reduced manual edit effort by 60%",
  "tags": ["helpful", "high-impact"],
  "search_tokens": ["autofix", "markdownlint", "fix", "manual", "edits", "spacing", "violations"]
}
```

---

## 13. Appendix B: Evidence from Session 15

### B.1 Violation Examples

**Violation 1**: Raw `gh pr view` instead of `Get-PRContext.ps1`

```bash
# What agent wrote:
gh pr view 50 --json title,body,files

# Should have been:
pwsh .claude/skills/github/scripts/pr/Get-PRContext.ps1 -PullRequest 50 -IncludeChangedFiles
```

**Violation 2**: Raw `gh pr comment` instead of `Post-PRCommentReply.ps1`

```bash
# What agent wrote:
gh pr comment 50 --body "Fixed in commit abc123"

# Should have been:
pwsh .claude/skills/github/scripts/pr/Post-PRCommentReply.ps1 -PullRequest 50 -Body "Fixed in commit abc123"
```

**Violation 3**: Inline `gh issue edit --add-label` instead of `Set-IssueLabels.ps1`

```bash
# What agent wrote:
gh issue edit 123 --add-label "bug" --add-label "P1"

# Should have been:
pwsh .claude/skills/github/scripts/issue/Set-IssueLabels.ps1 -Issue 123 -Labels @("bug") -Priority "P1"
```

### B.2 Root Cause Analysis

From `.serena/memories/skill-usage-mandatory.md`:

**Why agents keep using raw `gh`**:

1. **Habit**: Default to inline bash/PowerShell scripts
2. **Not checking first**: Don't verify if skill exists before writing code
3. **Ignoring user corrections**: Pattern repeats despite feedback
4. **Lack of discipline**: Even after being corrected, reverting to old patterns

**The Process** (from enforcement memory):

Before Writing ANY GitHub Operation:

1. **CHECK**: Does `.claude/skills/github/` have this capability?
2. **USE**: If exists, use the skill script
3. **EXTEND**: If missing, add to skill (don't write inline)

**Enforcement**:

> User will reject PRs/commits that:
> - Use raw `gh` commands when skill exists
> - Write inline scripts duplicating skill functionality
> - Ignore this guidance after being corrected

### B.3 Why Blocking Gate is Necessary

**Trust-based enforcement failed**:
- Serena memory `skill-usage-mandatory` exists
- User gave explicit corrections in Session 15
- Violations still occurred 5+ times

**Verification-based gates succeed**:
- Pre-commit hooks catch linting violations
- TypeScript compiler prevents type errors
- **Skill Catalog MCP validation will prevent skill violations**

**Analogy**: We don't trust developers to remember to run tests. CI blocks merge if tests fail. Similarly, we shouldn't trust agents to remember to check skills. MCP blocks execution if skill exists.

---

## 14. References

- [ADR-012: Skill Catalog MCP](../architecture/ADR-012-skill-catalog-mcp.md)
- [Technical Specification](../specs/skill-catalog-mcp-spec.md)
- [skill-usage-mandatory](../../.serena/memories/skill-usage-mandatory.md)
- [Session 15 Retrospective](../retrospective/2025-12-18-session-15.md)
- [.claude/skills/github/SKILL.md](../../.claude/skills/github/SKILL.md)
- [.agents/skills/linting.md](../../.agents/skills/linting.md)
- [ADR-005: PowerShell-Only Scripting](../architecture/ADR-005-powershell-only-scripting.md)
- [ADR-006: Thin Workflows, Testable Modules](../architecture/ADR-006-thin-workflows-testable-modules.md)
- [ADR-011: Session State MCP](../architecture/ADR-011-session-state-mcp.md)

---

*PRD Version: 1.0.0*
*Last Updated: 2025-12-21*
*Status: Draft - Awaiting Critic Review*

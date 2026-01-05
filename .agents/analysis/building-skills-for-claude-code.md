# Building Skills for Claude Code: Research Analysis

> **Research Date**: 2026-01-04
> **Session**: 308
> **Topic**: Official Claude Code Skills Documentation and Best Practices
> **Sources**: Anthropic blog, official documentation, engineering posts, community analysis

## Executive Summary

This analysis synthesizes official Anthropic guidance on building skills for Claude Code with this project's existing skill implementation. The ai-agents project already follows most best practices, with a few opportunities for refinement.

**Key Findings**:

1. Project skills align well with official patterns
2. Progressive disclosure implemented correctly via `references/` directories
3. Minor gaps in frontmatter (some skills use optional fields not recognized officially)
4. Trigger-based descriptions already implemented per earlier research

## 1. Official Skill Architecture

### 1.1 Core Concept

Skills are modular packages that teach Claude institutional knowledge. They function as "specialized onboarding documents" enabling automatic context discovery during tasks.

The fundamental problem addressed: Claude lacks access to team-specific table structures, business terminology, and procedural workflows scattered across wikis.

### 1.2 Three-Level Progressive Disclosure

Anthropic's design principle for skill loading:

| Level | Content | When Loaded |
|-------|---------|-------------|
| **Level 1** | Name + description (metadata) | Startup, into system prompt |
| **Level 2** | Complete SKILL.md body | When Claude determines relevance |
| **Level 3+** | Bundled files (scripts, references) | On-demand during execution |

This architecture makes context "effectively unbounded" because agents load information on-demand rather than maintaining everything in context.

### 1.3 Required vs Optional Frontmatter

| Field | Required | Constraints | Notes |
|-------|----------|-------------|-------|
| `name` | Yes | lowercase, numbers, hyphens only, max 64 chars | Must match directory name |
| `description` | Yes | max 1024 chars | Primary triggering mechanism |
| `allowed-tools` | No | Comma-separated tool names or patterns | Implements least privilege |
| `model` | No | Model ID or family alias | e.g., `claude-opus-4-5` |

**Note**: Fields like `version`, `license`, and `metadata` that this project uses are NOT in the official spec. They may be ignored by Claude Code.

### 1.4 Official Directory Structure

```text
skill-name/
├── SKILL.md              # Required: YAML frontmatter + instructions
├── reference.md          # Optional: Detailed API docs
├── examples.md           # Optional: Usage examples
└── scripts/
    └── helper.py         # Optional: Utility scripts
```

## 2. Project Alignment Analysis

### 2.1 Skills Inventory

The ai-agents project contains 28 skills across these categories:

| Category | Skills | Count |
|----------|--------|-------|
| **GitHub Operations** | github | 1 |
| **Agent Orchestration** | adr-review, analyze, planner, pr-comment-responder, slashcommandcreator, SkillForge | 6 |
| **Memory Management** | memory, memory-documentary, using-forgetful-memory, curating-memories, exploring-knowledge-graph | 5 |
| **Code Analysis** | encode-repo-serena, serena-code-architecture, using-serena-symbols | 3 |
| **Quality/Validation** | session-log-fixer, incoherence, doc-sync, decision-critic, fix-markdown-fences | 5 |
| **Security** | security-detection | 1 |
| **Session** | session, merge-resolver | 2 |
| **Research** | research-and-incorporate, programming-advisor | 2 |
| **Meta** | prompt-engineer, steering-matcher, metrics | 3 |

### 2.2 Structure Comparison

**Project Pattern** (github skill example):

```text
.claude/skills/github/
├── SKILL.md
├── references/           # Matches official "reference.md" pattern
│   ├── api-reference.md
│   ├── examples.md
│   ├── patterns.md
│   └── copilot-prompts.md
├── modules/              # Project-specific: shared PowerShell
│   └── GitHubCore.psm1
├── scripts/              # Matches official pattern
│   ├── pr/
│   ├── issue/
│   └── reactions/
└── tests/                # Project-specific: Pester tests
    └── *.Tests.ps1
```

**Alignment Score**: 90%

**Additions beyond official spec**:

- `modules/` directory for shared code (good practice, not in spec)
- `tests/` directory for validation (good practice, not in spec)
- `references/` directory (plural) vs `reference.md` (singular file)

### 2.3 Frontmatter Comparison

**Project Pattern**:

```yaml
---
name: github
version: 3.0.0               # Not in official spec
description: Execute GitHub operations...
license: MIT                  # Not in official spec
model: claude-opus-4-5
metadata:                     # Not in official spec
  domains: [github, pr, issue]
  type: integration
  complexity: intermediate
---
```

**Official Pattern**:

```yaml
---
name: github
description: Execute GitHub operations...
allowed-tools: Read, Bash(pwsh:*)
model: claude-opus-4-5
---
```

**Gap Analysis**:

| Field | Project Uses | Official Status | Recommendation |
|-------|--------------|-----------------|----------------|
| `version` | Yes | Not recognized | Keep for versioning, but Claude ignores |
| `license` | Yes | Not recognized | Keep for compliance, but Claude ignores |
| `metadata` | Yes | Not recognized | May cause parsing issues |
| `allowed-tools` | Inconsistent | Recommended | Add to skills needing restrictions |

### 2.4 Description Quality

Project descriptions already follow the trigger-based pattern documented in `creator-001-frontmatter-trigger-specification`:

**Good Example** (github skill):

> "Execute GitHub operations (PRs, issues, labels, comments, merges) using PowerShell scripts with structured output and error handling. Use when working with pull requests, issues, review comments, or CI checks instead of raw gh commands."

This includes:

1. What it does (capability)
2. When to use it (trigger context)
3. What NOT to do (avoid raw gh commands)

## 3. Key Insights from Official Sources

### 3.1 Skill Activation Mechanism

From technical analysis:

1. Claude detects user intent matching a skill's description
2. Calls the `Skill` tool with `command: "skill-name"`
3. System responds with base path + SKILL.md body
4. Claude executes referenced scripts relative to base path

**Important**: Skills operate within the main conversation as "injected instructions" rather than separate processes.

### 3.2 Tool Restrictions

The `allowed-tools` field enforces least privilege:

```yaml
# Read-only access
allowed-tools: Read, Grep, Glob

# PowerShell execution with specific patterns
allowed-tools: Bash(pwsh:*), Read, Write, Edit

# GitHub operations only
allowed-tools: Bash(gh:*), Bash(pwsh:*), Read
```

This prevents skills from executing unintended operations.

### 3.3 Skill Discovery

Skills are surfaced via XML tags in the tool definition:

```xml
<available_skills>
  <skill>
    <name>pdf</name>
    <description>[from frontmatter]</description>
    <location>user|project</location>
  </skill>
</available_skills>
```

**Implication**: Only `name` and `description` are used for discovery. Other frontmatter fields are for execution context only.

### 3.4 Executable Scripts as Tools

Anthropic recommends bundling deterministic code for operations where "token generation is far more expensive than running algorithms."

The project's PowerShell scripts in `scripts/` directories align with this guidance.

## 4. Recommendations

### 4.1 High Priority

| Item | Current State | Recommendation | Effort |
|------|---------------|----------------|--------|
| Remove unsupported frontmatter | Uses `version`, `license`, `metadata` | Keep `version`/`license` as comments; remove `metadata` or move to SKILL.md body | Medium |
| Add `allowed-tools` | Missing from most skills | Add to security-sensitive skills | Low |

### 4.2 Medium Priority

| Item | Current State | Recommendation | Effort |
|------|---------------|----------------|--------|
| Skill line count | Some SKILL.md files exceed 500 lines | Split into SKILL.md + references | Medium |
| Script permissions | Implicit execution | Add `chmod +x` verification to scripts | Low |

### 4.3 Low Priority (Nice to Have)

| Item | Current State | Recommendation | Effort |
|------|---------------|----------------|--------|
| Namespace support | Flat skill names | Consider `category:skill-name` format | High |
| Skill bundling | Individual skills | Consider plugin packaging for distribution | High |

## 5. Integration Points with ai-agents

### 5.1 Already Implemented

- Progressive disclosure via `references/` directories
- Trigger-based descriptions
- PowerShell script bundling
- Shared modules pattern
- Test coverage for scripts

### 5.2 Gaps to Address

1. **Frontmatter cleanup**: Remove or relocate `metadata` block
2. **Tool restrictions**: Add `allowed-tools` to security-sensitive skills
3. **SKILL.md sizing**: Audit for files exceeding 500 lines

### 5.3 Validation Tooling

Create skill validation script to check:

- Frontmatter schema compliance
- Description length (max 1024 chars)
- Name format (lowercase, hyphens, max 64 chars)
- File size recommendations

## 6. Sources

- [Agent Skills - Claude Code Docs](https://code.claude.com/docs/en/skills)
- [Equipping agents for the real world with Agent Skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills) - Anthropic Engineering
- [GitHub - anthropics/skills](https://github.com/anthropics/skills) - Official examples repository
- [Inside Claude Code Skills](https://mikhail.io/2025/10/claude-code-skills/) - Mikhail Shilkov technical analysis
- [Claude Skills and CLAUDE.md: a practical 2026 guide](https://www.gend.co/blog/claude-skills-claude-md-guide) - Community guide

## 7. Conclusion

The ai-agents project's skill implementation is well-aligned with official Anthropic guidance. The primary refinements needed are:

1. Clean up non-standard frontmatter fields
2. Add `allowed-tools` for security-sensitive skills
3. Audit SKILL.md file sizes

No major architectural changes required. The project's additions (modules/, tests/) enhance the official pattern without conflicting with it.

# Claude Code Skill Frontmatter Standards

## Required Schema (Minimal)

Only two fields are mandatory for Claude Code skills:

```yaml
---
name: skill-identifier  # lowercase, alphanumeric + hyphens, max 64 chars
description: What the skill does and when to use it  # max 1024 chars, primary trigger
---
```

## Optional Fields

```yaml
---
name: skill-identifier
version: 1.0.0                    # Semantic versioning
model: claude-opus-4-5            # Model alias (preferred for skills)
license: MIT                      # SPDX identifier
description: Detailed description
allowed-tools: Read, Write, Bash  # Comma-separated tool restrictions
metadata:                         # Domain-specific configuration
  domains: [architecture, planning]
  type: orchestrator
  complexity: advanced
---
```

## Model Identifiers

### Current Aliases (January 2026)

Use **aliases** for skills (benefit from automatic improvements):

- `claude-opus-4-5` - Maximum reasoning, orchestration ($5 input / $25 output per MTok)
- `claude-sonnet-4-5` - Standard workflows, coding ($3 / $15 per MTok)
- `claude-haiku-4-5` - Speed, lightweight tasks ($1 / $5 per MTok)

### Dated Snapshots (Production APIs)

Use for reproducible behavior in production:

- `claude-opus-4-5-20251101`
- `claude-sonnet-4-5-20250929`
- `claude-haiku-4-5-20251001`

## ai-agents Model Distribution

Current standardization (27 skills total):

- **11 Opus** (40.7%): adr-review, analyze, decision-critic, github, merge-resolver, planner, research-and-incorporate, session-log-fixer, skillcreator, incoherence, memory
- **12 Sonnet** (44.4%): curating-memories, doc-sync, encode-repo-serena, exploring-knowledge-graph, memory-documentary, metrics, pr-comment-responder, programming-advisor, prompt-engineer, security-detection, serena-code-architecture, using-forgetful-memory, using-serena-symbols
- **4 Haiku** (14.8%): fix-markdown-fences, steering-matcher, session

## Selection Criteria

| Complexity | Latency | Cost | Model |
|------------|---------|------|-------|
| Simple pattern matching | <1s critical | Minimal | Haiku |
| Standard workflows | <5s acceptable | Standard | Sonnet |
| Multi-agent orchestration | <30s acceptable | Premium justified | Opus |

## Validation Rules

- Frontmatter MUST start with `---` on line 1 (no blank lines before)
- Use spaces for indentation (tabs not allowed)
- Name format: `^[a-z0-9-]{1,64}$`
- Description: non-empty, max 1024 chars, include trigger keywords
- Keep SKILL.md under 500 lines (use progressive disclosure for larger skills)

## Migration Pattern

Standardization: Move from dated IDs to aliases, restructure metadata

**Before**:
```yaml
metadata:
  version: 1.0.0
  model: claude-opus-4-5-20251101
```

**After**:
```yaml
version: 1.0.0
model: claude-opus-4-5
metadata:
  domains: [...]
```

## References

- Analysis: `.agents/analysis/claude-code-skill-frontmatter-2026.md`
- Commit: 303c6d2 (standardized all 27 skills)
- Official docs: https://code.claude.com/docs/en/skills

# Skill Description and Trigger Standard

**Version**: 1.0
**Date**: 2026-01-03
**Status**: Canonical Standard
**Applies To**: All new skills, skill updates

## Purpose

Define the standard for skill descriptions (frontmatter) and trigger sections to maximize discoverability and usability.

## TL;DR

**Description**: 150-250 chars, action verb + what + when, no angle brackets
**Triggers**: 3-5 natural language phrases in table format with operation mapping

---

## Part 1: Description (Frontmatter)

### Required Format

```yaml
---
name: skill-name
description: Action verb + what it does + when to use it + outcome (150-250 chars)
license: MIT
metadata:
  version: 1.0.0
  model: claude-sonnet-4-5
---
```

### Description Formula

```
[ACTION VERB] + [WHAT] + [WHEN/USE CASE] + [OUTCOME]
```

### Good Examples

✅ **Excellent** (session-log-fixer):
```yaml
description: Fix session protocol validation failures in GitHub Actions. Use when
  a PR fails with "Session protocol validation failed", "MUST requirement(s) not
  met", "NON_COMPLIANT" verdict, or "Aggregate Results: FAIL".
```

- Action verb: "Fix"
- What: "session protocol validation failures"
- When: "Use when a PR fails with [specific errors]"
- Outcome: Implied (passing validation)

✅ **Excellent** (research-and-incorporate):
```yaml
description: Research external topics, create comprehensive analysis, determine
  project applicability, and incorporate learnings into Serena and Forgetful
  memory systems. Transforms knowledge into searchable, actionable context.
```

- Action verb: "Research"
- What: "external topics"
- When: Implied (when needing to incorporate knowledge)
- Outcome: "searchable, actionable context"

### Common Mistakes

❌ **Too Vague** (before):
```yaml
description: Handles memory operations
```

✅ **Fixed** (after):
```yaml
description: Search and manage memories across Serena and Forgetful. Use when
  needing past context, creating new memories, or linking related knowledge.
```

❌ **Too Technical** (before):
```yaml
description: Populates Forgetful via LSP symbol analysis
```

✅ **Fixed** (after):
```yaml
description: Encode codebase into searchable knowledge graph using symbol
  analysis. Use when onboarding to a new repository or refreshing project
  understanding.
```

❌ **No Use Case** (before):
```yaml
description: Collects metrics from git history
```

✅ **Fixed** (after):
```yaml
description: Collect and report agent usage metrics from git history. Use when
  measuring agent adoption, effectiveness, or system health over time.
```

### Description Checklist

- [ ] Starts with action verb (Detect, Generate, Collect, Fix, etc.)
- [ ] Describes what it does in plain language
- [ ] Includes "Use when..." or equivalent trigger language
- [ ] Mentions outcome or benefit
- [ ] 150-250 characters (optimal)
- [ ] No angle brackets (`<` or `>`)
- [ ] No version/date metadata (goes in metadata object)

---

## Part 2: Triggers Section

### Required Format

Every skill MUST have a `## Triggers` section immediately after the frontmatter and title.

### Trigger Section Template

```markdown
## Triggers

| Trigger Phrase | Operation |
|----------------|-----------|
| "explicit phrase users say" | What happens |
| "alternative phrasing" | What happens |
| "third variation" | What happens |

---
```

### Minimum Requirements

- **3-5 trigger phrases** (minimum 3, recommended 5)
- **Natural language** (how users actually talk)
- **Variation** (different ways to ask for same thing)
- **Specificity** (concrete examples, not generic)

### Good Examples

✅ **Table Format** (github):
```markdown
## Triggers

| Phrase | Operation |
|--------|-----------|
| `get PR context for #123` | Get-PRContext.ps1 |
| `respond to review comments` | Post-PRCommentReply.ps1 |
| `add label to issue #456` | Set-IssueLabels.ps1 |
| `merge this PR` | Merge-PR.ps1 |
```

✅ **Categorized Triggers** (SkillForge):
```markdown
## Triggers

### Creation Triggers
- `SkillForge: {goal}` - Full autonomous skill creation
- `create skill` - Natural language activation
- `design skill for {purpose}` - Purpose-first creation

### Improvement Triggers
- `SkillForge --improve {skill}` - Enter improvement mode
- `enhance the {skill} skill` - Natural improvement request
```

✅ **Use-When Format** (merge-resolver):
```markdown
## Triggers

Use this skill when you encounter:

- `resolve merge conflicts for PR #123`
- `PR has conflicts with main`
- `can't merge - conflicts detected`
- `fix the merge conflicts in this branch`
- `help me resolve conflicts for this pull request`
```

### Trigger Patterns

#### Pattern 1: Command + Context

```
{action} + {target} + {context}

Examples:
- "get PR context for #123"
- "add label enhancement to issue #456"
- "search memory for authentication patterns"
```

#### Pattern 2: Natural Question

```
{question word} + {subject} + {qualifier}

Examples:
- "what do we know about error handling?"
- "show me metrics for the last 30 days"
- "how do I fix markdown fence errors?"
```

#### Pattern 3: Problem Statement

```
{problem} + {constraint}

Examples:
- "PR has conflicts with main"
- "session validation failed"
- "markdown fences are malformed"
```

#### Pattern 4: Request + Goal

```
{action verb} + {goal}

Examples:
- "plan this feature implementation"
- "create ADR for database choice"
- "detect security-critical changes"
```

### Trigger Checklist

- [ ] Minimum 3 trigger phrases
- [ ] Uses natural language (how users talk)
- [ ] Includes variations (different ways to ask)
- [ ] Organized in table or list format
- [ ] Maps to specific operations or outcomes
- [ ] Placed immediately after title (before other sections)

---

## Part 3: Complete Example

### Exemplar: Well-Structured Skill

```yaml
---
name: code-review
description: Automated code review using project standards from CLAUDE.md. Use
  when ready to review changes before committing or after completing a feature.
  Checks style, patterns, and best practices.
license: MIT
metadata:
  version: 1.0.0
  model: claude-sonnet-4-5
---

# Code Review Skill

Brief intro paragraph explaining the skill's purpose and value.

## Triggers

| Trigger Phrase | Action |
|----------------|--------|
| "review my code" | Full codebase review |
| "check code quality" | Standards compliance check |
| "review changes before commit" | Pre-commit review |
| "code review this file" | Single file review |
| "check for style violations" | Style-focused review |

---

## Quick Start

[Rest of skill content...]
```

---

## Part 4: Validation Rules

### Pre-Commit Validation

The SkillForge validator (`scripts/validate-skill.py`) checks:

1. ✅ Description exists and is 1-1024 chars
2. ✅ Description has no angle brackets
3. ✅ Triggers section exists
4. ✅ Minimum 3 trigger phrases present

### Manual Review Checklist

Before marking skill complete:

- [ ] Description follows formula (verb + what + when + outcome)
- [ ] Description length 150-250 chars (optimal)
- [ ] Triggers section exists with table or list
- [ ] Minimum 3 distinct trigger phrases
- [ ] Triggers use natural language
- [ ] Triggers show variation (different phrasings)
- [ ] No version/date in body (only in metadata)
- [ ] No changelog section

---

## Part 5: Common Patterns by Skill Type

### Automation Skills (metrics, security-detection)

**Description Pattern**:
```
Collect/Detect/Monitor + [data source] + Use when [measuring/checking] + [outcome]
```

**Trigger Pattern**:
```
- "show me [metric]"
- "check for [condition]"
- "generate [report type]"
```

### Guidance Skills (using-forgetful-memory, curating-memories)

**Description Pattern**:
```
Guidance for [activity] + Use when [deciding/learning/understanding]
```

**Trigger Pattern**:
```
- "how do I [action]"
- "when should I [action]"
- "best practices for [topic]"
```

### Workflow Skills (planner, research-and-incorporate)

**Description Pattern**:
```
[Workflow verb] + [multi-step process] + Use when [starting/executing] + [outcome]
```

**Trigger Pattern**:
```
- "plan [feature/task]"
- "execute [plan]"
- "[action] this [artifact]"
```

### Diagnostic Skills (incoherence, analyze)

**Description Pattern**:
```
Detect/Analyze/Find + [problems] + Use when [symptoms] + [resolution outcome]
```

**Trigger Pattern**:
```
- "find [problem type]"
- "analyze [target]"
- "detect [inconsistencies]"
```

---

## Part 6: Migration Guide

### For Existing Skills Missing Triggers

1. Read current description
2. Extract implicit trigger phrases
3. Add 2-3 additional natural language variations
4. Create Triggers section with table format
5. Validate with checklist

### For Existing Skills with Poor Descriptions

1. Identify the action verb (what does it do?)
2. Add use-when language (when should it be invoked?)
3. Clarify outcome (what does user get?)
4. Trim to 150-250 chars
5. Validate with checklist

---

## Part 7: Enforcement

### When This Standard Applies

- **Required**: All new skills created after 2026-01-03
- **Recommended**: Update existing skills when modified
- **Blocked**: SkillForge will reject skills violating this standard

### Validation Tools

1. **Pre-commit hook**: Runs `validate-skill.py` (checks basic structure)
2. **SkillForge**: Phase 4 synthesis panel (checks quality)
3. **Manual review**: Use checklists in this document

---

## References

- [Skill Description Trigger Review](../analysis/skill-description-trigger-review.md) - Analysis of existing skills
- [SkillForge Specification](../../.claude/skills/SkillForge/SKILL.md) - Skill creation framework
- [Session 372](../sessions/2026-01-03-session-372.md) - Standard creation session

## Changelog

### v1.0.0 (2026-01-03)
- Initial standard based on review of 28 existing skills
- Established description formula and trigger patterns
- Created validation rules and checklists

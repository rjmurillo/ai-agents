# Skill Description and Trigger Clarity Review

**Date**: 2026-01-03
**Session**: 372
**Scope**: All 28 skills in `.claude/skills/`

## Executive Summary

Reviewed all skill descriptions and trigger sections for discoverability. Found 18 skills (64%) lacking explicit trigger sections, though many have implicit trigger language in descriptions.

### Key Findings

| Metric | Count | Percentage |
|--------|-------|------------|
| Total Skills | 28 | 100% |
| With Triggers Section | 9 | 32% |
| Without Triggers Section | 18 | 64% |
| Missing Description | 3 | 11% |

## Skills with Missing Descriptions

**Critical Issues** - These need immediate attention:

1. **github** - Empty description (has triggers section)
2. **merge-resolver** - Empty description (has triggers section)
3. **programming-advisor** - Empty description (no triggers section)

## Description Quality Analysis

### Excellent (Clear When/What/How)

Skills with exemplary descriptions that include trigger language:

| Skill | Description Strength |
|-------|---------------------|
| **session-log-fixer** | Includes exact error messages as triggers: "Session protocol validation failed", "MUST requirement(s) not met" |
| **doc-sync** | Lists explicit trigger phrases: "sync docs", "update CLAUDE.md files", "ensure documentation is in sync" |
| **fix-markdown-fences** | Clear use case: "when markdown files have closing fences with language identifiers" |
| **research-and-incorporate** | Strong action-oriented: "Research external topics, create comprehensive analysis, determine project applicability" |

### Good (Clear Purpose, Implicit Triggers)

Skills with solid descriptions but could benefit from explicit trigger section:

| Skill | Current State | Improvement Opportunity |
|-------|---------------|------------------------|
| **metrics** | Describes what (collect metrics) but not when | Add triggers like "show agent metrics", "generate usage report" |
| **incoherence** | Describes purpose but not invocation phrases | Add triggers like "detect incoherence", "find contradictions" |
| **security-detection** | Clear purpose, lacks user-facing triggers | Add triggers like "scan for security changes", "check security-critical files" |
| **planner** | Good use-when language but no explicit triggers | Add triggers like "plan this feature", "create implementation plan" |

### Needs Improvement

Skills with vague or incomplete descriptions:

| Skill | Issue | Recommendation |
|-------|-------|----------------|
| **encode-repo-serena** | Describes mechanism not use case | Add "when to use" language |
| **curating-memories** | Generic guidance language | Add specific memory curation trigger phrases |
| **steering-matcher** | Internal utility language | Clarify user-facing use cases |

## Trigger Section Analysis

### Excellent Trigger Sections

**SkillForge** - Multi-category triggers:
```
- Creation Triggers: "create skill", "design skill for X"
- Improvement Triggers: "improve skill", "enhance skill"
- Triage Triggers: "do I have a skill for X"
```

**github** - Operation-mapped table:
```
| Phrase | Operation |
|--------|-----------|
| "get PR context for #123" | Get-PRContext.ps1 |
| "respond to review comments" | Post-PRCommentReply.ps1 |
```

**memory** - Tier-mapped triggers:
```
| Trigger Phrase | Maps To |
|----------------|---------|
| "search memory for X" | Tier 1: Search-Memory.ps1 |
| "what do we know about X" | Tier 1: Search-Memory.ps1 |
```

### Common Patterns in Good Triggers

1. **Natural Language Variations**: Multiple phrasings for same operation
2. **Table Format**: Organized by operation or output
3. **Specific Examples**: Concrete phrases users might say
4. **Context Clues**: When to use each variation

## Recommendations by Priority

### P0 (Critical)

1. Add descriptions for github, merge-resolver, programming-advisor
2. Add trigger sections to top 5 most-used skills:
   - planner
   - security-detection
   - metrics
   - incoherence
   - analyze

### P1 (High Value)

3. Add trigger sections to skills with implicit triggers in descriptions:
   - doc-sync (already has phrases in description)
   - fix-markdown-fences (already has use-when language)
   - prompt-engineer (has clear use case)

### P2 (Quality Improvement)

4. Enhance descriptions for internal/utility skills to clarify user-facing value
5. Standardize trigger section format across all skills

## Metrics

### Description Lengths

| Range | Count | Skills |
|-------|-------|--------|
| 0 chars (missing) | 3 | github, merge-resolver, programming-advisor |
| 1-150 chars | 4 | encode-repo-serena, incoherence, session, using-serena-symbols |
| 151-250 chars | 15 | Most skills |
| 251+ chars | 6 | SkillForge, adr-review, curating-memories, doc-sync, planner, pr-comment-responder |

**Optimal Range**: 150-250 characters (covers what, when, how without verbosity)

### Trigger Section Presence

```
With Triggers:    9 skills (32%) ████████░░░░░░░░░░░░░░░░
Without Triggers: 18 skills (64%) ████████████████░░░░░░░░
Missing Desc:     3 skills (11%) ███░░░░░░░░░░░░░░░░░░░░░
```

## Next Steps

1. Create standard for skill descriptions and triggers (separate document)
2. Add missing descriptions (P0)
3. Add trigger sections to high-value skills (P0-P1)
4. Update skill-creator documentation with new standard

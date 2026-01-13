# Skill-Creator Best Practices Index

## Purpose

Index of atomic skill-creator patterns derived from PR #255 (2025-12-22). Use when creating or optimizing Claude Code skills.

## Quick Reference

| ID | Name | Category | Tokens Saved |
|----|------|----------|-------------|
| 001 | Frontmatter Trigger Specification | skill-creation | N/A (activation) |
| 002 | Token Efficiency via Comment Stripping | token-optimization | ~2,400 |
| 003 | Test Separation from Skill Directory | skill-structure | ~1,500 |
| 004 | Reference Material Extraction | progressive-disclosure | ~200 |
| 005 | Schema Redundancy Elimination | token-optimization | ~500 |
| 006 | TOC Requirement for Long Files | documentation | N/A (navigation) |
| 007 | Frontmatter Validation Compliance | validation | N/A (compliance) |

## Memory References

Read individual skills:

- [creator-001-frontmatter-trigger-specification](creator-001-frontmatter-trigger-specification.md)
- [creator-002-token-efficiency-comment-stripping](creator-002-token-efficiency-comment-stripping.md)
- [creator-003-test-separation-skill-directory](creator-003-test-separation-skill-directory.md)
- [creator-004-reference-material-extraction](creator-004-reference-material-extraction.md)
- [creator-005-schema-redundancy-elimination](creator-005-schema-redundancy-elimination.md)
- [creator-006-toc-requirement-long-files](creator-006-toc-requirement-long-files.md)
- [validation-007-frontmatter-validation-compliance](validation-007-frontmatter-validation-compliance.md)

## When to Use This Index

Use when:
- Creating a new Claude Code skill
- Reviewing skill for token optimization
- Organizing skill directory structure
- Writing skill documentation (SKILL.md)
- Writing skill frontmatter

## Total Token Impact

PR #255 demonstrated: **~4,600 tokens saved** from applying all patterns.

## Evidence

- PR #255: 8 atomic commits, +1105/-548 lines
- Session 65: Learning extraction and skill generation
- GitHub skill: `.claude/skills/github/`

## Activation Vocabulary

skill, creator, optimization, token, frontmatter, trigger, progressive disclosure, SKILL.md, comment stripping, test separation, reference extraction, schema redundancy, TOC, table of contents, validation, anthropic, metadata, compliance

## Created

2025-12-22

## Tag

skill-creator, index
# Agent Skills Open Standard Integration

**Date**: 2026-01-09
**Source**: agentskills.io
**Importance**: HIGH

## Summary

Agent Skills is an open, lightweight format for extending AI agent capabilities. Originally developed by Anthropic, it is now an industry standard supported by Claude Code, Gemini CLI, Cursor, VS Code, GitHub Copilot, and others.

## ai-agents Project Compatibility

**Status**: COMPLIANT with extensions

The ai-agents project skill system is compatible with the agentskills.io standard:

| Aspect | Standard | ai-agents | Status |
|--------|----------|-----------|--------|
| Directory structure | `SKILL.md`, `scripts/`, `references/`, `assets/` | Same + `modules/` | Compatible |
| Required fields | `name`, `description` | Same | Aligned |
| Name constraints | 64 chars, lowercase, hyphen-delimited | Same | Aligned |
| Description limit | 1024 chars | Same | Aligned |

## Project-Specific Extensions

The ai-agents project extends the standard with:

1. **`model` field**: Top-level field for Claude model selection (e.g., `claude-sonnet-4-5`)
2. **`version` field**: Semantic versioning at top level (standard uses `metadata.version`)
3. **`modules/` directory**: PowerShell .psm1 module support
4. **Domain metadata**: `domains`, `type`, `inputs`, `outputs` fields

## Standard Fields Not Yet Adopted

| Field | Purpose | Recommendation |
|-------|---------|----------------|
| `compatibility` | Environment requirements (max 500 chars) | Consider adopting |
| `allowed-tools` | Space-delimited tool permissions | Consider adopting |

## Validation

The standard provides a reference library:

```bash
# Validate skill compliance
skills-ref validate ./my-skill

# Generate prompt XML
skills-ref to-prompt ./skills/*
```

GitHub: https://github.com/agentskills/agentskills/tree/main/skills-ref

## Key Insight

The ai-agents project was an early adopter of the skill format. When creating or modifying skills, ensure compliance with both the open standard and project-specific extensions.

## References

- Analysis: `.agents/analysis/agentskills-io-standard-2026-01.md`
- Specification: https://agentskills.io/specification
- Example Skills: https://github.com/anthropics/skills
- Frontmatter Standards: [claude-code-skill-frontmatter-standards](claude-code-skill-frontmatter-standards.md) memory

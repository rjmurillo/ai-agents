# Skill Usage Mandatory

**Atomicity Score**: 95%
**Source**: CLAUDE.md Session Start requirement
**Date**: 2026-01-01
**ADR Reference**: ADR-007 Memory-First Architecture

## Statement

Before ANY GitHub operation (PR, issue, comment, workflow, etc.), check `.claude/skills/github/scripts/` for existing skills.

## Requirement

| Condition | Action |
|-----------|--------|
| Skill exists for operation | **MUST** use existing skill |
| Skill missing for operation | **MUST** add to skill library first, then use |
| Inline implementation | **PROHIBITED** - violates ADR-005, ADR-007 |

## Skill Locations

| Operation Type | Skill Directory |
|----------------|-----------------|
| PR operations | `.claude/skills/github/scripts/pr/` |
| Issue operations | `.claude/skills/github/scripts/issue/` |
| Reaction operations | `.claude/skills/github/scripts/reactions/` |
| Comment operations | `.claude/skills/github/scripts/comment/` |
| Workflow operations | `.claude/skills/github/scripts/workflow/` |

## Discovery Pattern

Before executing:
```powershell
Get-ChildItem -Path ".claude/skills/github/scripts" -Recurse -Filter "*.ps1"
```

## Enforcement

This memory MUST be read during Session Start per SESSION-PROTOCOL Phase 2.

**Verification**:
- Session log Evidence column must list this memory
- Validate-Session.ps1 cross-references memory names

**Violation Response**:
- Pre-commit hook warns on missing evidence
- CI validation fails if pattern violated

## Related

- ADR-005: PowerShell-Only Scripting Standard
- ADR-007: Memory-First Architecture
- SESSION-PROTOCOL.md Phase 2: Context Retrieval (BLOCKING)
- memory-index: Routes to this memory for GitHub operations

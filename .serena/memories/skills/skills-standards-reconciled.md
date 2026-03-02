# Skill Standards: Reconciled Authority

**Date**: 2026-01-09
**Document**: `.agents/architecture/SKILL-STANDARDS-RECONCILED.md`
**Status**: CANONICAL REFERENCE

## Summary

Comprehensive reconciliation of all skill knowledge from official standards (agentskills.io, claude.com), project ADRs, memory systems, and actual implementations. Resolves 5 major conflicts and establishes authoritative schema.

## Official Standard (Minimal)

**Required**: Only 2 fields
- `name`: Max 64 chars, lowercase+hyphens, matches directory
- `description`: Max 1024 chars, trigger mechanism

**Optional**: `license`, `compatibility` (500 chars), `metadata`, `allowed-tools` (space-delimited)

## ai-agents Extensions

**Additional Required**: `version` (semver), `model` (Claude alias), `license` (SPDX)

**Extended Metadata**: `subagent_model`, `domains`, `type`, `complexity`, `inputs`, `outputs`, `file_triggers`

**Extended Directories**: `modules/` (PowerShell .psm1), `templates/` (renamed from assets), `tests/` (Pester)

## Conflicts Resolved

### 1. version Field Placement
**Resolution**: TOP-LEVEL for ai-agents (SkillForge validator requirement)
**Rationale**: Semantic versioning is fundamental, not domain-specific

### 2. model Field Existence
**Resolution**: PROJECT-SPECIFIC EXTENSION
**Rationale**: Claude Code optimization, official spec is platform-agnostic

### 3. Required Fields Count
**Resolution**: TWO-TIER SYSTEM
- Official: 2 required (name, description) for portability
- ai-agents: 5 required (add version, license, model) for quality

### 4. allowed-tools Format
**Resolution**: SPACE-DELIMITED (official standard)
**Correction**: ADR-040 example showing comma-separated was incorrect

### 5. metadata.subagent_model vs Top-Level model
**Resolution**: BOTH, DIFFERENT PURPOSES
- `model`: Executes THIS skill
- `metadata.subagent_model`: Model for agents THIS skill delegates to (orchestrators only)

## Model Selection (ai-agents)

| Model | Cost | Use Case |
|-------|------|----------|
| claude-haiku-4-5 | $1/$5 | Speed, pattern matching, <1s |
| claude-sonnet-4-5 | $3/$15 | Standard workflows, <5s |
| claude-opus-4-5 | $5/$25 | Orchestration, reasoning, <30s |

Use **aliases** for auto-updates, **dated IDs** for deterministic behavior.

## Validation

**Official**: `skills-ref validate ./skill` (agentskills.io)
**ai-agents**: `python3 .claude/skills/SkillForge/scripts/validate-skill.py ./skill`

## Key Principle

The ai-agents project is 90% aligned with official standard but has project-specific extensions that must be clearly distinguished from the base specification.

## References

- Official spec: https://agentskills.io/specification
- Claude docs: https://code.claude.com/docs/en/skills
- ADR-040: `.agents/architecture/ADR-040-skill-frontmatter-standardization.md`
- Complete reconciliation: `.agents/architecture/SKILL-STANDARDS-RECONCILED.md`

## Related Memories

This memory supersedes fragmented skill knowledge in:
- claude-code-skill-frontmatter-standards
- agentskills-io-standard-integration
- Forgetful memories 99-110, 128-135, 167-174

## When to Use

Reference this memory when:
- Creating new skills
- Validating existing skills
- Resolving frontmatter conflicts
- Choosing model allocation
- Migrating between standards

## Related

- [skills-agent-workflow-index](skills-agent-workflow-index.md)
- [skills-analysis-index](skills-analysis-index.md)
- [skills-architecture-index](skills-architecture-index.md)
- [skills-autonomous-execution-index](skills-autonomous-execution-index.md)
- [skills-bash-integration-index](skills-bash-integration-index.md)

# Skill Description and Trigger Standard

**Version**: 2.0
**Date**: 2026-01-03
**Status**: Canonical Standard
**Applies To**: All new skills, skill updates

## Purpose

Maximize skill discoverability through excellent descriptions and efficient body structure.

---

## Core Principle

**The model selects skills based on description**. Description must be excellent. Body is lazy-loaded via progressive disclosure, so keep it concise and practical.

---

## Part 1: Description (Frontmatter)

### Requirements

Per Anthropic Claude Code specification:

- **Mandatory**: `name` and `description` only
- **Description is primary trigger**: Include trigger keywords for discoverability
- **Length**: 10+ words minimum (validator enforces), 150-250 chars recommended
- **Format**: Action verb + what + when + trigger keywords + outcome
- **No angle brackets**: `<` or `>` will fail validation

### Formula

```
[ACTION VERB] + [WHAT] + [WHEN WITH TRIGGER KEYWORDS] + [OUTCOME]
```

### Excellent Examples

**session-log-fixer**:
```yaml
description: Fix session protocol validation failures in GitHub Actions. Use when
  a PR fails with "Session protocol validation failed", "MUST requirement(s) not
  met", "NON_COMPLIANT" verdict, or "Aggregate Results: FAIL".
```

- Trigger keywords: exact error messages users will see
- When: explicit failure scenarios
- Outcome: implied (passing validation)

**research-and-incorporate**:
```yaml
description: Research external topics, create comprehensive analysis, determine
  project applicability, and incorporate learnings into Serena and Forgetful
  memory systems. Transforms knowledge into searchable, actionable context.
```

- What: research, analyze, incorporate
- Outcome: "searchable, actionable context"
- Trigger keywords: implicit in workflow verbs

### Common Mistakes

| Mistake | Why It Fails | Fix |
|---------|--------------|-----|
| "Handles memory operations" | No trigger keywords, vague | "Search and manage memories across Serena and Forgetful. Use when needing past context or creating new memories." |
| "Populates Forgetful via LSP" | Too technical, no when | "Encode codebase into searchable knowledge graph. Use when onboarding to repository or refreshing project understanding." |
| "Collects metrics" | No use case | "Collect agent usage metrics from git history. Use when measuring agent adoption or system health over time." |

---

## Part 2: Body Structure (Progressive Disclosure)

Body is lazy-loaded. Keep it concise and practical.

### Required Elements

1. **Trigger table or list** (phrase → operation mapping)
2. **Decision trees** (when to use vs alternatives)
3. **Anti-patterns** (what NOT to do)
4. **Verification checklists** (how to validate success)

### Optional Elements (use references/)

- Deep implementation details
- Advanced scenarios
- Historical context

### Trigger Table Format

Map user phrases to operations:

```markdown
## Triggers

| Trigger Phrase | Operation |
|----------------|-----------|
| "get PR context for #123" | Get-PRContext.ps1 |
| "respond to review comments" | Post-PRCommentReply.ps1 |
| "merge this PR" | Merge-PR.ps1 |
```

Or categorized lists:

```markdown
## Triggers

### Creation
- `create skill` - Natural language activation
- `design skill for {purpose}` - Purpose-first creation

### Improvement
- `improve {skill}` - Enter improvement mode
```

### Decision Trees

Show when to use this skill vs alternatives:

```markdown
## When to Use

Use this skill when:
- [ ] Condition A is true
- [ ] Condition B is present
- [ ] You need outcome X

Use alternative skill when:
- [ ] Condition C is true (use skill-Y instead)
```

### Anti-Patterns

Prevent common mistakes:

```markdown
## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Recreating from memory | Miss exact structure | Copy from template |
| Marking MUST as N/A | Validation fails | Provide justification |
| Placeholder evidence | Validators detect | Use real evidence text |
```

### Verification Checklist

Help users validate success:

```markdown
## Verification

After execution:
- [ ] Output file exists at expected path
- [ ] Validation script passes
- [ ] Commit includes all changes
- [ ] CI workflow triggered
```

---

## Part 3: Token Efficiency

### Progressive Disclosure Pattern

**Main SKILL.md**: Concise, practical, complete workflow

**references/ directory**: Deep dives, advanced scenarios, historical context

Example from adr-review:

```
SKILL.md (token-efficient):
- Quick Start
- Triggers table
- When to Use
- Anti-Patterns
- Verification checklist

references/:
- debate-protocol.md (detailed Phases 0-4)
- deletion-workflow.md (D1-D4 workflow)
- issue-resolution.md (P0/P1/P2 handling)
- artifacts.md (output formats)
```

### Concise Structure

| Section | Max Lines | Purpose |
|---------|-----------|---------|
| Triggers | 10-15 | Phrase mapping |
| When to Use | 5-10 | Decision criteria |
| Anti-Patterns | 5-10 | Common mistakes |
| Verification | 5-10 | Success checklist |

Deep content goes in `references/`.

---

## Part 4: Validation

### Pre-Commit Validation

The SkillForge validator (`.claude/skills/SkillForge/scripts/validate-skill.py`) checks:

1. ✅ Description exists (1-1024 chars)
2. ✅ Description has 10+ words
3. ✅ Description has no angle brackets
4. ✅ Frontmatter is valid YAML

**Note**: Validator checks WORD COUNT (10+ words), not character count. 150-250 chars is recommended for readability but not enforced.

### Security Requirements

Trigger phrases MUST use character whitelist: `[a-zA-Z0-9 \-:,.'"]`

Operation paths in trigger tables MUST:
- Be relative paths only (no `..`)
- Reference scripts in skill directory
- Not execute arbitrary commands

### Manual Review Checklist

Before marking skill complete:

- [ ] Description has action verb
- [ ] Description includes trigger keywords (how users will search)
- [ ] Description has "Use when" or equivalent
- [ ] Description mentions outcome
- [ ] Body has trigger table/list
- [ ] Body has decision tree or "when to use"
- [ ] Body has anti-patterns table
- [ ] Body has verification checklist
- [ ] Deep content moved to references/
- [ ] No changelog section in body
- [ ] No version/date metadata in body

---

## Part 5: Examples by Skill Type

### Automation Skills (metrics, security-detection)

**Description pattern**: `Collect/Detect + [data] + Use when [condition] + [outcome]`

**Body must have**:
- Trigger phrases for metric types
- Decision tree (when to use this vs manual)
- Verification checklist (validate output format)

### Workflow Skills (planner, research-and-incorporate)

**Description pattern**: `[Workflow verb] + [multi-step process] + Use when [starting condition] + [outcome]`

**Body must have**:
- Trigger table mapping phrases to workflow stages
- Decision tree (when full workflow vs shortcuts)
- Anti-patterns (common workflow mistakes)

### Diagnostic Skills (incoherence, analyze)

**Description pattern**: `Detect/Analyze + [problems] + Use when [symptoms] + [outcome]`

**Body must have**:
- Trigger phrases for symptoms
- Decision tree (what to analyze vs ignore)
- Verification checklist (validate findings)

---

## References

- [Skill Description Trigger Review](../analysis/skill-description-trigger-review.md) - 28-skill analysis
- [SkillForge Specification](../../.claude/skills/SkillForge/SKILL.md) - Skill creation framework
- [Session 372](../sessions/2026-01-03-session-372.md) - Standard creation session
- [ADR Review Debate Log](../critique/skill-description-trigger-standard-debate-log.md) - P0 issues addressed

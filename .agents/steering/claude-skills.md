---
name: Claude Skills
applyTo: ".claude/skills/**/*"
excludeFrom: ".claude/skills/**/node_modules/**"
priority: 8
version: 1.0.0
status: active
---

# Claude Skills Steering

Domain-specific guidance for creating and modifying Claude Code skills in `.claude/skills/`.

## Scope

**Applies to**: `.claude/skills/**/*` (all skill directories, scripts, and configuration)

## Pre-Flight Checks

Before starting skill work, answer these questions:

1. **New skill or update?** New skills require duplicate functionality check.
2. **Does a similar skill exist?** Search `.claude/skills/*/SKILL.md` descriptions.
3. **Is this skill-only?** Memory changes, hook changes, and ADR changes belong in separate PRs.

## Guidelines

### Language Selection (ADR-042)

New scripts use Python 3.10+ per ADR-042. Existing PowerShell scripts may be maintained in PowerShell.

| Scenario | Language | Reference |
|----------|----------|-----------|
| New skill script | Python (.py) | ADR-042 |
| Existing PowerShell maintenance | PowerShell (.ps1) | ADR-042 migration path |
| Hooks with LLM integration | Python (.py) | ADR-042 exception |

### SKILL.md Frontmatter

Every skill directory MUST contain a `SKILL.md` with valid frontmatter:

```yaml
---
name: skill-name
description: One-line description of what the skill does
---
```

Validate frontmatter before committing. The `name` field must match the directory name.

### Testing Requirements

- Python skills: pytest tests required
- PowerShell skills: Pester tests required (see `testing-approach.md` steering)
- Test files live alongside their scripts or in a `tests/` subdirectory

### Skill Structure

```text
.claude/skills/<skill-name>/
  SKILL.md          # Required: frontmatter + usage docs
  scripts/          # Implementation scripts
  tests/            # Tests (if not alongside scripts)
```

## Scope Control

PR #908 demonstrated scope explosion when skill work expanded into unrelated areas. Apply these constraints:

### One Skill, One Purpose

Each PR should modify one skill. If a skill change requires memory updates, hook changes, or ADR additions, split into separate PRs.

### File Count Limits

| Metric | Limit | Rationale |
|--------|-------|-----------|
| Files per PR | 10 or fewer | Reviewability |
| Commits per PR | 20 or fewer | Atomic changes |
| Skills per PR | 1 | Focused review |

### Scope Expansion Signals

Stop and reassess if you encounter any of these:

- Modifying files outside `.claude/skills/<target-skill>/`
- Creating new memory files (separate PR)
- Changing session protocol files (separate PR)
- Adding or modifying ADRs (separate PR with adr-review)

## Before PR Checklist

- [ ] SKILL.md frontmatter validates (name matches directory)
- [ ] Tests pass (pytest or Pester depending on language)
- [ ] No files outside the target skill directory modified (unless justified)
- [ ] Commit count is 20 or fewer
- [ ] File count is 10 or fewer

## Anti-Patterns

### Scope Explosion

```text
# BAD: Skill PR that also adds memories and modifies hooks
feat(skills): add new-skill
  .claude/skills/new-skill/SKILL.md
  .claude/skills/new-skill/scripts/run.py
  .serena/memories/new-memory-1.md       # Unrelated scope
  .serena/memories/new-memory-2.md       # Unrelated scope
  .claude/hooks/PreToolUse/new_hook.py   # Unrelated scope
```

```text
# GOOD: Focused skill PR
feat(skills): add new-skill
  .claude/skills/new-skill/SKILL.md
  .claude/skills/new-skill/scripts/run.py
  .claude/skills/new-skill/tests/test_run.py
```

### Missing Duplicate Check

Creating a skill without verifying no existing skill covers the same functionality. Search SKILL.md descriptions first.

### Ignoring Synthesis Panel

If architect, critic, or QA agents raise blocking issues during review, resolve them before creating the PR. Do not proceed with unresolved blocking findings.

## Examples

### Good: Focused Skill Update

```text
Task: Update the github skill to add issue labeling
Files changed:
  .claude/skills/github/scripts/issue/label_issue.py  (new)
  .claude/skills/github/tests/test_label_issue.py     (new)
  .claude/skills/github/SKILL.md                       (updated description)
```

### Bad: Unfocused Skill Work

```text
Task: Update the github skill to add issue labeling
Files changed:
  .claude/skills/github/scripts/issue/label_issue.py  (new)
  .agents/architecture/ADR-099-label-strategy.md       (scope creep)
  .serena/memories/github-labeling-patterns.md         (separate PR)
  .claude/hooks/PostToolUse/verify_labels.py           (separate PR)
  scripts/validate_labels.py                           (separate PR)
```

## References

- [ADR-042: Python Migration Strategy](../../.agents/architecture/ADR-042-python-migration-strategy.md)
- [PR #908 Retrospective](../../.agents/retrospective/2026-01-15-pr-908-comprehensive-retrospective.md)
- [Testing Approach Steering](./testing-approach.md)

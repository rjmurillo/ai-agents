# Skill-Governance-001: Consolidated Constraints

**Statement**: All project MUST-NOT patterns documented in PROJECT-CONSTRAINTS.md, read at session start.

**Evidence**: Session 15 - 5+ user interventions for violations of scattered preferences across multiple memories.

**Atomicity**: 90%

**Tag**: CRITICAL

**Impact**: 10/10 - Single source of truth for all constraints

## PROJECT-CONSTRAINTS.md Contents

```markdown
# Project Constraints

## Language Constraints
❌ MUST NOT: Create bash scripts
❌ MUST NOT: Create Python scripts
✅ MUST: Use PowerShell for all scripting
Reference: ADR-005, user-preference-no-bash-python

## Skill Usage Constraints
❌ MUST NOT: Use raw `gh` commands when `.claude/skills/github/` has capability
✅ MUST: Check `.claude/skills/` before writing GitHub operations
✅ MUST: Extend skills if missing, don't write inline
Reference: skill-usage-mandatory

## Workflow Constraints
❌ MUST NOT: Put business logic in workflow YAML
✅ MUST: Keep workflows <100 lines (orchestration only)
✅ MUST: Put logic in `.psm1` modules or `.claude/skills/`
Reference: ADR-006, pattern-thin-workflows

## Commit Constraints
❌ MUST NOT: Mix multiple logical changes in one commit
✅ MUST: One logical change per commit
✅ MUST: Max 5 files OR single topic in subject line
Reference: code-style-conventions
```

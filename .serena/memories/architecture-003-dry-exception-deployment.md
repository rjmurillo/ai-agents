# Skill-Architecture-003: DRY Exception for Deployment Units

## Statement

Apply DRY except for deployment units (agents, configs) - embed requirements for portability

## Context

When considering DRY refactoring. Exception: Files that ship to end-user machines must be self-contained. Embed content instead of referencing external files.

## Evidence

Commit 7d4e9d9 (2025-12-19): DRY pattern (external style guide) broke agent deployment. Fixed by embedding requirements. Deployment units need portability over DRY.

## Metrics

- Atomicity: 85%
- Impact: 9/10
- Category: architecture, dry-principle, deployment
- Created: 2025-12-19
- Tag: helpful
- Validated: 1

## Related Skills

- Skill-Deployment-001 (Agent Self-Containment)
- Skill-Architecture-015 (Deployment Path Validation)

## DRY Decision Matrix

| Artifact Type | Deployment | DRY Strategy |
|---------------|------------|--------------|
| Agent files (.md in src/claude/, templates/) | Ships to end user | EMBED (exception to DRY) |
| Workflow configs (.github/workflows/*.yml) | Ships to repo | EMBED (exception to DRY) |
| PowerShell modules (scripts/*.psm1) | Ships to deployments | EMBED (exception to DRY) |
| Internal docs (.agents/**/*.md) | Stays in repo | REFERENCE (apply DRY) |
| Source code (src/**/*.cs, src/**/*.ts) | Compiled/bundled | REFERENCE (apply DRY) |
| Build scripts (build/**/*.ps1) | Runs from repo | REFERENCE (apply DRY) |

## Key Principle

**Portability > DRY for deployment units**

If an artifact ships outside the repository structure, it must be self-contained even if this duplicates content.

## Application Pattern

**Source Tree (DRY applies)**:

```markdown
<!-- .agents/governance/CONSTRAINTS.md -->
# Project Constraints
[canonical constraints list]

<!-- .agents/architecture/ADR-005.md -->
**Constraints**: See .agents/governance/CONSTRAINTS.md
```

**Deployment Units (Embed for portability)**:

```markdown
<!-- src/claude/architect.md (ships to ~/.claude/) -->
**Constraints**:
- Use PowerShell 7.2+ for all scripting
- Follow ADR-005 for workflow design
- No Node.js or Python dependencies
[...full constraints embedded...]
```

## Success Criteria

- Deployment units contain all required content inline
- Source tree files use DRY (reference canonical sources)
- No broken references when artifacts ship to end-user machines
- Clear distinction between "ships" (embed) vs "stays in repo" (reference)

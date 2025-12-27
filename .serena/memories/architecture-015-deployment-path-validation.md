# Skill-Architecture-015: Deployment Path Validation

## Statement

Before creating file references, verify path exists at deployment location, not just source tree

## Context

Before committing file references in agent files, configs, or scripts. Validate from deployment context: ~/.claude/, ~/.copilot/, ~/.vscode/, not from repo root.

## Evidence

Commit 3e74c7e (2025-12-19): Referenced src/STYLE-GUIDE.md assuming source tree access. Deployment to ~/.claude/ broke reference. Required 36-file fix in commit 7d4e9d9.

## Metrics

- Atomicity: 92%
- Impact: 8/10
- Category: architecture, deployment, validation
- Created: 2025-12-19
- Tag: helpful
- Validated: 1

## Related Skills

- Skill-Deployment-001 (Agent Self-Containment)
- Skill-Architecture-003 (DRY Exception for Deployment Units)

## Validation Checklist

When adding file references to agent files or configs:

1. Identify deployment location:
   - Claude agents: ~/.claude/
   - Copilot agents: ~/.copilot/
   - VS Code agents: ~/.vscode/
   - Templates: Copied to user machines

2. Verify path resolution:
   - Will this file exist at deployment location?
   - Is path relative to deployment directory (not repo root)?
   - Is file embedded in agent package?

3. Decision:
   - If path exists at deployment: OK to reference
   - If path only exists in source tree: EMBED content or REMOVE reference

## Common Mistakes

- Assuming src/ directory exists at runtime
- Referencing .agents/ files from shipped agents
- Using repo-root-relative paths in deployment units

## Success Criteria

- All file references resolve from deployment location
- No broken references when agent runs on end-user machine
- Path validation performed before commit

# Skill-Deployment-001: Agent Self-Containment

## Statement

Agent files ship as independent units - embed requirements, do not reference external files

## Context

When adding documentation, guidelines, or requirements to agent files. Agent files are copied to end-user machines (~/.claude/, ~/.copilot/, ~/.vscode/) without source tree access.

## Evidence

Commit 7d4e9d9 (2025-12-19): External reference to src/STYLE-GUIDE.md failed because agents ship independently. Fixed by embedding requirements in all 36 agent files.

## Metrics

- Atomicity: 95%
- Impact: 9/10
- Category: deployment, agent-development, self-contained
- Created: 2025-12-19
- Tag: helpful
- Validated: 1

## Related Skills

- Skill-Architecture-015 (Deployment Path Validation)
- Skill-Planning-022 (Multi-Platform Scope)

## Application Pattern

**Before**:
```markdown
**MUST READ**: Before producing any output, reference src/STYLE-GUIDE.md for:
```

**After**:
```markdown
**Communication Standards**:
- Use clear, direct language
- Avoid emojis unless explicitly requested
- Structure responses with headers
[...embedded content...]
```

## Anti-Pattern

Referencing external files from agent prompts that ship to end-user machines:
- src/STYLE-GUIDE.md
- .agents/governance/CONSTRAINTS.md
- Any file outside agent deployment directory

## Success Criteria

- Agent file contains all required content inline
- No references to paths outside deployment location
- Agent works independently when copied to ~/.claude/, ~/.copilot/, ~/.vscode/

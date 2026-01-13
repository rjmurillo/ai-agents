# Skill-Planning-007: Multi-Platform Agent Scope

**Statement**: Agent changes affect multiple platforms: Claude, templates, copilot-cli, vs-code-agents (72 files minimum).

**Context**: During planning phase for agent enhancements.

**Evidence**: Commit 3e74c7e: Modified 18 files. Full scope should have been 72 files (4 platforms).

**Atomicity**: 88% | **Impact**: 8/10

## Platform Scope Checklist

| Platform | Directory | Count |
|----------|-----------|-------|
| Claude Code | src/claude/ | 18 agents |
| Templates | templates/agents/ | 18 agents |
| Copilot CLI | src/copilot-cli/ | 18 agents |
| VS Code | src/vs-code-agents/ | 18 agents |
| **Total** | **4 platforms** | **72 files minimum** |

## Common Gaps

- Modifying Claude only (18 files)
- Missing templates (36 files)
- Forgetting copilot-cli/vs-code-agents

## Related

- [planning-003-parallel-exploration-pattern](planning-003-parallel-exploration-pattern.md)
- [planning-004-approval-checkpoint](planning-004-approval-checkpoint.md)
- [planning-checkbox-manifest](planning-checkbox-manifest.md)
- [planning-priority-consistency](planning-priority-consistency.md)
- [planning-task-descriptions](planning-task-descriptions.md)

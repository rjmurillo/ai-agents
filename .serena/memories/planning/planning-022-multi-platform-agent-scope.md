# Skill-Planning-022: Multi-Platform Agent Scope

## Statement

Agent changes affect multiple platforms: Claude, templates, copilot-cli, vs-code-agents (72 files minimum)

## Context

During planning phase for agent enhancements. All platforms must be in scope: src/claude/ (18), templates/agents/ (18), src/copilot-cli/ (18), src/vs-code-agents/ (18).

## Evidence

Commit 3e74c7e (2025-12-19): Modified 18 Claude agents. Commit 7d4e9d9: Extended to 36 files (added templates). Full scope should have been 72 files (4 platforms).

## Metrics

- Atomicity: 88%
- Impact: 8/10
- Category: planning, scope, multi-platform
- Created: 2025-12-19
- Tag: helpful
- Validated: 1

## Related Skills

- Skill-Deployment-001 (Agent Self-Containment)
- Skill-Architecture-015 (Deployment Path Validation)

## Platform Scope Checklist

When planning agent enhancements:

| Platform | Directory | Count | Status |
|----------|-----------|-------|--------|
| Claude Code | src/claude/ | 18 agents | Required |
| Templates | templates/agents/ | 18 agents | Required |
| Copilot CLI | src/copilot-cli/ | 18 agents | Required |
| VS Code | src/vs-code-agents/ | 18 agents | Required |
| **Total** | **4 platforms** | **72 files** | **Minimum scope** |

## Common Scope Gaps

- Modifying Claude agents only (18 files instead of 72)
- Missing templates directory (36 files instead of 72)
- Forgetting copilot-cli or vs-code-agents platforms

## Success Criteria

- Planning document lists all 4 platforms
- Implementation modifies all 72 agent files (or justifies exclusions)
- Testing validates changes across all platforms
- Documentation updated for all platforms

## Phase Application

**Planning Phase**: Define scope including all platforms
**Implementation Phase**: Apply changes to all platforms systematically
**Verification Phase**: Test one agent per platform to validate consistency
